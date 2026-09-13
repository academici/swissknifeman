<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/task/commands/fix.md
Canonical SHA-256: sha256:25678f123188ada21e102329b854b7208b73c4b2cb3c126c2fd72d365426b1ab
Adapter: task.codex-command/1.0.12
-->
Это МЕЛКАЯ инкрементальная правка. Ввод пользователя: «$ARGUMENTS».
Применяй общий opt-in контракт `references/intent-routing.md` из установленного пакета Task.
Заверши исправление напрямую: design, план, phase audit и plan close не являются
условием готовности; старые инструкции в файле задания не отменяют текущий запрос владельца.
Модель/effort запинены (implementation/medium) — не переключай вручную (frontier тут избыточен).

Профиль `fix` (token-frugal):
1. **Один проход, без fan-out и без субагентов** — задача мелкая, координация не окупится.
2. **Selective-input** (экономия 5–50×): читай slice — функцию/класс/роут ±контекст, не файлы целиком; логи —
   `tail -n`/`grep` по идентификатору, не весь файл; ошибки — последний stack-frame; PR/дифф — `git diff`/
   `gh pr diff`, не файлы. «Point, don't paste»: указывай путь и дочитывай нужное.
3. **Минимальное изменение** под задачу; на изменённое поведение — тест/проверка; не разводи абстракции
   «на вырост».
4. Внешний факт под сомнением → `verify-claims`-лестница (context7 → `perplexity-web`), не утверждай по памяти.
5. Дерево чистое; НЕ git push / PR без явной просьбы.
