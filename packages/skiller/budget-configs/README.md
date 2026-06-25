# budget-configs

Тестовые конфиги (формат `.swissknife.json`: `project_type` / `buckets` / `exclude`)
для команды `skiller budget`. Нужны, чтобы сравнивать токеновый бюджет наборов без
реального проекта на диске:

```bash
skiller budget --config budget-configs/laravel-full.json
skiller budget --compare laravel-full,laravel-minimal
```

Имя в `--compare` резолвится в `budget-configs/<name>.json`. Добавляй сюда профили
типовых проектов, бюджет которых хочешь держать под контролем.
