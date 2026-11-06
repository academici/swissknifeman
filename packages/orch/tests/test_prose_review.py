import copy
import json
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
        for invalid in (text.replace('No findings.', 'A finding.'),
                        text.replace('None.', 'Why?'), text.replace('`GREEN`', '`RED`'),
                        text.replace('## Verdict', '## Verdict\n## Verdict')):
            self.assertIsNone(green_prose(invalid))

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


if __name__ == '__main__':
    unittest.main()
