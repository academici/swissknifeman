"""Codex adapter is strict at the raw JSONL boundary."""
import subprocess
import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from task.token_probe_codex import CodexExecProbeAdapter, CodexProbeError


class TestCodexExecProbeAdapter(unittest.TestCase):
    def completed(self, total=123, extra=None):
        usage = {"input_tokens": total, "cached_input_tokens": 99}
        if extra:
            usage.update(extra)
        return subprocess.CompletedProcess([], 0, '{"type":"turn.completed","usage":' + str(usage).replace("'", '"') + "}\n", "")

    def test_argv_is_isolated_and_pinned(self):
        adapter = CodexExecProbeAdapter("gpt-5.6-terra")
        argv = adapter.build_argv("/tmp/empty")
        self.assertEqual(argv[:7], ["codex", "-C", "/tmp/empty", "-m", "gpt-5.6-terra", "-c", 'model_reasoning_effort="low"'])
        self.assertIn("--ephemeral", argv)
        self.assertIn("--ignore-user-config", argv)
        self.assertIn("--ignore-rules", argv)
        self.assertIn("--skip-git-repo-check", argv)

    @unittest.mock.patch("task.token_probe_codex.subprocess.run")
    def test_cache_is_not_added_to_total(self, run):
        run.side_effect = [self.completed(), subprocess.CompletedProcess([], 0, "codex-cli 0.147.0\n", "")]
        record = CodexExecProbeAdapter("gpt-5.6-terra").probe("payload")
        self.assertEqual(record.input_tokens_total, 123)
        self.assertEqual(record.usage_breakdown["cached_input_tokens"], 99)

    @unittest.mock.patch("task.token_probe_codex.subprocess.run")
    def test_missing_or_duplicate_terminal_is_rejected(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, '{"type":"item.completed"}\n', "")
        with self.assertRaises(CodexProbeError):
            CodexExecProbeAdapter("gpt-5.6-terra").probe("payload")
        run.return_value = subprocess.CompletedProcess([], 0,
            '{"type":"turn.completed","usage":{"input_tokens":1}}\n'
            '{"type":"turn.completed","usage":{"input_tokens":2}}\n', "")
        with self.assertRaises(CodexProbeError):
            CodexExecProbeAdapter("gpt-5.6-terra").probe("payload")

    @unittest.mock.patch("task.token_probe_codex.subprocess.run")
    def test_bad_exit_json_and_usage_are_rejected(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, "", "bad")
        with self.assertRaises(CodexProbeError):
            CodexExecProbeAdapter("gpt-5.6-terra").probe("payload")
        run.return_value = subprocess.CompletedProcess([], 0, "not json\n", "")
        with self.assertRaises(CodexProbeError):
            CodexExecProbeAdapter("gpt-5.6-terra").probe("payload")
        run.return_value = subprocess.CompletedProcess([], 0,
            '{"type":"turn.completed","usage":{"input_tokens":-1}}\n', "")
        with self.assertRaises(CodexProbeError):
            CodexExecProbeAdapter("gpt-5.6-terra").probe("payload")
