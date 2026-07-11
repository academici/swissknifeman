# Open Questions — SKM-ROADMAP-005

Спорное/требующее владельца, вынесенное из фаз по протоколу plan-protocol §3.

| OQ | Дата | Статус | Вопрос | Контекст |
|:--|:--|:--|:--|:--|
| OQ1 | 2026-07-11 | 🔵 open | Политика **vendored-vs-bilingual** для скилла `architect/domain-modeling`: он вендорен (`upstream.json`, strategy=notify, тело из mattpocock/skills), но P6.1 правит его по двуязычной модели `SKILL.ru.md`→regen. `check-translations.sh` считает его external и НЕ стампит `ru-source-sha256` → дрейф RU↔EN не детектируется. Варианты: **(а)** снять `upstream.json` (принять как форк — мы уже разошлись) → тул начнёт детектить дрейф; **(б)** научить `check-translations.sh --stamp` стамповать external-скиллы с `SKILL.ru.md` (тул-фикс, отдельный item); **(в)** оставить как есть (авто-детект для этого скилла отключён осознанно). | P6.1 закрыт 🟠 с обходом (маркер заполнен вручную реальным sha). Не блокирует P6.2/P6.3. Детали — phases/P6.md P6.1 Known Deviations |
