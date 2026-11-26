#!/usr/bin/env bash
# test-bootstrap-machine.sh — smoke-tests scripts/bootstrap-machine.sh + route
# `swissknifeman setup --machine`. Does not raise demons/does not touch the real one ~/.claude —
# everything is done with isolated HOME=$(mktemp -d) (Code Guidance P7.1: wedge-HOME smoke).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/bootstrap-machine.sh"
SWISSKNIFEMAN="$REPO_ROOT/bin/swissknifeman"

# Dev clone (PLAN3 D13): every call below that has no explicit HOME= runs in a throwaway HOME.
GUARD_HOME="$(mktemp -d)"
trap 'rm -rf "$GUARD_HOME"' EXIT
export HOME="$GUARD_HOME"

fail=0
ok() { echo "ok - $1"; }
bad() { echo "NOT OK - $1"; fail=1; }

# 1) bash -n
bash -n "$SCRIPT" && ok "bash -n scripts/bootstrap-machine.sh" || bad "bash -n scripts/bootstrap-machine.sh"

# 2) --help comes out 0 and prints usage
if out="$("$SCRIPT" --help 2>&1)"; then
  [[ "$out" == *"bootstrap-machine.sh"* ]] && ok "--help prints usage" || bad "--help: no mention of script in output"
else
  bad "--help returned non-zero rc"
fi

# 3) unknown flag - error (rc != 0)
if "$SCRIPT" --bogus-flag >/tmp/bogus.out 2>&1; then
  bad "unknown flag --bogus-flag should fail"
else
  ok "unknown flag --bogus-flag fails with error"
fi

# 4) --dry-run in isolated HOME does not write ANYTHING to disk (no files, no directories).
#    Post-review fix: apply-permissions.sh did `mkdir -p .../auto-approve` BEFORE
#    checks DRY_RUN — fixed (mkdir moved inside `if [[ DRY_RUN -eq 0 ]]`),
#    so here we consider ANY record (-mindepth 1, without -type f).
TMP_HOME="$(mktemp -d)"
LOCAL_HOME=""
trap 'rm -rf "$GUARD_HOME" "$TMP_HOME" "${LOCAL_HOME:-}"' EXIT
before_all="$(find "$TMP_HOME" -mindepth 1 2>/dev/null | sort)"
HOME="$TMP_HOME" "$SCRIPT" --dry-run --bin-dir "$TMP_HOME/.local/bin" >/tmp/dry.out 2>&1 || true
after_all="$(find "$TMP_HOME" -mindepth 1 2>/dev/null | sort)"
if [[ "$before_all" == "$after_all" ]]; then
  ok "--dry-run does not create files in isolated HOME"
else
  bad "--dry-run created records in isolated HOME (diff): $(diff <(echo "$before_all") <(echo "$after_all") || true)"
fi
grep -q "install.sh" /tmp/dry.out && ok "--dry-run prints the plan install.sh" || bad "--dry-run: plan install.sh not found in output"
grep -q "MCP-presets" /tmp/dry.out && ok "--dry-run prints step MCP-presets" || bad "--dry-run: stage MCP-presets not found in output"

# 5) --skip-projects accepted (not an error) in dry-run mode
if HOME="$TMP_HOME" "$SCRIPT" --dry-run --skip-projects --bin-dir "$TMP_HOME/.local/bin" >/tmp/skip.out 2>&1; then
  grep -q -- "--skip-projects accepted" /tmp/skip.out && ok "--skip-projects is accepted and marked in the output" || bad "--skip-projects: note not found in output"
else
  bad "--dry-run --skip-projects failed"
fi

# 6) route `swissknifeman setup --machine --dry-run` delegates to bootstrap-machine.sh
if out="$(HOME="$TMP_HOME" "$SWISSKNIFEMAN" setup --machine --dry-run --bin-dir "$TMP_HOME/.local/bin" 2>&1)"; then
  echo "$out" | grep -q "bootstrap-machine" && ok "swissknifeman setup --machine delegates to bootstrap-machine.sh" || bad "swissknifeman setup --machine: no signs of delegation"
else
  bad "swissknifeman setup --machine --dry-run failed"
fi

# 7) `swissknifeman setup <project>` (without --machine) remains a route to maind onboard —
#    check that this is NOT routed to bootstrap-machine.sh (rc not important: no positional
#    project'a maind onboard itself fails with an error usage — this is his normal behavior, not ours).
out="$("$SWISSKNIFEMAN" setup --help 2>&1 || true)"
if echo "$out" | grep -q "bootstrap-machine"; then
  bad "setup --help mentions bootstrap-machine — route without --machine confused"
elif echo "$out" | grep -qi "onboard"; then
  ok "setup without --machine routed to maind onboard, not on bootstrap-machine.sh"
else
  bad "setup --help: output does not look like maind onboard usage, neither bootstrap-machine ($out)"
fi

# 8) --projects: invalid manifest (no required field path) — the level is clearly falling.
BAD_HOME="$(mktemp -d)"
BAD_MANIFEST="$BAD_HOME/manifest.json"
cat > "$BAD_MANIFEST" <<'EOF'
{"version": 1, "projects": [{"repo": "https://example.invalid/repo.git"}]}
EOF
if HOME="$BAD_HOME" "$SCRIPT" --dry-run --projects "$BAD_MANIFEST" --bin-dir "$BAD_HOME/.local/bin" >/tmp/badmanifest.out 2>&1; then
  bad "invalid manifest (without path) should fail"
else
  grep -q "manifest is invalid" /tmp/badmanifest.out && ok "invalid manifest - an obvious error" || bad "invalid manifest: no diagnostics in output"
fi
rm -rf "$BAD_HOME"

# 9) --projects + --dry-run: plan prints git clone/setup, does not write anything to disk
#    (except for the manifesto we created ourselves).
PROJ_HOME="$(mktemp -d)"
GOOD_MANIFEST="$PROJ_HOME/manifest.json"
cat > "$GOOD_MANIFEST" <<EOF
{"version": 1, "projects": [{"repo": "https://example.invalid/repo.git", "path": "~/dest/example-repo", "profile": ""}]}
EOF
before_proj="$(find "$PROJ_HOME" -mindepth 1 2>/dev/null | sort)"
HOME="$PROJ_HOME" "$SCRIPT" --dry-run --projects "$GOOD_MANIFEST" --bin-dir "$PROJ_HOME/.local/bin" >/tmp/dryprojects.out 2>&1 || true
after_proj="$(find "$PROJ_HOME" -mindepth 1 2>/dev/null | sort)"
if [[ "$before_proj" == "$after_proj" ]]; then
  ok "--projects --dry-run does not write files (except the manifest generated by the test)"
else
  bad "--projects --dry-run created disk entries: $(diff <(echo "$before_proj") <(echo "$after_proj") || true)"
fi
grep -q "git clone https://example.invalid/repo.git" /tmp/dryprojects.out && ok "--projects --dry-run prints the plan git clone" || bad "--projects --dry-run: plan clone not found in output"
rm -rf "$PROJ_HOME"

# 10) --projects (real run, without network - local git-repository as fixture):
#     RUN1 clones missing repository; RUN2 (rerun) DOES NOT repeat
#     clone/pull — working copy is idempotent (Code Guidance P7.2: manifest-step is idempotent).
LOCAL_HOME="$(mktemp -d)"
SRC_REPO="$LOCAL_HOME/src-repo"
mkdir -p "$SRC_REPO"
git init -q "$SRC_REPO"
git -C "$SRC_REPO" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
LOCAL_MANIFEST="$LOCAL_HOME/manifest.json"
cat > "$LOCAL_MANIFEST" <<EOF
{"version": 1, "projects": [{"repo": "$SRC_REPO", "path": "~/dest/local-repo", "profile": ""}]}
EOF
HOME="$LOCAL_HOME" "$SCRIPT" --projects "$LOCAL_MANIFEST" --bin-dir "$LOCAL_HOME/.local/bin" >/tmp/run1.out 2>&1 || true
DEST_REPO="$LOCAL_HOME/dest/local-repo"
if [[ -d "$DEST_REPO/.git" ]]; then
  ok "--projects clones missing repository from manifest"
else
  bad "--projects: repository from manifest is not cloned ($DEST_REPO not found)"
fi
commits_after_run1="$(git -C "$DEST_REPO" log --oneline 2>/dev/null | wc -l | tr -d ' ')"
HOME="$LOCAL_HOME" "$SCRIPT" --projects "$LOCAL_MANIFEST" --bin-dir "$LOCAL_HOME/.local/bin" >/tmp/run2.out 2>&1 || true
commits_after_run2="$(git -C "$DEST_REPO" log --oneline 2>/dev/null | wc -l | tr -d ' ')"
grep -q "SKIP clone" /tmp/run2.out && ok "rerun --projects skips clone already cloned" || bad "rerun --projects: no SKIP clone in the output"
if [[ "$commits_after_run1" == "$commits_after_run2" ]]; then
  ok "rerun --projects does not change git-clone history (pull doesn't)"
else
  bad "rerun --projects changed git-clone history (would be pull) — commits: $commits_after_run1 -> $commits_after_run2"
fi

# 11) --skip-projects wins even given --projects (step clearly missed).
HOME="$LOCAL_HOME" "$SCRIPT" --dry-run --skip-projects --projects "$LOCAL_MANIFEST" --bin-dir "$LOCAL_HOME/.local/bin" >/tmp/skipwins.out 2>&1 || true
grep -q -- "--skip-projects accepted" /tmp/skipwins.out && ok "--skip-projects wins --projects (step skipped)" || bad "--skip-projects: manifest step was not explicitly skipped"

if (( fail == 0 )); then
  echo "test-bootstrap-machine: all checks are green"
else
  echo "test-bootstrap-machine: THERE ARE FAILED CHECKS" >&2
fi
exit "$fail"
