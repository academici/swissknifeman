# Machine B: join the workspace `axioma` and merge the newer plans (PLAN6 P6.4, layout 2)

Audience: an agent session on machine B, started by the owner. Do the steps in order and stop at every `STOP`.
Never use `--force`, never `git push --force`, never delete a plan without a verified copy. Report at the end (step 10).

## What is true

- There is **one workspace, `axioma`**: the git repository `https://github.com/academici/swissknifeman-axioma-workspace`
  (private, branch `main`). On a machine it lives in `~/.local/share/swissknifeman/workspaces/axioma/`.
- It holds the plans of 8 projects, as `projects/<code>/plans/…`. The code of a project is the name of its checkout folder.
  Machine A moved the plans there and removed `plans/` from the repositories of the projects.
- **Machine B has newer plans** in the `plans/` folders of its checkouts. They must be merged into the workspace by hand, plan
  by plan, before anything of B is thrown away. After that the checkouts of B work only with the workspace.
- A checkout carries only a marker `.swissknifeman/project.json` (`{workspace, project_id, plans_store}`), committed with the
  project. B gets it with `git pull`, but **pull comes after the merge** (step 8): pulling earlier would delete the local `plans/`.
- About 600 files with secret-like content stayed on machine A (local-only). If B has such files in its plans, they stay on B too.

| code | checkout folder | remote to fetch | branch with the marker |
| --- | --- | --- | --- |
| billium | billium | origin | plan1-json-migration |
| commerz | commerz | origin | main |
| azguard | azguard | mirror | feat/1.0-final-hardening |
| chatom | chatom | origin | main |
| corex | corex | origin | main |
| sockit | sockit | origin | main |
| swissknifeman | swissknifeman | origin | main |
| vaulter | vaulter | origin | main |

A project that does not exist on B, or whose branch is not the one in the table: skip it, say so in the report.
Use `<P>` for the checkout, `<code>` for the code and `<remote>/<branch>` from the table below.

## 0. Preconditions (read-only)

```bash
git --version; python3 --version
git ls-remote https://github.com/academici/swissknifeman-axioma-workspace | head -2   # needs git credentials (private repo)
for p in billium commerz azguard chatom corex sockit swissknifeman vaulter; do d=~/projects/packages/$p; test -d $d && echo "have $d"; done
```
`STOP` if the remote is not readable: the owner sets up credentials. Adapt the base folder if the checkouts are elsewhere.
No conductor or planner run may be active in these projects (`ps aux | grep -E "conduct|plan.py"`): `STOP` if one is.

## 1. Back up everything that will be touched

```bash
B=~/skm-b-backup/$(date +%Y%m%d-%H%M)
mkdir -p $B
for p in <the checkouts that exist>; do
  d=~/projects/packages/$p
  test -d $d/plans && tar -C $d -czf $B/$p-plans.tgz plans
  git -C $d status --short > $B/$p-status.txt
  git -C $d log --oneline -20 > $B/$p-log.txt
  git -C $d branch --show-current >> $B/$p-log.txt
done
test -d ~/.local/share/swissknifeman && tar -C ~/.local/share -czf $B/skm-data.tgz swissknifeman
ls -la $B
```
Every archive must be non-empty (`tar -tzf … | head`). `STOP` otherwise. Nothing below deletes a file: things are moved into `$B`.

## 2. Update swissknifeman (the hub) and get the launcher

```bash
cd ~/projects/packages/swissknifeman
git status --short                  # tracked local changes in plans/ are expected; anything else: report
git fetch origin
git log --oneline HEAD..origin/main | head -3
```
The hub is also a project (code `swissknifeman`) and its own `plans/` is among B's newer plans, so **do not pull it yet**.
Run the new code from a separate checkout of the same commit instead:
```bash
git -C ~/projects/packages/swissknifeman worktree add ~/skm-hub-b origin/main      # or: git clone … ~/skm-hub-b
~/skm-hub-b/bin/swissknifeman --version
~/skm-hub-b/bin/swissknifeman workspace --help | head -12     # must list: init list clone project migrate sync
```
Below, `skm` means `~/skm-hub-b/bin/swissknifeman`. (Once the hub itself is finished in step 8, the normal checkout is used again.)

## 3. Trust the plans migrator (OWNER step)

The agent must not change machine config. Ask the owner to run:
```bash
skm config set --machine aicore.plugins.workspace-planner.manifest ~/skm-hub-b/bridges/workspace-planner/extension.json
skm config set --machine aicore.plugins.workspace-planner.enabled true
skm config set --machine aicore.plugins.workspace-planner.trusted true
```
Wait for the confirmation. (After step 8 the manifest path is changed to the real hub checkout.)

## 4. Clone the workspace

```bash
ls ~/.local/share/swissknifeman/workspaces 2>/dev/null            # must be empty or absent; else STOP and report
skm workspace clone https://github.com/academici/swissknifeman-axioma-workspace --json
skm workspace status --json          # code axioma, git.dirty 0, behind 0
skm workspace doctor                 # no [fail]
ls ~/.local/share/swissknifeman/workspaces/axioma/projects       # the 8 codes
```
There is only one workspace, so no `--workspace` is needed. (With several: `--workspace axioma` after any command.)

## 5. Per project: classify B's plans against the workspace (dry run, nothing written to the workspace)

For each checkout `<P>` that exists:

```bash
cd <P>
git fetch <remote>
# the marker of the project, taken from the remote without merging, and put in the OLD state (plans still local):
git show <remote>/<branch>:.swissknifeman/project.json | python3 -c "
import json,sys
d=json.load(sys.stdin); d['plans_store']='legacy'; open('.swissknifeman/project.json','w').write(json.dumps(d,indent=2)+'\n')"
cat .swissknifeman/project.json            # workspace axioma, project_id <code>, plans_store legacy
skm workspace project scan <P>             # binds the checkout to <code>
skm workspace migrate plan --project <P> --local-only-secrets --json > $B/plan-<code>.json 2> $B/plan-<code>.err; echo rc=$?
```
(`mkdir -p .swissknifeman` first if the folder is missing.) The marker file is local for now: do **not** commit it.

Read `$B/plan-<code>.json` → `plans[]`, each with `action`:

| action | meaning | what to do |
| --- | --- | --- |
| `skipped-equal` | B's plan equals the workspace copy | nothing |
| `copied` | the plan exists only on B | step 6a |
| `conflict` | the plan exists in both and differs (B is newer) | step 6b |

Blockers (`blockers[]`): `MIGRATION_IN_PROGRESS` (an item is `in_progress` in B's plan: finish or park it with the owner, or
agree to use `--allow-in-progress` and record why), `MIGRATION_BLOCKED_SECRET` (use `--local-only-secrets`, already given),
`MIGRATION_BLOCKED_SYMLINK` (report, skip the project), `PROJECT_CODE_TAKEN`/`WORKSPACE_MISMATCH` (report, skip).
A project with `0` conflicts and `0` copies needs no step 6.

Print one table for the owner now: project, number of plans per action. **Wait for the owner's go** before step 6.

## 6. Merge into the workspace

### 6a. Plans that exist only on B (`copied`)

```bash
skm workspace migrate apply --project <P> --local-only-secrets --yes --json > $B/apply-<code>.json
```
`apply` copies them into `projects/<code>/plans/` and switches the marker to `workspace`; it commits nothing. Plans that
conflict make `apply` refuse (`MIGRATION_CONFLICT`); use 6b first for those projects.

### 6b. Plans that differ (`conflict`): merge by hand

B's version is newer, but the workspace copy may hold work of machine A that B never saw, so never overwrite blindly.

1. Keep both versions side by side (nothing is overwritten): `skm workspace migrate apply --project <P> --on-conflict import-copy --local-only-secrets --yes`.
   The workspace now has `plans/<plan>` (A's) and `plans/<plan>~<device>` (B's). The marker is `workspace`.
2. For every conflicting plan compare the two folders:
   ```bash
   W=~/.local/share/swissknifeman/workspaces/axioma/projects/<code>/plans
   diff -rq "$W/<plan>" "$W/<plan>~<device>" | grep -v '/views/\|/context/\|\.lock'
   ```
3. Merge file by file into `$W/<plan>` (the plan that stays), as an editor of JSON would:
   - `log.jsonl`: union of the lines of both, ordered by their timestamp field, no duplicates (`sort -u` on the union is not
     enough if lines differ by whitespace: compare as JSON).
   - an item or phase file (`phases/Pn/Pn.m.json`, `plan.json`, `decisions/Dn.json`): take the version with the **later
     `updated_at`**; when both changed the same field with different values, **stop and ask the owner** with both values.
   - a file present on one side only: keep it (a new item, an artifact).
   - `status` never goes backwards (`done` beats `in_progress` beats `todo`) unless the owner says so.
   Edit with the planner where it has a verb (`planner set …`, `planner reopen …`), else edit the JSON by hand.
4. Check the result: `cd <P> && python3 -I .swissknifeman/launcher.py planner check <plan>` must have no new errors compared with
   `… planner check <plan>~<device>`; `planner plans` lists the plan with the progress you expect.
5. Only when the owner agrees the merge is complete, move B's copy out: `mv "$W/<plan>~<device>" $B/merged-<code>-<plan>~<device>`.
   Do not leave `~<device>` copies in the workspace.

If there are many conflicts, do the project with the fewest first and show the owner the result before the rest.

## 7. Publish the merged workspace

```bash
skm workspace doctor --publish-safety          # verdict must not be "block"
skm workspace sync --commit --pull --push --json
skm workspace status --fetch --json            # dirty 0, ahead 0, behind 0
```
`REMOTE_FOREIGN`, `REMOTE_OTHER_WORKSPACE`, a diverged state or `WORKSPACE_CONFLICT`: `STOP` and report (machine A may have pushed
meanwhile: `sync --pull` merges, a conflict is decided per path with the owner: `--resolve PATH=local|remote`).

## 8. Replace the plans of every checkout by the workspace

For each `<P>` (the hub `swissknifeman` last), after step 7 is clean:

```bash
cd <P>
git diff --stat HEAD -- plans | tail -1                 # B's plans changed locally: expected, they are merged and backed up
git log --oneline <remote>/<branch>..HEAD | head        # local commits not on the remote? if any touch plans/: STOP, ask the owner
mkdir -p $B/removed-<code> && mv plans $B/removed-<code>/plans            # move, not delete (B's old plans stay in the backup)
mv .swissknifeman/project.json $B/marker-<code>-temporary.json          # the temporary marker of step 5 would block the pull
git rm -r -q --cached plans 2>/dev/null || true                          # tracked plans: record the removal, same as the remote has
git pull --ff-only <remote> <branch>                      # brings the marker (workspace) and the removal of plans/
cat .swissknifeman/project.json                           # plans_store: workspace
skm workspace migrate verify --project <P> --json         # states equal / legacy-removed are fine
python3 -I .swissknifeman/launcher.py planner plans | head
```
(Nothing is destroyed: B's old `plans/` is in `$B/removed-<code>/`.)
`git pull --ff-only` refusing (diverged, or local changes in tracked files other than plans): `STOP` and report. Do not merge or
rebase the owner's branches by yourself.

For the hub (`swissknifeman`): after its pull, update the manifest of the migrator to the real checkout (owner step, same three
`config set` commands with `~/projects/packages/swissknifeman/bridges/workspace-planner/extension.json`), remove the temporary
worktree (`git worktree remove ~/skm-hub-b`), and use `swissknifeman` from the normal checkout from now on.

## 9. Final checks on B

```bash
swissknifeman workspace status --fetch --json | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['code'],d['git'])"
swissknifeman workspace doctor
for p in <the checkouts>; do (cd ~/projects/packages/$p && python3 -I .swissknifeman/launcher.py project doctor | grep -E "plans-store|workspace"; python3 -I .swissknifeman/launcher.py planner plans | head -3); done
for p in <the checkouts>; do test -d ~/projects/packages/$p/plans && echo "plans/ still in $p"; done
```
Every project: `project.plans-store` is a workspace store, `project.workspace` is `ok` (a `warn` for a folder name that differs from the
code is acceptable), `planner plans` lists the merged plans, no `plans/` folder in the checkout.

## 10. Report to the owner (short)

- hub commit and `--version`; workspace head (`git -C ~/.local/share/swissknifeman/workspaces/axioma rev-parse --short HEAD`).
- Per project: found / branch / plans by action (`skipped-equal`, `copied`, `conflict`) / conflicts merged and how / pull done /
  `planner plans` count.
- Everything skipped or stopped, with the exact error code.
- Where the backup is (`$B`) and what is in `removed-*` and `merged-*`. Do not paste secrets or file contents.

The owner brings the report back to the planner session on machine A. Machine A's checkouts are already clean.

## Do not

- touch machine config yourself; push `--force`; pull a checkout before step 8; delete anything instead of moving it into `$B`;
- resolve a field-level conflict of two different values without the owner; leave `~<device>` copies in the workspace;
- commit the temporary marker of step 5; run migrations while a conductor or planner of that project is running.
