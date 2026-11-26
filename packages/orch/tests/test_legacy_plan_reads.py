"""File inputs can name legacy Markdown reads without becoming native Planner inputs."""
import json
import sys

from orch import render
from tests.test_conductor import FIXTURES, GREEN, ROLES
from tests.test_conductor_input import InputCase


class LegacyMarkdownReadsTests(InputCase):
    def legacy_input(self):
        workspace = self.project.parent / "workspace/plans/legacy"
        workspace.mkdir(parents=True)
        (workspace / "remaining.md").write_text("Authoritative legacy requirement\n")
        (self.project / "plans").symlink_to(workspace.parent, target_is_directory=True)
        self.git("add", "plans")
        self.git("commit", "-qm", "legacy plans link")
        return self.write_input(reads=["plans/legacy/remaining.md"], exclude=["plans/**"]), workspace

    def test_explicit_legacy_markdown_reads_are_authorized_without_native_plan_access(self):
        path, workspace = self.legacy_input()
        doc = json.loads(path.read_text())
        before = path.read_bytes(), (workspace / "remaining.md").read_bytes()
        for role in ("context-scout", "executor"):
            with self.subTest(role=role):
                manifest, text = render.load_role(role)
                prompt = render.render_prompt(doc, manifest, text)
                self.assertIn("explicitly named legacy Markdown", prompt)
                self.assertIn("without `plan.json`", prompt)
                self.assertIn("existing plans symlink", prompt)
                self.assertIn("Native plan source JSON and generated views stay API-only", prompt)
                self.assertIn("plans/legacy/remaining.md", prompt)
                self.assertNotIn("Do not read or\nedit plan files", prompt)
                self.assertNotIn("Read or edit plan source files", prompt)
                self.assertEqual(manifest["tools"]["plan_api"], "none")
        self.assertEqual(doc["provenance"]["kind"], "adhoc")
        self.assertEqual(doc["result_contract"]["plan_mutation"], "forbidden")
        self.assertEqual((path.read_bytes(), (workspace / "remaining.md").read_bytes()), before)

    def test_same_file_input_reopens_a_blocked_attempt_and_preserves_its_history(self):
        path, workspace = self.legacy_input()
        before = path.read_bytes(), (workspace / "remaining.md").read_bytes()
        role = self.project.parent / "read_legacy.py"
        role.write_text("""import json,os,sys
from pathlib import Path
prompt=sys.stdin.read()
counter=Path(os.environ['FAKE_ROLE_STATE'])/'executor.count'
n=int(counter.read_text())+1 if counter.exists() else 1
counter.write_text(str(n))
if n==1:
 report={'status':'blocked','summary':'legacy required context unread','changed_paths':[],
         'checks_run':[],'evidence':[],'open_issues':[{'kind':'escalation','escalation_class':'environment',
         'text':'Required Markdown context was not read','impact':'Cannot implement the selected requirement',
         'next':'Resolve read access and resume this same run'}]}
else:
 assert 'explicitly named legacy Markdown' in prompt
 assert 'Native plan source JSON and generated views stay API-only' in prompt
 content=Path('plans/legacy/remaining.md').read_text()
 Path('out').mkdir(exist_ok=True)
 Path('out/adhoc.txt').write_text(content)
 report={'status':'done','summary':'implemented explicit legacy requirement','changed_paths':['out/adhoc.txt'],
         'checks_run':[],'evidence':[],'open_issues':[]}
text='```stage-report\\n'+json.dumps(report)+'\\n```'
print(json.dumps({'type':'system','subtype':'init','session_id':'legacy-'+str(n),'model':'fake-model'}))
print(json.dumps({'type':'result','result':text,'usage':{'input_tokens':100,'output_tokens':10}}))
""")
        argv = {name: [sys.executable, str(FIXTURES / "fake_role.py"), name] for name in ROLES}
        argv["executor"] = [sys.executable, str(role)]
        self.write_config(argv=argv)
        self.script({"reviewer": [GREEN]})
        code, _, error = self.run_input(path)
        self.assertEqual((code, self.outcome(error)), (1, ("stopped", "ITEM_BLOCKED")), error)
        self.assertIn("ENVIRONMENT_BLOCKED", error)
        directory = self.run_dir(error)
        ref = self.input_doc["input_id"]
        first = json.loads((directory / "state.json").read_text())
        self.assertEqual(first["items"][ref]["outcome"], "blocked")
        code, _, error = self.conduct("resume", "--run", directory.name, "--retry", ref, "--json-lines")
        self.assertEqual((code, self.outcome(error)), (0, ("finished", None)), error)
        state = json.loads((directory / "state.json").read_text())
        item = state["items"][ref]
        self.assertEqual(state["resumes"], 1)
        self.assertEqual(item["outcome"], "done")
        self.assertEqual(len(item["attempts"]), 1)
        archived = item["attempts"][0]["steps"]["executor.1"]
        self.assertEqual(archived["report_status"], "blocked")
        prior_report = next(directory.glob("*/attempts/1/reports/executor.1.json"))
        self.assertEqual(json.loads(prior_report.read_text())["status"], "blocked")
        self.assertEqual((self.project / "out/adhoc.txt").read_text(), "Authoritative legacy requirement\n")
        self.assertEqual((path.read_bytes(), (workspace / "remaining.md").read_bytes()), before)
        self.assertFalse((workspace / "plan.json").exists())
        self.assertEqual(self.source()["calls"], [])
