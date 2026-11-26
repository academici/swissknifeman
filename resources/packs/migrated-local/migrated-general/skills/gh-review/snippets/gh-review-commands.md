# Cheat Sheet gh for review and spot reading

> Principle: `gh` gives the minimum slice (diff, threads, one file) — this is it
> saving tokens vs. downloading files/entire repository. Local VCS —
> for `git`, is not duplicated.

## Read PR (dotted)

```bash
gh pr view <N>                          # description, status, checklists
gh pr view <N> --comments               # review threads only
gh pr diff <N>                          # diff only
gh pr diff <N> -- path/to/file          # single path diff
gh pr checks <N>                        # statuses CI (without logs)
gh pr view <N> --json files -q '.files[].path'    # list of paths
gh pr view <N> --json url -q .url       # link for handoff
```

## Review publication

```bash
gh pr comment <N> --body "..."
gh pr review <N> --comment        -b "..."
gh pr review <N> --approve        -b "LGTM: ..."
gh pr review <N> --request-changes -b "..."
```

## Point reading of someone else's repository (import/reconciliation)

```bash
# one file (content — base64)
gh api repos/{owner}/{repo}/contents/{path}?ref={ref} -q '.content' | base64 -d

# directory listing without content
gh api repos/{owner}/{repo}/contents/{dir}?ref={ref} -q '.[].path'

# last commit that changed the file (detect upstream-drift)
gh api 'repos/{owner}/{repo}/commits?path={path}&per_page=1' -q '.[0].sha'

# check limits before mass fetch
gh api rate_limit -q '.resources.core | "\(.remaining)/\(.limit)"'
```

## Issues and releases (handoff)

```bash
gh issue view <N> --json url -q .url
gh issue comment <N> --body "..."
gh release view <tag>
```

## What remains git (gh does NOT replace)

```bash
git commit / git branch / git switch
git diff            # working tree (not PR — for PR this gh pr diff)
git log / git rebase / git stash
```
