# P0 isolated CLI root-resolution defect

**Дата:** 2026-07-20
**Класс:** environment / root resolution / write isolation
**Статус:** incident confirmed by Owner; generated main outputs restored and sealed hash-only

## Инцидент

Во время owner-confirmed изолированного исполнения bare/global `skiller` был найден через
`PATH` вне worktree и разрешился в launcher dirty main checkout. Write-capable regeneration
тем самым выбрала main root вместо delivery worktree. Это finding фиксирует только механизм
ошибки и восстановленное hash/status состояние; содержимое main, unrelated paths и full main
status не читались и не публикуются.

## Path-only evidence

Bare CLI не запускался. Проверялась только резолюция пути:

```text
type -P skiller
→ /home/vostrikov/.local/bin/skiller

realpath /home/vostrikov/.local/bin/skiller
→ /home/vostrikov/projects/packages/swissknifeman/packages/skiller/bin/skiller

realpath ./packages/skiller/bin/skiller
→ /tmp/swissknifeman-p0.6-d63/packages/skiller/bin/skiller
```

Git root для resolved global launcher —
`/home/vostrikov/projects/packages/swissknifeman`; для explicit local launcher —
`/tmp/swissknifeman-p0.6-d63` (`git -C <launcher-dir> rev-parse --show-toplevel`).

## Восстановление и sealed evidence

`artifacts/d65-main-reconciliation.json` фиксирует два generated outputs как
`matches-base`: main path clean, main SHA-256 равен base SHA-256, delivery SHA-256 отличается.
Это ровно допустимое D68 exclusion. Если derived path dirty либо main hash не равен base,
`d65-main-reconciliation-check.py` блокирует reconciliation и требует пересчитать output
из delivery sources. Main writes для создания и проверки carrier не выполняются.

## Stable invariant

В isolated worktree write-capable package CLI вызывается только explicit worktree-local
путём `./packages/<name>/bin/<cli>`. Перед write проверяются resolved launcher и git repo
root; bare/global package CLI запрещён. Компактный recurring invariant добавлен в root
`AGENTS.md`.

## Post-item review — F1/F2 resolution

Пост-review подтвердил два узких дефекта именно в read-only D65 helper, без изменения
manifest или authority. **F1:** каждый git subprocess теперь получает сохранённый environment
с `GIT_OPTIONAL_LOCKS=0`; bounded throwaway-repository probe фиксирует неизменность SHA-256 и
mtime index после path-scoped `git status`. **F2:** каждый component main-root relative path
открывается descriptor-relative с `O_NOFOLLOW`, final descriptor проверяется через `fstat` как
regular file, и digest читается из этого descriptor. Bounded probes reject same-byte in-root и
outside-root symlinks, non-regular final node, а также symlink/replaced directory component.
Main остаётся path-scoped read-only; F1/F2 resolved отдельным fix-forward commit.
