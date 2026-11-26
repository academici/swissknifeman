-- 0027_execution_continuation: durable server-private continuation on an existing attempt.
-- NULL means no saved continuation or legacy-unknown; historical attempts stay NULL, no inferred replay/backfill.
-- The application validates urn:skm:execution:pending-continuation:v1 and canonical JSON <= 65536 bytes.
-- This defensive JSONB shape/131072-byte gate does not prove semantic UUIDs, exact refs, current fencing,
-- registered host-stage semantics, consume-once transitions or exclusivity with active stage records.
-- The immediate CHECK requires clearing continuation in the SAME UPDATE that sets a terminal attempt state.

ALTER TABLE skm_execution.attempts
    ADD COLUMN continuation jsonb NULL,
    ADD CONSTRAINT ck_attempts__continuation CHECK (
        continuation IS NULL OR COALESCE(
            state NOT IN ('completed', 'ownership_lost', 'abandoned')
            AND CASE WHEN jsonb_typeof(continuation) = 'object' THEN
                octet_length(continuation::text) <= 131072
                AND continuation -> 'schema_version' = '1'::jsonb
                AND jsonb_typeof(continuation -> 'continuation_id') = 'string'
                AND char_length(continuation ->> 'continuation_id') BETWEEN 1 AND 64
                AND CASE continuation ->> 'kind'
                    WHEN 'stage' THEN
                        continuation ?& ARRAY['schema_version', 'continuation_id', 'kind', 'stage', 'cause']
                        AND continuation - ARRAY['schema_version', 'continuation_id', 'kind', 'stage', 'cause'] = '{}'::jsonb
                        AND jsonb_typeof(continuation -> 'cause') = 'object'
                        AND CASE WHEN jsonb_typeof(continuation -> 'stage') = 'object' THEN
                            (continuation -> 'stage') ?& ARRAY['stage_id', 'stage_type', 'mode', 'round_no',
                                'params', 'not_before', 'route_override', 'feedback_refs', 'input_output_id', 'retry_of_id']
                            AND jsonb_typeof(continuation #> '{stage,stage_id}') = 'string'
                            AND jsonb_typeof(continuation #> '{stage,stage_type}') = 'string'
                            AND jsonb_typeof(continuation #> '{stage,mode}') = 'string'
                            AND CASE WHEN jsonb_typeof(continuation #> '{stage,round_no}') = 'number' THEN
                                (continuation #>> '{stage,round_no}')::numeric >= 1
                                AND trunc((continuation #>> '{stage,round_no}')::numeric)
                                    = (continuation #>> '{stage,round_no}')::numeric
                                ELSE false END
                            AND jsonb_typeof(continuation #> '{stage,params}') = 'object'
                            AND jsonb_typeof(continuation #> '{stage,not_before}') IN ('string', 'null')
                            AND jsonb_typeof(continuation #> '{stage,route_override}') IN ('object', 'null')
                            AND jsonb_typeof(continuation #> '{stage,input_output_id}') IN ('string', 'null')
                            AND jsonb_typeof(continuation #> '{stage,retry_of_id}') IN ('string', 'null')
                            AND CASE WHEN jsonb_typeof(continuation #> '{stage,feedback_refs}') = 'object' THEN
                                (continuation #> '{stage,feedback_refs}') ?& ARRAY['fix_brief_id',
                                    'schema_errors_step_id', 'answer_request_ids', 'advice_step_id',
                                    'interrupted_stage_record_id']
                                AND jsonb_typeof(continuation #> '{stage,feedback_refs,fix_brief_id}') IN ('string', 'null')
                                AND jsonb_typeof(continuation #> '{stage,feedback_refs,schema_errors_step_id}') IN ('string', 'null')
                                AND jsonb_typeof(continuation #> '{stage,feedback_refs,advice_step_id}') IN ('string', 'null')
                                AND jsonb_typeof(continuation #> '{stage,feedback_refs,interrupted_stage_record_id}') IN ('string', 'null')
                                AND CASE WHEN jsonb_typeof(continuation #> '{stage,feedback_refs,answer_request_ids}') = 'array'
                                    THEN jsonb_array_length(continuation #> '{stage,feedback_refs,answer_request_ids}') <= 128
                                    ELSE false END
                                ELSE false END
                            ELSE false END
                    WHEN 'advance' THEN
                        continuation ?& ARRAY['schema_version', 'continuation_id', 'kind', 'triggers']
                        AND continuation - ARRAY['schema_version', 'continuation_id', 'kind', 'triggers'] = '{}'::jsonb
                        AND CASE WHEN jsonb_typeof(continuation -> 'triggers') = 'array' THEN
                            jsonb_array_length(continuation -> 'triggers') BETWEEN 1 AND 128
                            AND NOT jsonb_path_exists(continuation,
                                '$.triggers[*] ? (@.type() != "object" || !exists(@.source_event_id) || @.source_event_id.type() != "string" || @.source_event_id == "" || !exists(@.cause) || @.cause.type() != "object")')
                            ELSE false END
                    ELSE false END
                ELSE false END,
            false)
    );
