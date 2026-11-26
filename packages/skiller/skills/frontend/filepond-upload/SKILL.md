---
name: filepond-upload
bucket: frontend
version: 0.1.0
description: "File upload via FilePond in Vue + Laravel: register vue-filepond + plugins (validate-type/size, image-preview, file-poster), server via rahulhaque/laravel-filepond (process/revert on /filepond), bind serverId to form, previews/posters. Activate on file upload, drag-and-drop, FilePond field, image preview, filepond/vue-filepond/laravel-filepond/process/revert/serverId."
risk: write
persona: oss-dev
tags: [filepond, vue, laravel, file-upload, frontend, forms, image-preview, inertia, uploads]
requires: []
produces_for: []
outputs: []
snippets: [register-filepond.ts, FilePondField.vue, form-binding.md]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: FilePond file upload (Vue + Laravel)

Stack: `filepond` (core) + `vue-filepond` (Vue wrapper) + `filepond-plugin-*` + `rahulhaque/laravel-filepond` (backend). One route `/filepond` serves all FilePond callbacks (process/revert/patch/restore); temp file identified by `serverId`, later bound to a domain model. Field integrates as a normal input via `v-model` — compatible with Inertia forms (see `frontend-backend/inertia-vue`).

## Activate when
- Adding/editing file-upload field, drag-and-drop upload, image preview, attachment posters in a form.
- Code/task mentions: `filepond`, `vue-filepond`, `laravel-filepond`, `registerPlugin`, `processfile`/`removefile`, `serverId`, endpoints `process`/`revert`, `Filepond::field()`.
- Need to bind uploaded files to a form (`useForm`) and handle them on backend.

## Do NOT activate
- Upload done otherwise: native `<input type=file>` + manual `FormData`, Uppy, Dropzone, direct S3-presigned — different stack.

## Laravel Boost
- FilePond and `rahulhaque/laravel-filepond` are NOT in Boost (no `.ai/` dir in package) — ours-only skill, no upstream. Versioned Inertia form basics (`useForm`, navigation) belong to Boost skill inertia-vue; here only neutral field contract + form binding. Package: https://github.com/laravel/boost (skills — `vendor/laravel/boost/.ai/`).

## Flow

```
[register-filepond.ts]  vueFilePond(...plugins) + CSS        → once per app
        │ registers Vue component <FilePond>
        ▼
[FilePondField.vue]  server: /filepond, v-model { id?, serverId? }[]
        │  instant upload  → POST /filepond → serverId (process)
        │  remove          → DELETE /filepond            (revert)
        │  restore posters → GET /filepond               (load/restore)
        ▼ v-model (list of refs)
[form useForm]  attachment_files: UploadedFileRef[]        → form.post()
        ▼ payload
[Laravel]  Filepond::field($serverId)->getFile()          → bind to model
```

- Principle: field does not know the form, form does not know FilePond. Link only via serializable ref list `{ id?, serverId? }[]` → field portable across forms/projects.

## Algorithm

1. **Install.** Front: `npm i filepond vue-filepond` + needed plugins (`filepond-plugin-file-validate-type`, `-file-validate-size`, `-image-preview`, `-file-poster`). Back: `composer require rahulhaque/laravel-filepond`, publish config (`php artisan vendor:publish --tag=filepond-config`), configure temp disk + temp-file TTL.

2. **Register once** (`resources/js/app.ts` or module `components/forms/filepond.ts`): call `vueFilePond(...plugins)` (internally does `registerPlugin(...)`, returns Vue component). Import core CSS AND each plugin's CSS that has one (`image-preview`, `file-poster`) — without styles preview/poster won't render. Register component globally or re-export the factory. Include only needed plugins (each adds to bundle). See `snippets/register-filepond.ts` (variants: published `vue-filepond`, and local typed wrapper over `filepond` core).

3. **Field `FilePondField.vue`** (`snippets/FilePondField.vue`):
   - `server` config to laravel-filepond endpoints: `url`/`process`/`revert`/`patch` on `/filepond`, `withCredentials: true`, headers `X-CSRF-TOKEN` and `X-Requested-With: XMLHttpRequest` (else Laravel returns 419/redirect);
   - `v-model` — ref list `{ id?, serverId? }[]`: `{ id }` = already-saved file, `{ serverId }` = new temp;
   - already-saved files restored as `defaultFiles` with `options.type: "local"` (posters/names) — source = their `id`;
   - `@processfile` adds `{ serverId }` to model, `@removefile` removes entry by `id` or `serverId`;
   - props facade: `name`, `multiple`, `acceptedFileTypes`, `maxFileSize`, `files` (existing) — neutral, no domain specifics.

4. **Bind to form** (`snippets/form-binding.md`): ref list goes into `useForm` as a normal field (`attachment_files`), initialized from `{ id }` of existing files; on `form.post()` both saved and new are sent. Validation errors from `form.errors`. Push "existing vs pending" logic into a composable, not the component.

5. **Backend** (`snippets/form-binding.md`, backend section): `/filepond` route registered by package service-provider — do not write by hand. Get file by `serverId`: `Filepond::field($serverId)->getFile()` (→ `UploadedFile`), optionally `->validate([...])`, then bind to model (media-library etc.). For multiple field pass array of serverIds. Sync saved `{ id }` separately (keep/delete). Temp files cleared after `getFile()` — leave no dangling uploads.

6. **Validate in two places.** Client: plugins `file-validate-type` (`acceptedFileTypes`) + `file-validate-size` (`maxFileSize`). Server: `->validate()` or FormRequest — client validation is convenience, not protection.

7. **Large files.** Set `:chunk-uploads="true"` — FilePond sends chunks via `PATCH /filepond`; laravel-filepond supports it out of the box.

## Previews & posters
- `filepond-plugin-image-preview` — inline image preview right after select. Needs both JS plugin and its CSS.
- `filepond-plugin-file-poster` + `:allow-file-poster="true"` — poster card for non-images and restored files; poster set via `metadata.poster` or restore `type: "local"`.
- Restore saved files: `defaultFiles` array with `{ source: <id|url>, options: { type: "local", file: { name, size, type } } }` — FilePond loads via `load`/`restore` (GET `/filepond`) and shows poster without re-uploading.

## Common errors
- **419 / redirect on process** — missing `X-CSRF-TOKEN` or `X-Requested-With` in `server.headers`, or `withCredentials` not set.
- **Preview/poster not visible** — forgot plugin CSS import (need both JS and CSS).
- **File not bound to model** — `serverId` in payload but backend didn't handle it via `Filepond::field()`, or temp file expired (config TTL).
- **Duplicates on edit** — existing files added both in `defaultFiles` and again as new; model must distinguish `{ id }` (keep) vs `{ serverId }` (add).
- **Hard domain coupling** — field carries entity business types; keep contract neutral (`{ id?, serverId? }`), domain logic outside.

## Which snippet
| Case | File |
|:---|:---|
| Register FilePond + plugins, set up CSS (entry point) | `snippets/register-filepond.ts` |
| Write reusable upload field with server config + v-model | `snippets/FilePondField.vue` |
| Bind field to form + handle files server-side (serverId → model) | `snippets/form-binding.md` |

## Quality checklist
- [ ] FilePond + plugins registered once; core CSS + each used plugin's CSS imported.
- [ ] `server` config points to `/filepond` with `withCredentials` + headers `X-CSRF-TOKEN` + `X-Requested-With`.
- [ ] Field driven via `v-model` neutral list `{ id?, serverId? }[]`; form unaware of FilePond.
- [ ] Existing files restored via `defaultFiles` (`type: "local"`), not re-uploaded.
- [ ] `@processfile` adds `{ serverId }`, `@removefile` cleans entry by id/serverId.
- [ ] Backend handles `serverId` via `Filepond::field()->getFile()`, temp files don't leak.
- [ ] Type and size validated on both client (plugins) and server.
- [ ] Large files use `chunk-uploads` (PATCH `/filepond`).
- [ ] Field and contract free of domain/project specifics — portable.

## Links
- https://pqina.nl/filepond/ — FilePond + plugins docs
- https://github.com/pqina/vue-filepond — Vue wrapper
- https://github.com/rahulhaque/laravel-filepond — server-side (process/revert, `Filepond::field()`)
- Related skills: `frontend-backend/inertia-vue` (forms/pages), `frontend-vue/vue-composition-api`, `frontend-wayfinder/wayfinder`
