---
name: writing-style
bucket: general
version: 0.1.0
description: "Tone & language of code artifacts: Russian by default for comments, commit bodies, test descriptions it()/test(), docstrings, internal docs; live language, no bureaucratese, explain WHY not WHAT. Activate when writing comments, commit bodies, test descriptions, internal docs (git format/mechanics → git-commit-rules)."
risk: read
persona: oss-dev
tags: [writing, language, russian, comments, commits, tests, docs, style]
requires: []
produces_for: []
outputs: []
snippets: [before-after.md]
adapters: [claude, cursor, fable]
sha256: ""
---

# Writing Style

Advisory (risk: read): shapes wording, not format. Applies when writing: code comments (`//`, `#`, `/* */`); commit message body (subject + body); test descriptions `it('...')`, `test('...')`, `describe('...')`, method names `test_...`; docstring / PHPDoc / JSDoc and internal docs (module README, `docs/`).

Split vs `git-commit-rules` (general): that = git FORMAT & MECHANICS (Conventional Commits, types, scope, breaking, husky/commitlint, action order). Here = TONE & LANGUAGE. Take format from `git-commit-rules`, wording from here.

## Algorithm

1. Determine artifact language. Default Russian for anything team members read: comments, commit bodies, test descriptions, docstrings, internal docs. Exceptions → "When English fits".
2. Decide if a comment is needed at all. Justified only when WHY is non-obvious without it. If text restates what the code shows — delete it, don't rewrite.
3. State reason, not action. Write intent and consequence ("so the archive isn't pulled into the public list"), not mechanics ("performs a selection"). If a phrase starts with "this code / method performs / produces" — rewrite.
4. Tense: present or past — "проверяем", "ограничили", "оставили". No infinitives, no verbal nouns ("осуществление проверки").
5. Commit subject — completed action, past tense, usually plural: "добавили", "исправили", "убрали", "обновили". Not a bare infinitive ("добавить", "исправить"). Body — reason + effect in 1–2 lines. Structure (type, scope, breaking) from `git-commit-rules`.
6. Test descriptions — human-readable Russian phrase describing checked behavior: what the system does and under what conditions. Not a restatement of the method name, not transliteration. See "Test descriptions".
7. Docstrings & internal docs — Russian, concrete: why the class/method exists, non-obvious constraints and side effects. Don't restate the signature in words.
8. Run the quality checklist before leaving the text.

## Russian by default

- Code comments — Russian.
- Commit message (subject + body) — Russian.
- Test descriptions & human-readable args (`it('...')`, `test('...')`, `describe('...')`) — Russian.
- Docstring / PHPDoc / JSDoc and internal docs (module docs, team `docs/`) — Russian.
- Identifiers, API keys, method/class names, enum values, format tokens — stay English; translate only user-facing wording, not the contract.

## Live language, no bureaucratese

- Explain WHY, not WHAT: code already shows what it does; the comment adds missing intent/context.
- Present/past tense: "ограничили", "проверяем", "оставили как есть".
- Forbidden — bureaucratese and AI templates: "данный код", "осуществляет", "производит выборку", "выполняет операцию", "в рамках", "является".
- No jargon or "universal" phrases that fit any code.
- Short: one or two lines of reason beat a paragraph of restatement.

```php
// Хорошо — причина:
// Ограничили выборку активными записями, чтобы не тянуть архив в публичный список.

// Плохо — пересказ канцеляритом:
// Данный код осуществляет выборку записей из таблицы.
```

## Commit bodies: tone & language

- Subject — completed action in Russian: "добавили", "исправили", "убрали".
- Body — concrete result and why it's needed, no template phrases.
- Format (type, scope, breaking, hooks) — entirely from `git-commit-rules`.

```text
fix(api): исправили ложный 403 для участников без роли исполнителя

Добавили guard по статусу, чтобы не отклонять запросы тех, у кого доступ есть.
```

## Test descriptions

- Describe BEHAVIOR and under what conditions — Russian, concrete.
- Don't transliterate the method name or restate the signature.

```php
// Хорошо:
it('возвращает 403, когда у пользователя нет роли исполнителя', function () { /* ... */ });

// Плохо — транслитерация имени метода:
it('test user role check returns forbidden', function () { /* ... */ });
```

```php
// PHPUnit-стиль — имя метода латиницей, описание по-русски:
/** @test Архивный документ не попадает в публичный список */
public function archived_document_is_hidden_from_public_list(): void { /* ... */ }
```

## When English fits

Deliberate choice, not default. Fits when text is read outside the team or is part of an external contract:

- Public API of a library/package: PHPDoc/JSDoc and docstrings of public classes/methods external consumers see.
- Docs for publication: `docs-public`, repo README with external audience, marketplace/registry texts.
- Messages for international audience where Russian excludes readers.

Stays inside the team → Russian. Unsure who the reader is → default Russian.

## Quality checklist

- [ ] Comments/commit bodies/test descriptions/internal-code docstrings — Russian.
- [ ] English kept only for public API, docs-public, external audience.
- [ ] Comment explains WHY, not WHAT; no redundant comments.
- [ ] No bureaucratese / AI templates ("данный код", "осуществляет", "производит", "является").
- [ ] Present/past tense, no infinitives or verbal nouns.
- [ ] Commit subject — completed action, not bare infinitive; body has reason + effect.
- [ ] Test description — about behavior and conditions, no method-name transliteration.
- [ ] Identifiers, keys, contracts not translated — only prose translated.

## Conformance

- Write comments, commit bodies, test descriptions, internal-code docstrings in Russian.
- Keep English only for public API, docs-public, external audience.
- Comment explains WHY, not restates WHAT; delete code-restating comments.
- No bureaucratese / AI templates: "данный код", "осуществляет", "производит", "является".
- Present/past tense; no infinitives or verbal nouns.
- Commit subject — completed action ("добавили"), not a bare infinitive.
- Commit body — reason + effect in 1–2 lines, no generic phrases.
- Test description — behavior and conditions in Russian, no method-name transliteration.
- Don't translate identifiers, keys, contracts — prose only.

## References

- `git-commit-rules` (general) — git format & mechanics: Conventional Commits, types, scope, breaking, husky/commitlint, action order.
- `compact-responses` (general) — model output brevity (how much text, when); this skill is tone & language when text IS needed.
- snippets/before-after.md — bad/good pairs for a comment and a commit subject.

<!-- ru-source-sha256: f70f22617687a6cac7d09eba060e37d5334b9c5ff03f513319a5a0bd1c030685 -->
