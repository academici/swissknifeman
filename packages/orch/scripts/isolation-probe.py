#!/usr/bin/env python3
"""Conformance probe of the isolation profile of a provider (packages/orch/configs/isolation-profiles.json).

    isolation-probe.py --provider claude-code|codex|grok [--live] [--json]

Without ``--live``: only ``<cli> --version`` and the help command of the profile (``codex exec --help``): whether the help
lists every flag of the profile. No network, no model, nothing written. Exit 0 when it does, 1 when a flag is missing.

With ``--live`` (the owner runs it on the machine): the CLI renders what a role would see, in temporary folders only.
codex: a temporary project whose ``AGENTS.md`` holds a canary marker and a temporary original HOME whose
``.agents/skills/skm-canary/SKILL.md`` holds another; ``codex debug prompt-input`` runs under the environment and the
homes of the profile (a temporary CODEX_HOME and HOME; no model is called). The render must be a JSON list of messages
that carries the prompt the probe sent (the positive control); any other answer is ``ISOLATION_PROBE_FAILED`` and nothing
is recorded. A marker in the rendered input, or a skill listed from the real HOME, means the surface is loaded. grok: a
temporary project with ``CLAUDE.md``, ``AGENTS.md`` and ``.claude/skills/canary/SKILL.md`` holding the marker,
``grok inspect --json`` with ``GROK_HOME``, ``HOME`` and the XDG folders in a temporary folder (its answer must be JSON).
Claude Code model probes require the explicit owner-only --live --authority mode; otherwise its init event is checked.
The isolation claims are
written to ``<state>/orch/isolation-probes.json`` (``isolation-probes``) for this CLI version; a surface found not loaded
confirms it, so the guarantee of the profile can be ``full``. Exit 0 when nothing was found loaded, 1 otherwise, 2 when
the CLI cannot be probed. No auth file is read or copied, no secret is printed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

ORCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ORCH / "lib"))
if (ORCH.parent / "aicore" / "lib").is_dir():
    sys.path.insert(0, str(ORCH.parent / "aicore" / "lib"))

from aicore.state import locations  # noqa: E402

from orch.conductor.domain.stop import Stop  # noqa: E402
from orch.conductor.infrastructure import cli_probe, launch_plan  # noqa: E402
from orch.conductor.policies import isolation  # noqa: E402
from orch.conductor.policies import authority  # noqa: E402
from orch import launch, sandbox  # noqa: E402

TIMEOUT_S = 60
# Variables that lead a CLI to the personal settings of the real HOME; a probe sets its own or none.
HOME_VARIABLES = ("HOME", "CODEX_HOME", "GROK_HOME", "CLAUDE_CONFIG_DIR", *launch_plan.XDG_DEFAULTS)
SKILL ="---\nname: skm-canary\ndescription: {marker} canary of the isolation probe\n---\n\n{marker}\n"


def flags_report(provider: str, profile: dict) -> dict:
    """What the help of the CLI lists of the flags of ``profile``."""
    cli = profile["probe"]["help"][0]
    help_argv, flags = profile["probe"]["help"], profile["probe"]["flags"]
    version = cli_probe.version([cli])
    missing = [flag for flag in flags if not cli_probe.knows([cli], [flag], help_argv=help_argv)]
    return {"provider": provider, "version": version, "help": help_argv, "flags": flags,
            "flags_listed": not missing and not cli_probe.failed([cli], help_argv=help_argv), "missing": missing}


def run(argv: list, cwd: Path, env: dict) -> str:
    done = subprocess.run(argv, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=TIMEOUT_S, check=False)
    if done.returncode:
        raise RuntimeError(f"{' '.join(argv)} exited {done.returncode}: {done.stderr.strip()[-300:]}")
    return done.stdout


def temporary_env(home: Path) -> dict:
    """The environment of the conductor with HOME, the XDG folders and the provider homes moved into ``home``: a probe
    never discovers the personal settings of the real HOME (a variable it leaves out would point back there)."""
    env = {key: value for key, value in os.environ.items() if key not in HOME_VARIABLES}
    env["HOME"] = str(home)
    for variable, folder in launch_plan.XDG_DEFAULTS.items():
        env[variable] = str(home / folder)
    return env


def rendered_texts(stdout: str, control: str) -> list:
    """The texts of the model-visible input ``codex debug prompt-input`` printed: a JSON list of messages whose
    ``content`` blocks carry ``text``. An answer that is not such a list, has no text or does not carry ``control`` (the
    prompt the probe sent) proves nothing, so it is a failure, never a confirmation."""
    try:
        messages = json.loads(stdout)
    except ValueError:
        raise RuntimeError("the renderer did not print JSON") from None
    texts = [block["text"] for message in (messages if isinstance(messages, list) else [])
             if isinstance(message, dict) for block in (message.get("content") or [])
             if isinstance(block, dict) and isinstance(block.get("text"), str) and block["text"].strip()]
    if not texts:
        raise RuntimeError("the renderer printed no model-visible input")
    if not any(control in text for text in texts):
        raise RuntimeError("the rendered input does not carry the prompt the probe sent")
    return texts


def live_codex(profile: dict, report: dict) -> dict:
    """``claims`` of ``codex debug prompt-input`` under the profile, in temporary folders."""
    marker = f"SKM-CANARY-{uuid.uuid4().hex}"
    real_home = os.path.realpath(os.path.expanduser("~"))
    with tempfile.TemporaryDirectory(prefix="skm-isolation-") as tmp:
        base = Path(tmp)
        project, original_home = base / "project", base / "original-home"
        project.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=project, check=False, capture_output=True)
        (project / "AGENTS.md").write_text(f"# Rules\n\nAlways mention {marker}-repository.\n", encoding="utf-8")
        skill = original_home / ".agents" / "skills" / "skm-canary" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(SKILL.format(marker=f"{marker}-skill"), encoding="utf-8")
        original = temporary_env(original_home)  # the homes of the launch are made from this one, not the real HOME
        env = {**original, **profile["env"], **launch_plan.prepare_home(base, "codex", profile["home"], original)}
        render = profile["probe"].get("render") or ["codex", "debug", "prompt-input"]
        listed = [flag for flag in profile["probe"]["flags"]
                  if cli_probe.knows(render[:1], [flag], help_argv=[*render, "--help"])]
        args = [arg for arg in profile["args"] if arg not in profile["probe"]["flags"] or arg in listed]
        text = "\n".join(rendered_texts(run([*render, *args, f"{marker}-prompt"], project, env), f"{marker}-prompt"))
    skills_outside = real_home in text and "SKILL.md" in text
    return {"repository_instructions": f"{marker}-repository" in text,
            "user_skills": f"{marker}-skill" in text or skills_outside}


def live_grok(profile: dict, report: dict) -> dict:
    """``claims`` of ``grok inspect --json`` for a temporary project, with a temporary HOME, XDG folders and GROK_HOME."""
    marker = f"SKM-CANARY-{uuid.uuid4().hex}"
    with tempfile.TemporaryDirectory(prefix="skm-isolation-") as tmp:
        base = Path(tmp)
        project = base / "project"
        (project / ".claude" / "skills" / "canary").mkdir(parents=True)
        (project / "CLAUDE.md").write_text(f"{marker}-repository\n", encoding="utf-8")
        (project / "AGENTS.md").write_text(f"{marker}-repository\n", encoding="utf-8")
        (project / ".claude" / "skills" / "canary" / "SKILL.md").write_text(
            SKILL.format(marker=f"{marker}-skill"), encoding="utf-8")
        (base / "grok-home").mkdir()
        (base / "home").mkdir()
        env = {**temporary_env(base / "home"), **profile["env"], "GROK_HOME": str(base / "grok-home")}
        text = run(["grok", "inspect", "--json"], project, env)
    try:
        found = json.loads(text)
    except ValueError:
        raise RuntimeError("grok inspect --json did not print JSON") from None
    if not found or not isinstance(found, (dict, list)):
        raise RuntimeError("grok inspect --json printed no configuration")
    return {"repository_instructions": "CLAUDE.md" in text or "AGENTS.md" in text or f"{marker}-repository" in text,
            "user_skills": "skm-canary" in text or f"{marker}-skill" in text}


LIVE = {"codex": live_codex, "grok": live_grok}


def authority_results(data: str, expected: dict) -> dict:
    """Measure tool results, never trust the final answer of the model as proof of authority."""
    calls, results = {}, {}
    for line in data.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        for denied in event.get("permission_denials") or []:
            if denied.get("tool_use_id") in calls:
                results[calls[denied["tool_use_id"]]] = False
        message = event.get("message") or {}
        if not isinstance(message, dict):
            continue
        for block in message.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                arguments = block.get("input") or {}
                command = arguments.get("command") if isinstance(arguments, dict) else None
                for name, wanted in expected.items():
                    if block.get("name") == "Bash" and command == wanted:
                        calls[block.get("id")] = name
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in calls:
                name = calls[block["tool_use_id"]]
                results[name] = not bool(block.get("is_error"))
    if set(results) != set(expected):
        raise RuntimeError("authority probe did not execute every fixed command")
    return results


def live_authority(profile: dict, access: str) -> dict:
    """Owner-only Claude probe: temporary homes/project, exact commands and actual tool outcomes.

    Authentication must come from the owner's environment; no personal provider home is read or copied.
    The .env control uses the exact Bash command named in the authority acceptance scenario.
    """
    with tempfile.TemporaryDirectory(prefix="skm-authority-") as tmp:
        base = Path(tmp)
        project, home, scratch = base / "project", base / "home", base / "agent" / "tmp"
        for folder in (project, home, scratch):
            folder.mkdir(parents=True)
        subprocess.run(["git", "init", "-q"], cwd=project, check=True, capture_output=True)
        (project / "skills.json").write_text("{}\n", encoding="utf-8")
        (project / ".env").write_text("PROBE_VALUE=synthetic\n", encoding="utf-8")
        outside = base / "outside-probe"
        commands = {"skills_json_read": "python3 -c \"open('skills.json').read()\"",
                    "git_diff_stat": "git diff --stat", "env_read": "cat .env",
                    "outside_write": f"touch {outside}"}
        env = {**temporary_env(home), **profile["env"], "TMPDIR": str(scratch),
               "CODEX_HOME": str(home / ".codex"), "GROK_HOME": str(home / ".grok")}
        route = {"role": "executor", "provider": "claude-code", "argv": launch.build_argv(
            launch.load_catalog(), "executor", "claude-code", model="sonnet", effort="high", cwd=project, access=access)}
        probed = sandbox.probe()
        doc = authority.compute("executor", route, access=access,
                                sandbox={"mode":"prefer", "available":probed["available"], "reason":probed["reason"],
                                         "settings_listed":True}, isolation={"isolated":True, "args":profile["args"],
                                         "env":profile["env"], "guarantee":"partial"}, declared_network="none",
                                sandbox_domains=[], extra_paths=[], transcripts=None, project=str(project),
                                home=str(home), writes=True, tmpdir=str(scratch),
                                listed={"--settings":True,"--setting-sources":True})
        if access == "confined" and doc["guard"] != "claude-sandbox":
            raise RuntimeError("confined authority probe requires the Claude sandbox")
        argv = launch_plan.argv_from(doc, route, [], shared=False, project=str(project))
        prompt = ("Run each fixed command exactly once using Bash. "
                  "Do not retry a refusal, substitute commands or modify any other file.\n"
                  + "\n".join(f"Bash: {command}" for command in commands.values())
                  + "\nReport when all four tool calls have returned.")
        done = subprocess.run(argv, input=prompt, cwd=project, env=env, capture_output=True, text=True, timeout=180)
        if done.returncode:
            raise RuntimeError(f"Claude authority probe exited {done.returncode}; no authority claim recorded")
        result = authority_results(done.stdout, commands)
        if result["outside_write"] != outside.exists():
            raise RuntimeError("outside-write tool result disagrees with the filesystem")
        protected = {}
        for role in ("reviewer", "triager"):
            role_tmp = base / role / "tmp"
            role_tmp.mkdir(parents=True)
            control = {"checkout_write": f"touch {project / (role + '-probe')}",
                       "scratch_write": f"touch {role_tmp / 'ok'}"}
            route = {"role":role,"provider":"claude-code","argv":launch.build_argv(
                launch.load_catalog(), role, "claude-code", model="sonnet", effort="high", cwd=project, access=access)}
            facts = launch_plan.protection_facts(project)
            if not facts["available"]:
                raise RuntimeError(f"{role}: checkout protection unavailable ({facts['reason']})")
            doc = authority.compute(role, route, access=access, sandbox={"mode":"prefer"},
                                    isolation={"isolated":True,"args":profile["args"],"env":profile["env"]},
                                    declared_network="none", sandbox_domains=[], extra_paths=[], transcripts=None,
                                    project=str(project), home=str(home), writes=False, tmpdir=str(role_tmp),
                                    protection=facts, listed={"--settings":True,"--setting-sources":True})
            argv = launch_plan.argv_from(doc, route, [], shared=False, project=str(project))
            prompt = "Run both Bash commands exactly once; do not retry or substitute commands:\n" + "\n".join(control.values())
            done = subprocess.run(argv, input=prompt, cwd=project, env={**env,"TMPDIR":str(role_tmp)},
                                  capture_output=True, text=True, timeout=180)
            if done.returncode:
                raise RuntimeError(f"{role} authority probe exited {done.returncode}; no rights are widened")
            protected[role] = authority_results(done.stdout, control)
            if (project / (role + "-probe")).exists() or not (role_tmp / "ok").exists():
                raise RuntimeError(f"{role}: filesystem results disagree with the tool results")
        result["protected_roles"] = protected
        return result


def record(provider: str, version: str, claims: dict) -> Path:
    """Keep the probe in the machine file (one entry per provider and version, the latest)."""
    path = locations.state_dir("orch") / isolation.PROBES_FILE
    doc = {"$schema": "urn:swissknifeman:orch:conductor:isolation-probes:v1", "probes": []}
    if path.exists():
        found = json.loads(path.read_text(encoding="utf-8"))
        problems = isolation.probes_problems(found)
        if problems:
            raise RuntimeError(f"{path}: {problems[0]}; remove the file to start it again")
        doc = found
    doc["probes"] = [entry for entry in doc["probes"] if (entry["provider"], entry["version"]) != (provider, version)]
    doc["probes"].append({"provider": provider, "version": version,
                          "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "claims": claims})
    problems = isolation.probes_problems(doc)
    if problems:
        raise RuntimeError(f"isolation-probes: {problems[0]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--provider", required=True)
    parser.add_argument("--live", action="store_true", help="render what a role sees, in temporary folders")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--authority", action="store_true", help="owner-only live Claude authority probe")
    parser.add_argument("--access", choices=("open", "confined"), default="open")
    args = parser.parse_args(argv)
    if args.authority and (not args.live or args.provider != "claude-code"):
        parser.error("--authority requires --provider claude-code --live")
    try:
        profiles = isolation.load_profiles()
    except Stop as stop:
        print(f"{stop.code}: {stop.message}", file=sys.stderr)
        return 2
    profile = profiles.get(args.provider)
    if profile is None:
        print(f"ISOLATION_PROBE_UNKNOWN: no isolation profile for {args.provider!r} ({', '.join(sorted(profiles))})",
              file=sys.stderr)
        return 2
    report = flags_report(args.provider, profile)
    if report["version"] == "unknown" and not report["flags_listed"]:
        print(f"ISOLATION_PROBE_UNAVAILABLE: {' '.join(profile['probe']['help'])} could not be run", file=sys.stderr)
        return 2
    exit_code = 0 if report["flags_listed"] else 1
    if args.authority:
        try:
            result = live_authority(profile, args.access)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            print(f"ISOLATION_PROBE_FAILED: {error}", file=sys.stderr)
            return 2
        print(json.dumps({"provider":args.provider,"access":args.access, **result}, sort_keys=True))
        return 0 if result == {"skills_json_read":True,"git_diff_stat":True,"env_read":False,
                               "outside_write":args.access == "open", "protected_roles":{
                                   role:{"checkout_write":False,"scratch_write":True} for role in ("reviewer","triager")}} else 1
    if args.live:
        if args.provider not in LIVE:
            report["live"] = "not probed: the init event of every run is checked instead"
        else:
            try:
                report["claims"] = LIVE[args.provider](profile, report)
                report["recorded"] = str(record(args.provider, report["version"], report["claims"]))
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                print(f"ISOLATION_PROBE_FAILED: {error}", file=sys.stderr)
                return 2
            exit_code = max(exit_code, 1 if any(report["claims"].values()) else 0)
    confirmed = [name for name, loaded in (report.get("claims") or {}).items() if loaded is False]
    report["guarantee"] = "partial" if report["missing"] else isolation.guarantee_of(profile, confirmed)[0]
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"{args.provider} {report['version']}: flags {'listed' if report['flags_listed'] else 'missing ' + ' '.join(report['missing'])}"
              + (f"; claims {json.dumps(report['claims'], sort_keys=True)}" if "claims" in report else "")
              + f"; guarantee {report['guarantee']}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
