import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest import mock
import unittest

from orch.conductor.domain.report import findings_problems
from orch.conductor.infrastructure.results import completed_error_review, green_prose


class ProseReviewTest(unittest.TestCase):
    def test_green_preserves_risk(self):
        text = ('## Review Findings\n\nNo findings.\n\n## Questions\n\nNone.\n\n'
                '## Material Residual Risk\n\n- A race remains.\n\n## Verdict\n\n`GREEN`\n')
        result = green_prose(text)
        self.assertEqual(result, {'verdict': 'GREEN', 'findings': [], 'questions': [],
                                  'residual_risk': '- A race remains.'})
        reordered = ('## Review Findings\n\nNone.\n\n## Questions\n\nNone.\n\n'
                     '## Verdict\n\n**`GREEN`**\n\nExplanation.\n\n'
                     '## Material Residual Risk\n\n- A race remains.\n')
        self.assertEqual(green_prose(reordered)['residual_risk'], 'Explanation.\n\n- A race remains.')
        self.assertEqual(green_prose(reordered.replace('## Review Findings', '## Review-findings')),
                         green_prose(reordered))
        self.assertEqual(green_prose(reordered.replace('## ', '### ')), green_prose(reordered))
        inline = reordered.replace('## Review Findings', '## Findings').replace('**`GREEN`**\n\nExplanation.',
                                                                                 '**GREEN** — Explanation.')
        self.assertEqual(green_prose(inline), green_prose(reordered))
        for invalid in (text.replace('No findings.', 'A finding.'),
                        text.replace('None.', 'Why?'), text.replace('`GREEN`', '`RED`'),
                        text.replace('## Verdict', '## Verdict\n## Verdict')):
            self.assertIsNone(green_prose(invalid))

    def test_prose_does_not_erase_findings_or_questions(self):
        template = ('## Review Findings\n\n{}\n\n## Questions\n\n{}\n\n'
                    '## Material Residual Risk\n\nRemaining risk.\n\n## Verdict\n\nGREEN\n')
        for findings, questions in (
                ('[Minor] Preserve this finding.', 'None.'),
                ('No findings. [Major] Must fix.', 'None.'),
                ('No findings.', 'None. Why is this safe?')):
            with self.subTest(findings=findings, questions=questions):
                self.assertIsNone(green_prose(template.format(findings, questions)))

    def test_completed_review_before_503_preserves_verdict_and_error(self):
        body = ('Review complete.\n```review-findings\n'
                '{"verdict":"GREEN","findings":[],"questions":[],"residual_risk":"race"}\n```')
        def raw(doc):
            return {"type": "agy.raw", "line": json.dumps(doc)}
        update = {"conversation_id": "s", "step_index": 4, "step_type": "agent_response",
                  "state": "DONE", "text_delta": body}
        terminal = {"conversation_id": "s", "status": "ERROR", "response": body,
                    "error": "UNAVAILABLE (code 503): capacity"}
        events = [raw({"event": "step_update", "step_update": update}),
                  raw({"event": "result", "result": terminal})]
        result = completed_error_review(events, findings_problems)
        self.assertEqual(result["findings"]["residual_risk"], "race")
        self.assertEqual(result["provider_error"], terminal["error"])
        for key, value in (("status", "SUCCESS"), ("error", "authentication error"),
                           ("response", "truncated"), ("conversation_id", "other")):
            invalid = copy.deepcopy(events)
            event = json.loads(invalid[1]["line"])
            event["result"][key] = value
            invalid[1]["line"] = json.dumps(event)
            self.assertIsNone(completed_error_review(invalid, findings_problems))
        self.assertIsNone(completed_error_review(events[1:], findings_problems))

    def test_replay_binds_tree_route_attempt_and_provider_error(self):
        from orch.conductor.domain.stop import Stop
        from orch.conductor.stages import review
        body = ('```review-findings\n'
                '{"verdict":"GREEN","findings":[],"questions":[],"residual_risk":"race"}\n```')
        def raw(doc):
            return {"type": "agy.raw", "line": json.dumps(doc)}
        update = {"conversation_id": "s", "step_index": 4, "step_type": "agent_response",
                  "state": "DONE", "text_delta": body}
        terminal = {"conversation_id": "s", "status": "ERROR", "response": body,
                    "error": "UNAVAILABLE (code 503): capacity"}
        events = [raw({"event": "step_update", "step_update": update}),
                  raw({"event": "result", "result": terminal})]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "streams").mkdir()
            (root / "agents" / "reviewer").mkdir(parents=True)
            data = ("\n".join(json.dumps(event) for event in events) + "\n").encode()
            (root / "streams" / "review.1.jsonl").write_bytes(data)
            route = {"provider": "antigravity", "model": "m", "effort": "high"}
            (root / "agents" / "reviewer" / "request.json").write_text(json.dumps(
                {"step": "review.1", "role": "reviewer", "route": route}))
            state = {"steps": {"review.1": {"status": "stopped", "code": "ROLE_FAILED"}},
                     "retries_by_stage": {"review.1": 1}, "review_marks": {"1": {"file": "hash"}}}
            item = SimpleNamespace(routes={"reviewer": route}, state=state, input_doc={}, directory=root, ref="I")
            captured = []
            def step(_item, _key, run, **_kwargs):
                result = run()
                captured.append(result)
                return result
            owner = SimpleNamespace(project=root, _upgrade_reviewer=lambda _: None, _review_focus=lambda _: (None, None),
                _review_base=lambda _: "base", _changed=lambda _: ["file"], _not_the_role=lambda _: [],
                _relative=lambda path: str(path), _step=step, _verdict_file=lambda _: None,
                label=lambda _: "route", progress=SimpleNamespace(emit=lambda *a, **kw: None))
            env = {"SKM_ORCH_ACCEPT_REVIEW_AFTER_PROVIDER_ERROR": "1",
                   "SKM_ORCH_PROSE_REVIEW_SHA256": hashlib.sha256(data).hexdigest()}
            with mock.patch.dict(os.environ, env), \
                 mock.patch.object(review.checks_mod, "candidate", return_value={"paths": {"file": "blob"}}), \
                 mock.patch.object(review.checks_mod, "review_outside", return_value={}), \
                 mock.patch.object(review.checks_mod, "dirty_files", return_value={"file": "hash"}), \
                 mock.patch.object(review.scopes, "own", side_effect=lambda paths, _: list(paths)):
                self.assertEqual(review.review(owner, item, 1, [])['verdict'], 'GREEN')
                self.assertIn('UNAVAILABLE (code 503)', captured[0]['healed'][0])
                self.assertEqual(state['retries_by_stage']['review.1'], 1)
                state['review_marks']['1']['file'] = 'changed'
                with self.assertRaises(Stop) as error:
                    review.review(owner, item, 1, [])
                self.assertEqual(error.exception.code, 'REVIEW_RECOVERY_CHANGED')
                state['review_marks']['1']['file'] = 'hash'
                item.routes['reviewer'] = dict(route, model='wrong')
                with self.assertRaises(Stop) as error:
                    review.review(owner, item, 1, [])
                self.assertEqual(error.exception.code, 'REVIEW_RECOVERY_INVALID')
                item.routes['reviewer'] = route
                state['retries_by_stage']['review.1'] = 2
                (root / 'streams' / 'review.1-a2.jsonl').write_text(json.dumps(
                    raw({'event': 'result', 'result': {'response': 'later review'}})) + '\n')
                with mock.patch.dict(os.environ, {'SKM_ORCH_REVIEW_RECOVERY_ATTEMPT': '1'}):
                    with self.assertRaises(Stop) as error:
                        review.review(owner, item, 1, [])
                self.assertEqual(error.exception.code, 'REVIEW_RECOVERY_INVALID')


if __name__ == '__main__':
    unittest.main()
