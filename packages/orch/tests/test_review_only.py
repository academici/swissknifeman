"""Review-only conductor with fake roles: dirty worktree, receipt and compact stdout."""
import copy
import json
from pathlib import Path
import stat
import subprocess
import sys
import venv
from unittest import mock

from orch import adhoc
from orch.conductor import checks, contract, records
from tests.test_conductor import ConductorCase, GREEN, FINDING


class ReviewOnlyTests(ConductorCase):
    def review_with_acceptance(self, **acceptance):
        doc = adhoc.build_adhoc_input(None, [], review="HEAD..WORKTREE", **acceptance)
        path = self.project.parent / "review-check.json"
        path.write_text(json.dumps(doc))
        self.script({"reviewer": [GREEN], "triager": [{"result": {"confirmed": [], "rejected": []}}]})
        return doc, path

    def test_command_acceptance_runs_and_registers_engine_evidence(self):
        (self.project / "README.md").write_text("candidate\n")
        doc, path = self.review_with_acceptance(checks=["V1=test \"$(cat README.md)\" = candidate"])
        code, out, err = self.conduct("run", "--input", path, "--json-lines")
        self.assertEqual(code, 0, err)
        evidence = list((self.project / ".swissknifeman" / "orch-artifacts").rglob("evidence/V1.json"))
        self.assertTrue(evidence)
        found = json.loads(evidence[0].read_text())
        self.assertEqual((found["check_id"], found["exit"], found["producer"]["kind"]), ("V1", 0, "engine"))
        self.assertEqual(found["candidate"]["head"], self.git("rev-parse", "HEAD").strip())
        self.assertEqual(json.loads(out.splitlines()[-1])["verdict"], "GREEN")

    def test_red_command_does_not_register_green_review(self):
        _, path = self.review_with_acceptance(checks=["V1=false"])
        code, _, err = self.conduct("run", "--input", path, "--json-lines")
        self.assertNotEqual(code, 0)
        self.assertIn("REGISTER_EVIDENCE_RED", err)

    def test_missing_evidence_does_not_register(self):
        _, path = self.review_with_acceptance(checks=["V1=true"])
        with mock.patch.object(checks, "run_checks", return_value=[{"id": "V1", "kind": "acceptance", "green": True}]):
            code, _, err = self.conduct("run", "--input", path, "--json-lines")
        self.assertNotEqual(code, 0)
        self.assertIn("REGISTER_EVIDENCE_MISSING", err)

    def test_manual_procedure_is_not_invented(self):
        _, path = self.review_with_acceptance(procedures=["V1=Inspect the result"])
        code, _, err = self.conduct("run", "--input", path, "--json-lines")
        self.assertNotEqual(code, 0)
        self.assertIn("REGISTER_EVIDENCE_MISSING", err)

    def test_command_mutating_candidate_stops_before_registration(self):
        before = (self.project / "README.md").read_text()
        _, path = self.review_with_acceptance(checks=["V1=echo changed > README.md"])
        code, _, err = self.conduct("run", "--input", path, "--json-lines")
        self.assertNotEqual(code, 0)
        self.assertIn("REGISTER_EVIDENCE_RED", err)
        self.assertEqual((self.project / "README.md").read_text(), before)

    def test_temporary_substitution_is_denied_and_tmpdir_is_writable(self):
        before = (self.project / "README.md").read_text()
        command = ('cp README.md "$TMPDIR/original" && '
                   'if echo substituted > README.md; then cp "$TMPDIR/original" README.md; exit 0; else exit 1; fi')
        _, path = self.review_with_acceptance(checks=["V1=" + command])
        code, _, err = self.conduct("run", "--input", path, "--json-lines")
        self.assertNotEqual(code, 0, err)
        self.assertIn("REGISTER_EVIDENCE_RED", err)
        self.assertEqual((self.project / "README.md").read_text(), before)

    def test_isolated_tmp_is_writable(self):
        _, path = self.review_with_acceptance(checks=['V1=echo ok > "$TMPDIR/value" && test "$(cat "$TMPDIR/value")" = ok'])
        code, _, err = self.conduct("run", "--input", path, "--json-lines")
        self.assertEqual(code, 0, err)

    def test_metadata_substitution_is_denied(self):
        candidate = self.project / "README.md"
        original = stat.S_IMODE(candidate.stat().st_mode)
        _, path = self.review_with_acceptance(checks=[
            'V1=chmod 0755 README.md && test -x README.md && chmod 0644 README.md'])
        code, _, err = self.conduct("run", "--input", path, "--json-lines")
        self.assertNotEqual(code, 0, err)
        self.assertIn("REGISTER_EVIDENCE_RED", err)
        self.assertEqual(stat.S_IMODE(candidate.stat().st_mode), original)

    def test_guard_allows_python_script_and_keeps_other_ioctls_denied(self):
        candidate = self.project / "probe.py"
        candidate.write_text(
            "import ctypes, errno, fcntl, os\n"
            "fd = os.open('README.md', os.O_RDONLY)\n"
            "fcntl.ioctl(fd, 0x5451)  # FIOCLEX\n"
            "assert fcntl.fcntl(fd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC\n"
            "libc = ctypes.CDLL(None, use_errno=True)\n"
            "assert libc.ioctl(fd, 0x40086602, 0) == -1  # FS_IOC_SETFLAGS\n"
            "assert ctypes.get_errno() == errno.EPERM\n"
            "print('guarded script ran')\n")
        _, path = self.review_with_acceptance(checks=["V1=/usr/bin/python3 probe.py"])
        code, _, err = self.conduct("run", "--input", path, "--json-lines")
        self.assertEqual(code, 0, err)
        evidence = list((self.project / ".swissknifeman" / "orch-artifacts").rglob("evidence/V1.json"))
        self.assertTrue(evidence)
        self.assertEqual(json.loads(evidence[0].read_text())["exit"], 0)

    def test_xattrat_syscalls_are_denied(self):
        script = checks.ORCH_ROOT / "scripts" / "ro-run.py"
        probe = ("import ctypes, errno; libc = ctypes.CDLL(None, use_errno=True); "
                 "assert all(libc.syscall(n, -100, b'README.md', 0, b'user.guard_probe', 0, 0) == -1 "
                 "and ctypes.get_errno() == errno.EPERM for n in (463, 466))")
        result = subprocess.run([sys.executable, "-I", "-S", str(script), "--metadata-guard",
                                 "--no-default-rw", "--protect", str(self.project), "--",
                                 sys.executable, "-I", "-S", "-c", probe],
                                cwd=self.project, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_file_setattr_and_unknown_syscalls_are_denied(self):
        script = checks.ORCH_ROOT / "scripts" / "ro-run.py"
        probe = ("import ctypes, errno; libc = ctypes.CDLL(None, use_errno=True); "
                 "attr = ctypes.create_string_buffer(24); ctypes.c_uint64.from_buffer(attr).value = 0x80; "
                 "assert libc.syscall(469, -100, b'README.md', ctypes.byref(attr), 24, 0) == -1 "
                 "and ctypes.get_errno() == errno.EPERM; "
                 "assert all(libc.syscall(n) == -1 and ctypes.get_errno() == errno.EPERM "
                 "for n in (337, 423, 470, 1000))")
        result = subprocess.run([sys.executable, "-I", "-S", str(script), "--metadata-guard",
                                 "--no-default-rw", "--protect", str(self.project), "--",
                                 sys.executable, "-I", "-S", "-c", probe],
                                cwd=self.project, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_virtualenv_site_and_pth_cannot_run_before_guard(self):
        environment = self.project.parent / "guard-venv"
        venv.create(environment, with_pip=False)
        python = environment / "bin" / "python"
        site = subprocess.check_output([str(python), "-I", "-c",
                                        "import site; print(site.getsitepackages()[0])"], text=True).strip()
        candidate = self.project / "README.md"
        before = candidate.read_text()
        markers = [self.project.parent / "site-loaded", self.project.parent / "pth-loaded"]
        for filename, marker in zip(("sitecustomize.py", "guard_probe.pth"), markers):
            payload = ("import sys; from pathlib import Path; "
                       f"Path({str(marker)!r}).write_text('loaded'); "
                       f"Path({str(candidate)!r}).write_text('substituted') if sys.argv[0].endswith('/ro-run.py') else None\n")
            if filename.endswith(".pth"):
                payload = payload.rstrip() + f"; sys.path.insert(0, {site!r})\n"
            (Path(site) / filename).write_text(payload)
        subprocess.run([str(python), "-I", "-c", "pass"], check=True)
        for marker in markers:
            self.assertTrue(marker.exists())
            marker.unlink()
        _, path = self.review_with_acceptance(checks=["V1=true"])
        with mock.patch.object(checks.sys, "executable", str(python)):
            code, _, err = self.conduct("run", "--input", path, "--json-lines")
        self.assertEqual(code, 0, err)
        self.assertFalse(any(marker.exists() for marker in markers))
        self.assertEqual(candidate.read_text(), before)

    def test_pythonpath_sitecustomize_cannot_run_before_guard(self):
        candidate = self.project / "README.md"
        before = candidate.read_text()
        custom = self.project / "custom"
        custom.mkdir()
        (custom / "sitecustomize.py").write_text(
            "import sys\nfrom pathlib import Path\n"
            "if sys.argv[0].endswith('/ro-run.py'):\n"
            f"    Path({str(candidate)!r}).write_text('substituted')\n")
        self.git("add", "custom/sitecustomize.py")
        self.git("commit", "-qm", "sitecustomize fixture")
        _, path = self.review_with_acceptance(checks=["V1=true"])
        check_env = checks.check_env
        def with_custom(*args, **kwargs):
            return dict(check_env(*args, **kwargs), PYTHONPATH=str(custom), PYTHONDONTWRITEBYTECODE="1")
        with mock.patch.object(checks, "check_env", side_effect=with_custom):
            code, _, err = self.conduct("run", "--input", path, "--json-lines")
        self.assertEqual(code, 0, err)
        self.assertEqual(candidate.read_text(), before)

    def test_guard_failure_never_starts_command(self):
        marker = self.project.parent / "started"
        _, path = self.review_with_acceptance(checks=[f"V1=touch {marker}"])
        with mock.patch.object(checks, "ORCH_ROOT", self.project.parent / "missing"):
            code, _, err = self.conduct("run", "--input", path, "--json-lines")
        self.assertNotEqual(code, 0)
        self.assertIn("CHECKS_FAILED", err)
        self.assertFalse(marker.exists())

    def test_metadata_guard_unavailable_fails_closed(self):
        marker = self.project.parent / "metadata-started"
        script = checks.ORCH_ROOT / "scripts" / "ro-run.py"
        bootstrap = ("import platform, runpy, sys; platform.machine = lambda: 'unsupported'; "
                     f"sys.argv = [{str(script)!r}, '--metadata-guard', '--no-default-rw', "
                     f"'--protect', {str(self.project)!r}, '--', 'touch', {str(marker)!r}]; "
                     f"runpy.run_path({str(script)!r}, run_name='__main__')")
        result = subprocess.run([sys.executable, "-I", "-c", bootstrap], capture_output=True, text=True)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("METADATA_GUARD_UNAVAILABLE", result.stderr)
        self.assertFalse(marker.exists())

    def test_idle_timeout_rejects_hung_check(self):
        _, path = self.review_with_acceptance(checks=["V1=sleep 30"])
        options = self.project.parent / "idle.json"
        options.write_text(json.dumps({"limits": {"check_timeout_s": 0, "check_idle_timeout_s": 1}}))
        code, _, err = self.conduct("run", "--input", path, "--options", options, "--json-lines")
        self.assertNotEqual(code, 0, err)
        self.assertIn("REGISTER_EVIDENCE_RED", err)
        evidence = list((self.project / ".swissknifeman" / "orch-artifacts").rglob("evidence/V1.json"))
        self.assertTrue(evidence)
        self.assertEqual(json.loads(evidence[0].read_text())["exit"], 124)

    def test_named_revision_with_dirty_checkout_cannot_prove_command(self):
        base = self.git("rev-parse", "HEAD").strip()
        (self.project / "README.md").write_text("committed\n")
        self.git("add", "README.md")
        self.git("commit", "-qm", "candidate")
        (self.project / "README.md").write_text("different\n")
        doc = adhoc.build_adhoc_input(None, [], review=base + "..HEAD", checks=["V1=true"])
        path = self.project.parent / "review-revision.json"
        path.write_text(json.dumps(doc))
        self.script({"reviewer": [GREEN], "triager": [{"result": {"confirmed": [], "rejected": []}}]})
        code, _, err = self.conduct("run", "--input", path, "--json-lines")
        self.assertNotEqual(code, 0)
        self.assertIn("CHECKS_CANDIDATE_MISMATCH", err)

    def test_dirty_worktree_is_reviewed_without_executor_checks_advisor_or_commit(self):
        base = self.git("rev-parse", "HEAD").strip()
        (self.project / "README.md").write_text("candidate\n")
        (self.project / "new.py").write_text("new\n")
        doc = adhoc.build_adhoc_input(None, [], review=base + "..WORKTREE", plan="T", item="W1")
        path = self.project.parent / "review.json"
        path.write_text(json.dumps(doc))
        findings = copy.deepcopy(FINDING["result"])
        findings["findings"][0]["location"] = "README.md:1"
        stream = "RAW_REVIEW_STREAM_" * 131072
        self.script({"reviewer": [{"result": findings, "stream": [stream]}], "triager": [{"result": {
            "confirmed": [{"finding": "F1", "reproduction": {"cmd": "test candidate", "exit": 1,
            "observed": "bad candidate"}, "fix": "repair"}], "rejected": []}}]})
        code, out, err = self.conduct("run", "--input", path, "--commit", "--json-lines")
        self.assertEqual((0, ("finished", None)), (code, self.outcome(err)), err)
        result = json.loads(out.splitlines()[-1])
        self.assertEqual(set(result), {"run", "receipt", "verdict", "open", "findings"})
        self.assertEqual([], contract.problems(result, "review-summary"))
        self.assertTrue(contract.problems(dict(result, stream="forbidden"), "review-summary"))
        receipt = json.loads((self.project / result["receipt"]).read_text())
        self.assertEqual(receipt["subject"], "T.W1")
        self.assertEqual(receipt["base"], base)
        self.assertEqual(set(receipt["candidate"]["paths"]), {"README.md", "new.py"})
        self.assertEqual(receipt["open"], {"blocker": 0, "major": 1})
        self.assertEqual(result["findings"][0]["id"], "F1")
        state = records.read(self.run_dir(err) / "state.json", "state")
        steps = state["items"][doc["input_id"]]["steps"]
        self.assertIn("review.1", steps)
        self.assertIn("triage.1", steps)
        self.assertIn("register", steps)
        self.assertFalse(any(name.startswith(("executor", "checks", "scout", "research", "advice", "commit"))
                             for name in steps))
        self.assertEqual(self.calls("executor"), 0)
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), base)
        self.assertNotIn("RAW_REVIEW_STREAM_", out)
        self.assertLess(len(out), 2000)
        self.assertTrue(list(self.run_dir(err).glob("*/streams/review.1.jsonl")))

    def test_clean_review_has_input_subject_and_still_triages_once(self):
        doc = adhoc.build_adhoc_input(None, [], review="HEAD..WORKTREE")
        path = self.project.parent / "review.json"
        path.write_text(json.dumps(doc))
        self.script({"reviewer": [GREEN], "triager": [{"result": {"confirmed": [], "rejected": []}}]})
        code, out, err = self.conduct("run", "--input", path, "--json-lines")
        self.assertEqual(code, 0, err)
        receipt = json.loads((self.project / json.loads(out.splitlines()[-1])["receipt"]).read_text())
        self.assertEqual(receipt["subject"], doc["input_id"])
        self.assertEqual(self.calls("triager"), 1)

    def test_equal_normalized_keys_do_not_hide_a_blocker_in_the_receipt(self):
        doc = adhoc.build_adhoc_input(None, [], review="HEAD..WORKTREE")
        path = self.project.parent / "review-collisions.json"
        path.write_text(json.dumps(doc))
        finding = dict(FINDING["result"]["findings"][0], location="README.md:1", severity="Blocker")
        other = dict(finding, id="F2", severity="Major")
        self.script({"reviewer": [{"result": {"verdict": "RED", "findings": [finding, other]}}],
                     "triager": [{"result": {"confirmed": [{"finding": row["id"],
                         "reproduction": {"cmd": "test case", "exit": 1, "observed": "failure"}, "fix": "repair"}
                         for row in (finding, other)], "rejected": []}}]})
        code, out, err = self.conduct("run", "--input", path, "--json-lines")
        self.assertEqual(code, 0, err)
        result = json.loads(out.splitlines()[-1])
        self.assertEqual({"blocker": 1, "major": 1}, result["open"])
        self.assertEqual(["F1", "F2"], [row["id"] for row in result["findings"]])

    def test_named_head_reviews_committed_blobs_instead_of_dirty_worktree(self):
        base = self.git("rev-parse", "HEAD").strip()
        (self.project / "README.md").write_text("committed candidate\n")
        self.git("add", "README.md")
        self.git("commit", "-qm", "candidate")
        head = self.git("rev-parse", "HEAD").strip()
        blob = self.git("rev-parse", "HEAD:README.md").strip()
        (self.project / "README.md").write_text("different uncommitted content\n")
        doc = adhoc.build_adhoc_input(None, [], review=base + "..HEAD")
        path = self.project.parent / "review-head.json"
        path.write_text(json.dumps(doc))
        self.script({"reviewer": [GREEN], "triager": [{"result": {"confirmed": [], "rejected": []}}]})
        code, out, err = self.conduct("run", "--input", path, "--json-lines")
        self.assertEqual(code, 0, err)
        receipt = json.loads((self.project / json.loads(out.splitlines()[-1])["receipt"]).read_text())
        self.assertEqual(receipt["candidate"]["paths"], {"README.md": "100644 " + blob})
        self.assertEqual(receipt["candidate"]["head"], head)
        prompt = self.prompt("reviewer", 1)
        self.assertIn("+committed candidate", prompt)
        self.assertNotIn("+different uncommitted content", prompt)
