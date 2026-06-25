# Острая грань: raw-запросы Eloquent / Query Builder

## Паттерны поиска

```bash
grep -rnE "DB::raw|whereRaw|selectRaw|orderByRaw|havingRaw|groupByRaw|DB::(statement|select|insert|update|delete)\(" app/
```

## Что считается уязвимостью

Пользовательский ввод (request, route-параметр, заголовок, поле модели,
заполненное пользователем) попадает в raw-строку через конкатенацию или
интерполяцию:

```php
// УЯЗВИМО: ввод в строке запроса
->whereRaw("name like '%{$request->q}%'")
->orderByRaw($request->input('sort'))   // сортировка из запроса — инъекция

// БЕЗОПАСНО: биндинги
->whereRaw('name like ?', ["%{$request->q}%"])
```

## Особые случаи

- `orderByRaw`/`groupByRaw` **не поддерживают биндинги для имён колонок** —
  имя колонки из ввода валидировать allow-list'ом:
  `in_array($sort, ['name', 'created_at'], true)`.
- `DB::statement` в миграциях с константной строкой — не находка.
- Косвенный ввод: значение из БД, которое когда-то пришло от пользователя
  (second-order injection) — тоже считается.

## Severity

- Ввод напрямую в raw без биндинга — **critical**.
- Ввод через allow-list/каст к int — ok, отметить как проверенное.
- Raw с константной строкой — не находка (но отметить для variant analysis:
  похожие места могут быть с вводом).
