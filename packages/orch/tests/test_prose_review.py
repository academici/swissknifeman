import unittest

from orch.conductor.infrastructure.results import green_prose


class ProseReviewTest(unittest.TestCase):
    def test_green_preserves_risk(self):
        text = ('## Review Findings\n\nNo findings.\n\n## Questions\n\nNone.\n\n'
                '## Material Residual Risk\n\n- A race remains.\n\n## Verdict\n\n`GREEN`\n')
        result = green_prose(text)
        self.assertEqual(result, {'verdict': 'GREEN', 'findings': [], 'questions': [],
                                  'residual_risk': '- A race remains.'})
        for invalid in (text.replace('No findings.', 'A finding.'),
                        text.replace('None.', 'Why?'), text.replace('`GREEN`', '`RED`'),
                        text.replace('## Verdict', '## Verdict\n## Verdict')):
            self.assertIsNone(green_prose(invalid))


if __name__ == '__main__':
    unittest.main()
