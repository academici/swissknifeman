"""A fake provider CLI for the conductor tests: ``fake_role.py ROLE`` reads the prompt on stdin and answers from a script.

``$FAKE_ROLE_SCRIPT`` is a JSON file ``{role: [answer, …]}``; the n-th call of a role takes the n-th answer (the last
one repeats). An answer may hold ``result`` (a JSON document put into the result block of the role), ``text`` (the
whole answer), ``tag`` (the tag of the result block, for the report-fixer), ``write`` (``{path: content}`` written below
the working directory first; an absolute path is written as it is), ``run_command`` (run the ``sh`` block of
the prompt, the way the registrar does) , ``exit`` and ``usage``. Failure shapes: ``stream`` (raw JSON lines printed before
the result, for example ``api_retry`` system events and ``rate_limit_event``; each is a document or a string), ``stderr`` (text on
stderr), ``is_error`` (the result is an error; its text is the answer text), ``api_error_status`` (put into the result),
``codex`` (print the event stream of codex instead of claude's) and ``codex_failed`` (a message: codex ``turn.failed``
instead of ``turn.completed``).
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
    tag = answer.get("tag") or TAGS.get(role, "json")
    text = f"[orch] work done\n\n```{tag}\n{json.dumps(answer['result'])}\n```\n"
else:
    text = "a context map line — why it matters\nUnknowns:\n- none\n"
if role == "context-scout":
    sys.stdout.write(text)
else:
    usage = answer.get("usage", {"input_tokens": 100, "output_tokens": 10})
    session = f"{role}-session-{number}"
    if answer.get("codex") or answer.get("codex_failed"):
        print(json.dumps({"type": "thread.started", "thread_id": session}))
    else:
        print(json.dumps({"type": "system", "subtype": "init", "session_id": session,
                          "model": answer.get("model", "fake-model")}))
    for line in answer.get("stream") or []:
        print(line if isinstance(line, str) else json.dumps(line))
    if answer.get("codex_failed"):
        print(json.dumps({"type": "turn.failed", "error": {"message": answer["codex_failed"]}}))
    elif answer.get("codex"):
        print(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": text}}))
        print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": usage.get("input_tokens", 0),
                                                              "output_tokens": usage.get("output_tokens", 0)}}))
    else:
        result = {"type": "result", "subtype": "success", "is_error": bool(answer.get("is_error")), "result": text,
                  "session_id": session, "usage": usage}
        if "api_error_status" in answer:
            result["api_error_status"] = answer["api_error_status"]
        print(json.dumps(result))
if answer.get("stderr"):
    sys.stderr.write(answer["stderr"])
sys.exit(answer.get("exit", 0))
