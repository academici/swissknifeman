#!/usr/bin/env bash
# dev-worktree.sh — develop a large plan while the main checkout runs stable tools.
#
# Usage:
#   scripts/dev-worktree.sh create [--path DIR] [--branch NAME] [--from REF]
#   scripts/dev-worktree.sh status [--path DIR] [--json]
#   scripts/dev-worktree.sh bind [--path DIR]
#   scripts/dev-worktree.sh unbind [--path DIR]
#   scripts/dev-worktree.sh promote-check --branch NAME [--path DIR]
#
# DIR defaults to swissknifeman-next beside the main worktree; create defaults to
# branch stable/p1 from main. bind/unbind atomically include both checkouts, preserving all
# bound paths, and make DIR/the main checkout primary. SKM_DEV_WORKTREE_WORKSPACE_CLI is for tests.
# promote-check prints the owner's promotion commands after checking live main, ancestry and cleanliness.
# This script never merges, pushes, resets, cleans or removes a worktree.
# Exit: 0 ok, 1 refused (DEV_WORKTREE_*: message), 2 usage.
set -euo pipefail

help_text() { sed -n '2,/^set -euo pipefail$/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; }
usage() { help_text >&2; exit 2; }
refuse() { printf '%s: %s\n' "$1" "$2" >&2; exit 1; }

[ $# -gt 0 ] || usage
CMD="$1"; shift
case "$CMD" in
  -h|--help|help) [ $# -eq 0 ] || usage; help_text; exit 0 ;;
  create|status|bind|unbind|promote-check) ;;
  *) usage ;;
esac

DIR="" BRANCH="" FROM="main" JSON=0
while [ $# -gt 0 ]; do
  case "$1" in
    --path) [ $# -ge 2 ] && [ -n "$2" ] || usage; DIR="$2"; shift 2 ;;
    --branch)
      [ "$CMD" = create ] || [ "$CMD" = promote-check ] || usage
      [ $# -ge 2 ] && [ -n "$2" ] || usage; BRANCH="$2"; shift 2 ;;
    --from)
      [ "$CMD" = create ] && [ $# -ge 2 ] && [ -n "$2" ] || usage
      FROM="$2"; shift 2 ;;
    --json) [ "$CMD" = status ] || usage; JSON=1; shift ;;
    *) usage ;;
  esac
done
[ "$CMD" != promote-check ] || [ -n "$BRANCH" ] || usage

# The first porcelain record is the main worktree, even when invoked in a linked worktree.
LIVE="$(git worktree list --porcelain | sed -n '1s/^worktree //p')"
[ -n "$LIVE" ] || usage
DIR="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "${DIR:-$(dirname "$LIVE")/swissknifeman-next}")"
SCRIPT_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"

# Preserve an executable path with spaces, or split a test command prefix into argv.
if [ -n "${SKM_DEV_WORKTREE_WORKSPACE_CLI:-}" ] && [ -x "$SKM_DEV_WORKTREE_WORKSPACE_CLI" ]; then
  WS=("$SKM_DEV_WORKTREE_WORKSPACE_CLI")
else
  read -r -a WS <<< "${SKM_DEV_WORKTREE_WORKSPACE_CLI:-swissknifeman workspace}"
fi

# JSON boundaries use the foundation validator. The two small script-owned schemas stay
# here with their sole reader/writer; the project marker uses its existing aicore contract.
json_tool() {
  python3 -c '
import json, os, subprocess, sys
sys.path.insert(0, os.path.join(sys.argv[1], "packages", "aicore", "lib"))
from aicore.util import schema
from aicore.workspace import WorkspaceError, read_marker

def validate(kind, document, properties, required, extra=False):
    prefix = "urn:swissknifeman:workspace:dev-worktree-"
    schema_id = prefix + kind + ":v1"
    contract = {"$id": schema_id, "type": "object", "properties": properties,
                "required": required, "additionalProperties": extra}
    registry = schema.Registry({schema_id: contract}, urn_prefix=prefix, kinds=(kind,))
    issues = schema.validate(document, kind, registry)
    if issues:
        raise ValueError(str(issues[0]))

try:
    mode, directory = sys.argv[2:4]
    marker = read_marker(directory)
    if marker is None:
        raise ValueError("missing .swissknifeman/project.json in " + directory)
    if mode == "project":
        print(marker["project_id"])
    elif mode == "workspace":
        print(marker["workspace"])
    else:
        def git(*args):
            return subprocess.check_output(["git", "-C", directory, *args]).decode().strip()
        ahead, behind = map(int, git("rev-list", "--left-right", "--count", "HEAD...main").split())
        changed = subprocess.check_output(["git", "-C", directory, "status", "--porcelain", "-z",
                                           "--untracked-files=no"]).split(b"\0")
        # A rename/copy contributes two NUL fields but only one changed entry.
        count, index = 0, 0
        while index < len(changed) and changed[index]:
            count += 1
            index += 2 if b"R" in changed[index][:2] or b"C" in changed[index][:2] else 1
        untracked = subprocess.check_output(["git", "-C", directory, "ls-files", "--others",
                                             "--exclude-standard", "-z"]).split(b"\0")
        env = dict(os.environ, SKM_WORKSPACE=marker["workspace"])
        try:
            result = subprocess.run([*sys.argv[5:], "project", "show", marker["project_id"], "--json"],
                                    cwd=directory, env=env, capture_output=True, text=True)
        except OSError as exc:
            result = subprocess.CompletedProcess([], 127, "", "WORKSPACE_CLI_UNAVAILABLE: " + str(exc))
        primary, code = None, str(result.returncode)
        if result.returncode == 0:
            try:
                answer = json.loads(result.stdout)
                validate("binding-answer", answer, {"binding": {"type": ["object", "null"],
                         "properties": {"primary": {"type": "string"}},
                         "required": ["primary"], "additionalProperties": True}}, [], True)
                primary = (answer.get("binding") or {}).get("primary")
            except (ValueError, TypeError):
                code = "invalid JSON"
        else:
            last = result.stderr.strip().splitlines()
            if last and ":" in last[-1]:
                code = last[-1].split(":", 1)[0]
        bound = primary is not None and os.path.realpath(primary) == directory
        document = dict(path=directory, branch=git("rev-parse", "--abbrev-ref", "HEAD"), head=git("rev-parse", "HEAD"),
                        ahead=ahead, behind=behind, changed=count, untracked=len([p for p in untracked if p]),
                        project=marker["workspace"] + "/" + marker["project_id"], primary=primary, bound=bound)
        properties = {key: {"type": "string"} for key in ("path", "branch", "head", "project")}
        properties.update({key: {"type": "integer", "minimum": 0} for key in ("ahead", "behind", "changed", "untracked")})
        properties.update(primary={"type": ["string", "null"]}, bound={"type": "boolean"})
        validate("status", document, properties, list(properties))
        if sys.argv[4] == "1":
            print(json.dumps(document))
        else:
            for key in ("path", "branch", "head"):
                print(key + ": " + document[key])
            print("vs main: ahead %s / behind %s" % (ahead, behind))
            for key in ("changed", "untracked", "project"):
                print(key + ": " + str(document[key]))
            print("binding primary: " + (primary or "unknown (" + code + ")"))
            print("bound to worktree: " + ("yes" if bound else "no"))
except (OSError, ValueError, WorkspaceError, subprocess.CalledProcessError) as exc:
    print(str(exc), file=sys.stderr)
    sys.exit(1)
' "$SCRIPT_ROOT" "$@"
}

workspace_run() {
  local output
  if ! output="$(cd "$DIR" && SKM_WORKSPACE="$WORKSPACE_CODE" "${WS[@]}" "$@" 2>&1)"; then
    refuse DEV_WORKTREE_BIND_FAILED "${output##*$'\n'}"
  fi
}

case "$CMD" in
  create)
    BRANCH="${BRANCH:-stable/p1}"
    [ ! -e "$DIR" ] && [ ! -L "$DIR" ] || refuse DEV_WORKTREE_EXISTS "$DIR exists"
    if git -C "$LIVE" show-ref --verify --quiet "refs/heads/$BRANCH"; then
      refuse DEV_WORKTREE_BRANCH_EXISTS "$BRANCH"
    fi
    git -C "$LIVE" worktree add "$DIR" -b "$BRANCH" "$FROM"
    printf 'Next steps:\n  %q bind --path %q\n' "${BASH_SOURCE[0]}" "$DIR"
    printf '  cd %q && python3 -I .swissknifeman/launcher.py orch conduct --project %q run --plan <PLAN> --items <ITEM>\n' "$DIR" "$DIR"
    ;;
  status)
    if ! output="$(json_tool status "$DIR" "$JSON" "${WS[@]}" 2>&1)"; then
      refuse DEV_WORKTREE_BIND_FAILED "${output##*$'\n'}"
    fi
    printf '%s\n' "$output"
    ;;
  bind|unbind)
    if ! PROJECT_ID="$(json_tool project "$DIR" 2>&1)"; then
      refuse DEV_WORKTREE_BIND_FAILED "${PROJECT_ID##*$'\n'}"
    fi
    WORKSPACE_CODE="$(json_tool workspace "$DIR")"
    if [ "$CMD" = bind ]; then
      workspace_run project rebind "$PROJECT_ID" --path "$DIR" --preserve-paths --include-path "$LIVE" --json
    else
      workspace_run project rebind "$PROJECT_ID" --path "$LIVE" --preserve-paths --include-path "$DIR" --json
    fi
    ;;
  promote-check)
    live_branch="$(git -C "$LIVE" symbolic-ref --quiet HEAD)" || refuse DEV_WORKTREE_LIVE_NOT_MAIN "$LIVE must be on main (detached HEAD)"
    [ "$live_branch" = refs/heads/main ] || refuse DEV_WORKTREE_LIVE_NOT_MAIN "$LIVE must be on main (on $live_branch)"
    git -C "$LIVE" show-ref --verify --quiet "refs/heads/$BRANCH" || refuse DEV_WORKTREE_NO_BRANCH "$BRANCH"
    git -C "$LIVE" merge-base --is-ancestor main "$BRANCH" || refuse DEV_WORKTREE_NOT_FF "$BRANCH is not a fast-forward of main"
    dirty="$(git -C "$LIVE" status --porcelain --untracked-files=no)"
    [ -z "$dirty" ] || refuse DEV_WORKTREE_LIVE_DIRTY "$dirty"
    if ! dirty="$(git -C "$DIR" status --porcelain 2>&1)"; then
      refuse DEV_WORKTREE_DIRTY "$dirty"
    fi
    [ -z "$dirty" ] || refuse DEV_WORKTREE_DIRTY "$dirty"
    # Recheck the branch when the operator runs the printed command.
    printf '[ "$(git -C %q symbolic-ref --quiet HEAD)" = refs/heads/main ] && git -C %q merge --ff-only %q\nswissknifeman doctor\n' "$LIVE" "$LIVE" "$BRANCH"
    ;;
esac
