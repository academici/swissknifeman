"""The risk score of the dynamic review (P7.2): a pure function of facts, weights and patterns."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from orch.conductor import risk, scope


def names(result: dict) -> list:
    return [row["name"] for row in result["features"]]


class ScoreTests(unittest.TestCase):
    def test_no_facts_score_zero(self):
        self.assertEqual(risk.score({}), {"score": 0, "features": []})

    def test_every_default_feature_with_its_weight_and_evidence(self):
        facts = {"changed": ["bin/tool", "packages/orch/schemas/x.json", "src/auth/login.py", "packages/aicore/lib/a.py"],
                 "outside": ["docs/a.md"], "diff_lines": 401, "red_first": True, "deviation": True, "recommended": True}
        found = risk.score(facts)
        self.assertEqual(sorted(names(found)), sorted(risk.DEFAULT_WEIGHTS))
        self.assertEqual(found["score"], 100)  # 170 capped
        weights = {row["name"]: row["weight"] for row in found["features"]}
        self.assertEqual(weights, risk.DEFAULT_WEIGHTS)
        evidence = {row["name"]: row["evidence"] for row in found["features"]}
        self.assertIn("bin/tool", evidence["public_cli"])
        self.assertEqual(evidence["diff_size"], "401 changed lines > 400")
        self.assertIn("docs/a.md", evidence["outside_write_set"])

    def test_one_feature_adds_its_weight_once_however_many_paths(self):
        found = risk.score({"changed": ["a/schemas/1.json", "b/schemas/2.json", "c/migrations/3.sql"]})
        self.assertEqual((names(found), found["score"]), (["schema"], 25))
        many = risk.score({"changed": [f"a/schemas/{n}.json" for n in range(5)]})
        self.assertIn("(+2 more)", many["features"][0]["evidence"])

    def test_diff_size_needs_more_lines_than_the_limit(self):
        self.assertEqual(risk.score({"diff_lines": 400})["score"], 0)
        self.assertEqual(risk.score({"diff_lines": 401})["score"], 10)
        self.assertEqual(risk.score({"diff_lines": 51}, {"diff_lines": 50})["score"], 10)

    def test_a_project_changes_weights_and_patterns_and_a_zero_weight_turns_a_feature_off(self):
        config = {"weights": {"schema": 70, "diff_size": 0}, "patterns": {"schema": ["contracts/**"]}}
        found = risk.score({"changed": ["contracts/a.json", "x/schemas/b.json"], "diff_lines": 9999}, config)
        self.assertEqual((names(found), found["score"]), (["schema"], 70))  # the schema pattern was replaced
        self.assertEqual(risk.score({"recommended": True}, {"weights": {"executor_recommended": 0}})["score"], 0)

    def test_the_score_is_pure(self):
        facts, config = {"changed": ["bin/x"], "red_first": True}, risk.defaults()
        before = (dict(facts), risk.defaults())
        self.assertEqual(risk.score(facts, config), risk.score(facts, config))
        self.assertEqual((facts, config), before)


class DiffLinesTests(unittest.TestCase):
    """``scope.diff_lines`` counts an untracked path the way ``git diff --numstat`` counts it once staged."""

    def test_untracked_text_counts_lines_and_binary_and_symlink_count_like_numstat(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            git = lambda *args: subprocess.run(["git", *args], cwd=project, capture_output=True, text=True, check=True).stdout
            git("init", "-q")
            git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "base")
            (project / "a.txt").write_text("1\n2\n3\n", encoding="utf-8")
            (project / "blob.bin").write_bytes(b"\n" * 500 + b"\0" * 100)
            (project / "big.txt").write_text("x\n" * 1000, encoding="utf-8")
            (project / "link.txt").symlink_to("big.txt")
            paths = ["a.txt", "blob.bin", "link.txt"]
            before = scope.diff_lines(project, paths)
            git("add", "--", *paths)
            staged = sum(int(row.split("\t")[0]) + int(row.split("\t")[1]) for row in
                         git("diff", "--cached", "--numstat", "--", *paths).splitlines() if row[0].isdigit())
            self.assertEqual((before, staged), (4, 4))  # 3 text lines + 1 for the symlink, none for the binary
            self.assertEqual(scope.diff_lines(project, []), 0)


if __name__ == "__main__":
    unittest.main()
