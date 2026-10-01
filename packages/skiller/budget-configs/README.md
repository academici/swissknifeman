# budget-configs

Test configs (format `.swissknife.json`: `project_type` / `buckets` / `exclude`)
for the command `skiller budget`. Needed to compare the token budget of sets without
real project on disk:

```bash
skiller budget --config budget-configs/laravel-full.json
skiller budget --compare laravel-full,laravel-minimal
```

Name in `--compare` resolves to `budget-configs/<name>.json`. Add profiles here
typical projects whose budget you want to keep under control.
