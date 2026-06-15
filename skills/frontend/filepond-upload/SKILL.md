---
name: filepond-upload
bucket: frontend
version: 0.1.0
description: "Загрузка файлов через FilePond в Vue + Laravel: регистрация vue-filepond и плагинов (validate-type/size, image-preview, file-poster), серверная обработка через rahulhaque/laravel-filepond (process/revert на /filepond), привязка serverId загруженного файла к форме, превью и постеры. Активировать при добавлении/правке загрузки файлов, drag-and-drop аплоада, FilePond-поля, превью изображений в форме, при словах filepond/vue-filepond/laravel-filepond/file upload/process/revert/serverId."
risk: write
persona: oss-dev
tags: [filepond, vue, laravel, file-upload, frontend, forms, image-preview]
requires: []
produces_for: []
outputs: []
snippets: [register-filepond.ts, FilePondField.vue, form-binding.md]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Загрузка файлов через FilePond (Vue + Laravel)

## Контекст

Загрузка файлов в форму Vue/Inertia-приложения на Laravel через **FilePond**:
drag-and-drop, мгновенная загрузка на сервер (instant upload), превью изображений
и постеры файлов, клиентская валидация типа/размера. Серверная часть — пакет
`rahulhaque/laravel-filepond`: один маршрут `/filepond` обслуживает все колбэки
FilePond (process/revert/patch/restore), временный файл идентифицируется
`serverId`, который потом привязывается к доменной модели.

**Когда активировать:**
- Добавляете/правите поле загрузки файлов, drag-and-drop аплоад, превью картинок
  или постеры вложений в форме.
- В коде/задаче встречаются: `filepond`, `vue-filepond`, `laravel-filepond`,
  `registerPlugin`, `processfile`/`removefile`, `serverId`, endpoints
  `process`/`revert`, `Filepond::field()`.
- Нужно связать загруженные файлы с формой (`useForm`) и обработать их на бэке.

**Не активировать**, если в проекте загрузка файлов сделана иначе (нативный
`<input type=file>` + ручной `FormData`, Uppy, Dropzone, прямой S3-presigned) —
это другой стек, скилл про FilePond.

Стек, который покрывает скилл: `filepond` (core) + `vue-filepond` (Vue-обёртка)
+ плагины `filepond-plugin-*` + `rahulhaque/laravel-filepond` (бэк). Поле
интегрируется как обычный input через `v-model` — совместимо с Inertia-формами
(см. скилл `frontend/inertia-vue`).

**Laravel Boost**: FilePond и `rahulhaque/laravel-filepond` **не** входят в Boost
(нет `.ai/`-каталога в пакете) — это **ours-only** скилл, паттерн описан целиком,
upstream не нужен. Версионные основы Inertia-форм (`useForm`, навигация) — за
Boost-скиллом inertia-vue-development; здесь — только нейтральный контракт поля и
его привязка к форме. Пакет: https://github.com/laravel/boost (скиллы —
`vendor/laravel/boost/.ai/`).

## Архитектура потока

```
[register-filepond.ts]  vueFilePond(...plugins) + CSS        → один раз на приложение
        │ регистрирует Vue-компонент <FilePond>
        ▼
[FilePondField.vue]  server: /filepond, v-model { id?, serverId? }[]
        │  instant upload  → POST /filepond → serverId (process)
        │  remove          → DELETE /filepond            (revert)
        │  restore постеров → GET /filepond              (load/restore)
        ▼ v-model (список ссылок)
[форма useForm]  attachment_files: UploadedFileRef[]      → form.post()
        ▼ payload
[Laravel]  Filepond::field($serverId)->getFile()         → привязка к модели
```

Главный принцип: **поле не знает про форму, форма не знает про FilePond**. Связь
— только через сериализуемый список ссылок `{ id?, serverId? }[]`. Это делает
поле переносимым между формами и проектами.

## Алгоритм

1. **Установка.** Фронт: `npm i filepond vue-filepond` + нужные плагины
   (`filepond-plugin-file-validate-type`, `-file-validate-size`,
   `-image-preview`, `-file-poster`). Бэк: `composer require rahulhaque/laravel-filepond`,
   опубликовать конфиг (`php artisan vendor:publish --tag=filepond-config`),
   настроить временный диск и TTL временных файлов.

2. **Регистрация один раз** (`resources/js/app.ts` или модуль `components/forms/filepond.ts`):
   вызвать `vueFilePond(...plugins)` — он внутри делает `registerPlugin(...)` и
   возвращает Vue-компонент. Импортировать CSS ядра **и** CSS каждого плагина,
   у которого он есть (`image-preview`, `file-poster`) — без стилей превью/постер
   не отрисуются. Зарегистрировать компонент глобально либо реэкспортить фабрику.
   Подключайте только нужные плагины — каждый утяжеляет бандл. См.
   `snippets/register-filepond.ts` (варианты: published-пакет `vue-filepond` и
   локальная типизированная обёртка над `filepond` core).

3. **Поле `FilePondField.vue`** (`snippets/FilePondField.vue`):
   - `server`-конфиг на endpoints laravel-filepond: `url`/`process`/`revert`/`patch`
     на `/filepond`, `withCredentials: true`, заголовки `X-CSRF-TOKEN` и
     `X-Requested-With: XMLHttpRequest` (иначе Laravel вернёт 419/redirect);
   - `v-model` — список ссылок `{ id?, serverId? }[]`: `{ id }` — уже сохранённый
     файл, `{ serverId }` — новый временный;
   - уже сохранённые файлы восстанавливаются как `defaultFiles` с
     `options.type: "local"` (постеры/имена) — source = их `id`;
   - обработчик `@processfile` добавляет в модель `{ serverId }`, `@removefile`
     убирает запись по `id` или `serverId`;
   - props-фасад поля: `name`, `multiple`, `acceptedFileTypes`, `maxFileSize`,
     `files` (существующие) — нейтральны, без доменной специфики.

4. **Привязка к форме** (`snippets/form-binding.md`): список ссылок кладётся в
   `useForm` как обычное поле (`attachment_files`), инициализируется `{ id }`
   существующих файлов; на `form.post()` уходят и сохранённые, и новые. Ошибки
   валидации — из `form.errors`. Логику «существующие vs ожидающие» при
   необходимости выносить в composable, а не в компонент.

5. **Серверная обработка** (`snippets/form-binding.md`, раздел backend): маршрут
   `/filepond` регистрируется сервис-провайдером пакета — руками не писать. По
   `serverId` забрать файл: `Filepond::field($serverId)->getFile()` (→ `UploadedFile`),
   при необходимости `->validate([...])`, затем привязать к модели (media-library
   и т.п.). Для множественного поля передавать массив serverId. Сохранённые `{ id }`
   синхронизировать отдельно (оставить/удалить). Временные файлы после `getFile()`
   очищаются — не оставлять «висящих» загрузок.

6. **Валидация в двух местах.** Клиент: плагины `file-validate-type`
   (`acceptedFileTypes`) и `file-validate-size` (`maxFileSize`). Сервер:
   `->validate()` или FormRequest — клиентская валидация удобство, не защита.

7. **Большие файлы.** Включить `:chunk-uploads="true"` — FilePond шлёт чанки
   через `PATCH /filepond`; laravel-filepond это поддерживает из коробки.

## Превью и постеры

- **`filepond-plugin-image-preview`** — инлайн-превью изображений сразу после
  выбора. Нужен и JS-плагин, и его CSS.
- **`filepond-plugin-file-poster`** + `:allow-file-poster="true"` — карточка-постер
  для не-картинок и для восстановленных файлов; постер задаётся через
  `metadata.poster` или восстановлением `type: "local"`.
- Восстановление сохранённых файлов: массив `defaultFiles` с
  `{ source: <id|url>, options: { type: "local", file: { name, size, type } } }`
  — FilePond подтянет их через `load`/`restore` (GET `/filepond`) и покажет
  постером, не загружая заново.

## Типичные ошибки

- **419 / redirect на process** — нет `X-CSRF-TOKEN` или `X-Requested-With`
  в `server.headers`, либо `withCredentials` не выставлен.
- **Превью/постер не видны** — забыт импорт CSS плагина (нужен и JS, и CSS).
- **Файл не привязался к модели** — в payload ушёл `serverId`, но бэк его не
  обработал через `Filepond::field()`, либо временный файл протух (TTL конфига).
- **Дубли при редактировании** — существующие файлы добавлены и в `defaultFiles`,
  и повторно как новые; модель должна различать `{ id }` (оставить) и `{ serverId }`
  (добавить).
- **Жёсткая привязка к домену** — поле тащит бизнес-типы конкретной сущности;
  держите контракт нейтральным (`{ id?, serverId? }`), доменное — снаружи.

## Когда какой сниппет открывать

| Ситуация | Файл |
|:---|:---|
| Подключить FilePond и плагины, настроить CSS (точка входа) | `snippets/register-filepond.ts` |
| Написать переиспользуемое поле загрузки с server-конфигом и v-model | `snippets/FilePondField.vue` |
| Связать поле с формой и обработать файлы на сервере (serverId → модель) | `snippets/form-binding.md` |

## Чеклист качества

- [ ] FilePond и плагины зарегистрированы один раз; импортирован CSS ядра и каждого используемого плагина.
- [ ] `server`-конфиг указывает на `/filepond` с `withCredentials` и заголовками `X-CSRF-TOKEN` + `X-Requested-With`.
- [ ] Поле управляется через `v-model` нейтральным списком `{ id?, serverId? }[]`; форма про FilePond не знает.
- [ ] Существующие файлы восстановлены через `defaultFiles` (`type: "local"`), не загружаются повторно.
- [ ] `@processfile` добавляет `{ serverId }`, `@removefile` чистит запись по id/serverId.
- [ ] На бэке `serverId` обработан `Filepond::field()->getFile()`, временные файлы не утекают.
- [ ] Тип и размер валидируются и на клиенте (плагины), и на сервере.
- [ ] Для крупных файлов включён `chunk-uploads` (PATCH `/filepond`).
- [ ] Поле и контракт без доменной/проектной специфики — переносимы.

## Ссылки

- https://pqina.nl/filepond/ — документация FilePond и плагинов
- https://github.com/pqina/vue-filepond — Vue-обёртка
- https://github.com/rahulhaque/laravel-filepond — серверная обработка (process/revert, `Filepond::field()`)
- Связанные скиллы: `frontend/inertia-vue` (формы/страницы), `frontend/vue-composition-api`, `frontend/wayfinder`
