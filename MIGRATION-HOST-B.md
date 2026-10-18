# Machine B: join the portable workspace (PLAN6 P6.4)

Audience: an agent session on machine B, run by the owner. Execute the steps in order, stop on any `STOP`, report at the end.
Do not run anything outside this file. No `--force`, no `git push --force`, no `migrate cleanup` (that is P6.5, on machine A).

## Facts

- Workspace remote (private): `https://github.com/academici/swissknifeman-axioma-workspace`, branch `main`.
- Workspace plan data was moved there from `plans/` of 6 projects on machine A: billium, commerz, azguard, chatom, corex, swissknifeman.
- **vaulter is excluded**: do not attach, scan-bind, migrate or touch it. It stays on legacy `plans/`.
- Each migrated repo carries a committed marker `.swissknifeman/project.json` (`plans_store: workspace`). `.swissknifeman` is gitignored in most repos; the marker was added with `git add -f`, so `git pull` brings it.
- Branches carrying the marker commit: billium `plan1-json-migration` (origin), azguard `feat/1.0-final-hardening` (remote `mirror`), commerz/chatom/corex `main`, swissknifeman `main`.
- About 500 files with secret-like content stayed **local-only on A**. They are not in the workspace git, so they will not appear on B. This is expected.
- Plugin `workspace-planner` needs machine trust; setting it is the owner's action (agents may not edit machine config).

## 0. Preconditions (read-only)

```bash
git --version; python3 --version
git ls-remote https://github.com/academici/swissknifeman-axioma-workspace | head -2   # needs git credentials for the private repo
```
`STOP` if the remote is not readable: ask the owner to set up git credentials.

Find the checkouts on B (adapt `~/projects/packages` if different) and note which of the six exist:
```bash
for p in billium commerz azguard chatom corex swissknifeman; do ls -d ~/projects/packages/$p 2>/dev/null; done
```
Missing checkouts: ask the owner to clone them (see step 2), or skip that project and report it.

## 1. Update swissknifeman to the pushed main

```bash
cd <swissknifeman checkout>
git status --short            # STOP if there are local changes you did not make; report them
git fetch origin && git checkout main && git pull --ff-only
git log -1 --format=%h        # record
swissknifeman --version       # record; must match machine A (A runs main at or after e5c705f2e)
swissknifeman workspace --help | head -5   # must list clone/migrate/project
```
Use the repo launcher if the global `swissknifeman` is not installed: `python3 -I .swissknifeman/launcher.py <args>`.

## 2. Pull the project checkouts (markers arrive)

For each of the six (existing) checkouts:
```bash
git -C $p status --short      # STOP for that project if tracked local changes exist; report
git -C $p fetch --all
git -C $p branch --show-current
git -C $p pull --ff-only      # on the branch named in Facts
test -f $p/.swissknifeman/project.json && python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['plans_store'])" $p/.swissknifeman/project.json   # expect: workspace
```
- billium / azguard: switch to the branch from Facts first (`git checkout plan1-json-migration`, `git checkout feat/1.0-final-hardening` after `git fetch mirror`), then pull.
- If the branch is not available or the marker is missing: do not create one by hand; report and skip that project.

## 3. Choose the data root and clone the workspace

Default data root: `~/.local/share/swissknifeman/workspace`. Set it explicitly for every later command; the launcher otherwise sets `SKM_WORKSPACE_ROOT` to the module code root and the commands break (`WORKSPACE_PROJECT_MISSING`).

```bash
export SKM_WORKSPACE_ROOT=$HOME/.local/share/swissknifeman/workspace
test -e "$SKM_WORKSPACE_ROOT" && ls -A "$SKM_WORKSPACE_ROOT" | head   # STOP if it exists and is not empty: report, do not overwrite
swissknifeman workspace clone https://github.com/academici/swissknifeman-axioma-workspace --root "$SKM_WORKSPACE_ROOT" --json
swissknifeman workspace status --json     # git.dirty 0, behind 0
swissknifeman workspace doctor --json     # no fail
```
Keep `SKM_WORKSPACE_ROOT` exported in every following command (a new shell resets it).

## 4. Trust the planner plugin (OWNER step)

The plans-migrator plugin must be trusted on this machine. Ask the owner to run (the agent must not):
```bash
cd <swissknifeman checkout>
python3 -I .swissknifeman/launcher.py config set --machine aicore.plugins.workspace-planner.manifest "$PWD/bridges/workspace-planner/extension.json"
python3 -I .swissknifeman/launcher.py config set --machine aicore.plugins.workspace-planner.enabled true
python3 -I .swissknifeman/launcher.py config set --machine aicore.plugins.workspace-planner.trusted true
```
Wait for confirmation. Without it, `migrate` fails with `MIGRATOR_UNAVAILABLE` / plugin-not-trusted.

## 5. Bind checkouts to workspace projects

```bash
swissknifeman workspace project scan ~/projects/packages --json
swissknifeman workspace project list --json    # expect the existing ones of the six bound; no vaulter
```
Not bound but marker present: `workspace project rebind <project_id> --path <checkout>`.
A project that exists only on B (no marker): `workspace project attach --project DIR --yes` (creates a new project id), then continue with step 6 as usual. Report it.

## 6. Import dry run (writes nothing)

Artifacts go in `~/skm-b-report/` (create it; outside any repo).
```bash
mkdir -p ~/skm-b-report
for p in <existing checkouts>; do
  swissknifeman workspace migrate plan --project $p --json > ~/skm-b-report/b-migrate-plan-$(basename $p).json 2> ~/skm-b-report/b-migrate-plan-$(basename $p).err
done
```
Per project, summarize the plan classes (equal = skip, new-on-B = copy, differs = conflict). Do not print file contents or any secret-looking value.

- Local `plans/` on B absent or all `equal`: nothing to import, go to step 8.
- `new` only: go to step 7.
- Any conflict (a plan changed both on B and in the workspace): `STOP`, show the owner project, plan id, and both digests. Owner chooses `--on-conflict keep-workspace` or `import-copy`. Never choose it yourself; default apply refuses with `MIGRATION_CONFLICT`.
- `PS-SECRET` findings that block: report (rule, path only). Owner decides whether to use `--local-only-secrets` (keeps those files on B, not in git).
- Plans with status `in_progress`: do not use `--allow-in-progress` without the owner.

## 7. Import apply (only projects with new/copy items; per project, separately)

```bash
swissknifeman workspace migrate apply --project $p [--on-conflict <owner choice>] [--local-only-secrets if the owner allowed] --json > ~/skm-b-report/b-apply-$(basename $p).json
swissknifeman workspace migrate verify --project $p --json > ~/skm-b-report/b-verify-$(basename $p).json
```
Verify: every plan state `equal`. `STOP` otherwise.
Do not commit anything in the project repos in this step.

## 8. Publish what B added to the workspace

```bash
swissknifeman workspace doctor --publish-safety --json     # verdict must not be "block"
swissknifeman workspace sync --commit --pull --push --json
swissknifeman workspace status --fetch --json               # dirty 0, ahead 0, behind 0
```
Known harmless: `legacy-plans` doctor warn (legacy `plans/` still present until cleanup on A); publish-safety `warn` count in the thousands.
`REMOTE_FOREIGN` / `REMOTE_OTHER_WORKSPACE` / diverged: `STOP`.

## 9. Final checks on B

For each bound checkout:
```bash
cd $p && swissknifeman planner plans --output json > ~/skm-b-report/b-plans-$(basename $p).json
```
It must list the plans of that project (from the workspace; a `LEGACY_PLANS_PRESENT` warning is fine). Compare with machine A: same plan ids and statuses (the PLAN6 plan itself may be newer; ignore it).
```bash
swissknifeman workspace doctor --json > ~/skm-b-report/b-doctor.json     # no fail
```

## 10. Report back to the owner (short)

- swissknifeman commit and `--version` on B; workspace head (`git -C "$SKM_WORKSPACE_ROOT" rev-parse --short HEAD`).
- Per project: checkout found / branch / marker ok / plan classes / apply done / verify equal / planner plans count.
- Anything skipped or stopped, with the exact error code.
- Paths of the files in `~/skm-b-report/`. Do not paste secrets or file contents.

The owner then returns the report to the planner session on machine A to close P6.4 (gate MIGRATE-HOST-B) and run P6.5 (cleanup).

## Do not

- touch vaulter; run `migrate cleanup`; `git rm` anything in `plans/`; change machine config; use `--force`;
- delete or overwrite local `plans/` on B; resolve a conflict without the owner;
- commit in project repos; edit `.swissknifeman/project.json`.
