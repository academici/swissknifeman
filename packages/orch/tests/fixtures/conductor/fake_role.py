"""A fake provider CLI for the conductor tests: ``fake_role.py ROLE`` reads the prompt on stdin and answers from a script.

``$FAKE_ROLE_SCRIPT`` is a JSON file ``{role: [answer, …]}``; the n-th call of a role takes the n-th answer (the last
one repeats). An answer may hold ``result`` (a JSON document put into the result block of the role), ``text`` (the
whole answer), ``write`` (``{path: content}`` written below the working directory first), ``run_command`` (run the ``sh`` block of
the prompt, the way the registrar does) , ``exit`` and ``usage``.
Every call is counted and its prompt kept in ``$FAKE_ROLE_STATE/<role>-<n>.md``. The context-scout answers in plain
text (the text transport); the other roles print stream-json like claude-code.
"""
import json
import os
import sys
from pathlib import Path

TAGS = {"executor": "stage-report", "reviewer": "review-findings", "triager": "triage-result"}

role = sys.argv[1]
prompt = sys.stdin.read()
state = Path(os.environ["FAKE_ROLE_STATE"])
state.mkdir(parents=True, exist_ok=True)
counter = state / f"{role}.count"
number = int(counter.read_text()) + 1 if counter.exists() else 1
counter.write_text(str(number))
(state / f"{role}-{number}.md").write_text(prompt, encoding="utf-8")
answers = json.loads(Path(os.environ["FAKE_ROLE_SCRIPT"]).read_text(encoding="utf-8")).get(role) or [{}]
answer = answers[min(number, len(answers)) - 1]
if answer.get("sleep"):  # a slow role (the cancellation tests)
    import time
    time.sleep(float(answer["sleep"]))
for path, content in (answer.get("write") or {}).items():
    target = Path.cwd() / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
if answer.get("run_command"):  # the registrar: run the one command of the prompt, as a model would
    import re
    import shlex
    import subprocess
    block = re.search(r"```sh\n(.*?)\n```", prompt, re.S)
    done = subprocess.run(shlex.split(block.group(1)), capture_output=True, text=True, check=False)
    text = f"[orch] closing\n\n```json\n{done.stdout}\n```\n" + (
        "RECORDED" if done.returncode == 0 else f"REFUSED: {done.stderr.strip()}")
elif "text" in answer:
    text = answer["text"]
elif "result" in answer:
    text = f"[orch] work done\n\n```{TAGS.get(role, 'json')}\n{json.dumps(answer['result'])}\n```\n"
else:
    text = "a context map line — why it matters\nUnknowns:\n- none\n"
if role == "context-scout":
    sys.stdout.write(text)
else:
    usage = answer.get("usage", {"input_tokens": 100, "output_tokens": 10})
    print(json.dumps({"type": "system", "subtype": "init", "session_id": f"{role}-session-{number}",
                      "model": answer.get("model", "fake-model")}))
    print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": text,
                      "session_id": f"{role}-session-{number}", "usage": usage}))
sys.exit(answer.get("exit", 0))
