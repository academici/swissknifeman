import { useState } from "react";
import type { PackPayload, ResourceKind } from "../../api/generated/extensions";
import { useExtensionAccess, useExtensionCommand, usePacks, useResolution, useResources } from "../../api/hooks/extensions";
import { operatorError, segment } from "../../api/hooks/workspace";
import { SafeLink } from "../../components/content/SafeLink";
import { JsonView } from "../../components/data/JsonView";
import { Pagination } from "../../components/data/Pagination";
import { Table } from "../../components/data/Table";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Badge } from "../../components/primitives/Badge";
import { Button } from "../../components/primitives/Button";
import { escapeText } from "../../lib/safeText";
import { QueryView } from "../workspaces/WorkspacesPage";

function InstallForm() {
  const command = useExtensionCommand();
  const [invalid, setInvalid] = useState(false);
  return <section>
    <h2>Установка пакета</h2>
    <form onSubmit={event => {
      event.preventDefault();
      const fields = new FormData(event.currentTarget);
      let files: PackPayload["files"];
      try {
        files = JSON.parse(String(fields.get("files")));
        if (!Array.isArray(files) || !files.every(file =>
          file && typeof file.path === "string" && typeof file.content_b64 === "string")) throw new Error();
      } catch {
        setInvalid(true);
        return;
      }
      setInvalid(false);
      command.submit({ action: "install", body: {
        origin_label: String(fields.get("origin")).trim(),
        payload: { manifest_text: String(fields.get("manifest")), files },
        trust: fields.get("trust") === "operator" ? "operator" : "third_party",
        allow_quarantine: fields.has("quarantine"), dry_run: fields.has("preview"),
      } });
    }}>
      <label>Источник<input name="origin" placeholder="path:extensions/overlay" pattern="(path|archive):.+" required maxLength={200} /></label>
      <label>Манифест пакета<textarea name="manifest" required /></label>
      <label>Файлы пакета (JSON, поля path и content_b64)<textarea name="files" defaultValue="[]" required /></label>
      <label>Доверие<select name="trust"><option>third_party</option><option>operator</option></select></label>
      <label><input type="checkbox" name="quarantine" defaultChecked />Разрешить карантин</label>
      <label><input type="checkbox" name="preview" />Только проверить</label>
      {invalid && <p role="alert">Укажите массив файлов с полями path и content_b64.</p>}
      <Button type="submit" disabled={command.status === "pending"}>Установить пакет</Button>
    </form>
    <Button disabled={command.status === "pending"} onClick={() => command.submit({ action: "sync" })}>Синхронизировать встроенные пакеты</Button>
    {command.error && <ErrorPanel error={operatorError(command.error)} onRetry={command.retry} />}
    {command.status === "success" && <><p role="status">Операция завершена</p><JsonView value={command.data} /></>}
  </section>;
}

function Resolution({ kind, resourceKey }: { kind: ResourceKind; resourceKey: string }) {
  const query = useResolution(kind, resourceKey);
  return <section>
    <h3>Выбор версии · {escapeText(resourceKey)}</h3>
    {query.data && query.isStale && <Badge tone="warning">Данные устарели</Badge>}
    <QueryView query={query}>{view => <>
      {view.chosen ? <SafeLink href={`/extensions/resources/${segment(view.chosen.resource_version_id)}`}>
        {view.chosen.key} · {view.chosen.version}
      </SafeLink> : <p>Версия не выбрана</p>}
      <Table rows={view.candidates} rowKey={row => row.pack + row.version} empty="Нет кандидатов" columns={[
        { id: "pack", header: "Пакет", cell: row => escapeText(row.pack) },
        { id: "version", header: "Версия", cell: row => escapeText(row.version) },
        { id: "verdict", header: "Совместимость", cell: row => escapeText(row.verdict) },
        { id: "reason", header: "Причина выбора", cell: row => escapeText(row.reason) },
      ]} />
      {view.diagnostics.length > 0 && <JsonView value={view.diagnostics} />}
    </>}</QueryView>
  </section>;
}

function Catalog() {
  const packs = usePacks();
  const resources = useResources();
  const [selected, setSelected] = useState<{ kind: ResourceKind; key: string }>();
  const [id, setId] = useState("");
  return <>
    <h2>Пакеты</h2>
    {packs.query.data && packs.query.isStale && <Badge tone="warning">Данные устарели</Badge>}
    <QueryView query={packs.query}>{page => <>
      <Table rows={page.items} rowKey={row => row.pack_id} empty="Нет пакетов" columns={[
        { id: "title", header: "Пакет", cell: row => <SafeLink href={`/extensions/packs/${segment(row.pack_id)}`}>{row.title}</SafeLink> },
        { id: "slug", header: "Имя", cell: row => escapeText(row.slug) },
        { id: "versions", header: "Версии", cell: row => escapeText(row.versions.map(v => v.version).join(", ")) },
        { id: "trust", header: "Доверие", cell: row => escapeText(row.trust) },
        { id: "priority", header: "Приоритет", cell: row => row.priority },
      ]} /><Pagination {...packs.cursor} next={page.next_cursor} />
    </>}</QueryView>
    <h2>Ресурсы</h2>
    {resources.query.data && resources.query.isStale && <Badge tone="warning">Данные устарели</Badge>}
    <QueryView query={resources.query}>{page => <>
      <Table rows={page.items} rowKey={r => [r.kind, r.key, r.pack_slug, r.pack_version].join("/")} empty="Нет ресурсов" columns={[
        { id: "key", header: "Ресурс", cell: r => <Button onClick={() => setSelected(r)}>{escapeText(r.kind + ":" + r.key)}</Button> },
        { id: "version", header: "Версия", cell: r => escapeText(r.version) },
        { id: "pack", header: "Источник", cell: r => escapeText(r.pack_slug + "@" + r.pack_version) },
        { id: "compatibility", header: "Совместимость", cell: r => escapeText(r.verdict) },
        { id: "quarantine", header: "Карантин", cell: r => r.quarantined ? "В карантине" : "Нет" },
      ]} /><Pagination {...resources.cursor} next={page.next_cursor} />
    </>}</QueryView>
    {selected && <Resolution kind={selected.kind} resourceKey={selected.key} />}
    <label>ID версии ресурса<input value={id} onChange={e => setId(e.target.value.trim())} /></label>
    {id && <SafeLink href={`/extensions/resources/${segment(id)}`}>Открыть по ID</SafeLink>}
  </>;
}

export default function ExtensionsPage() {
  const { read, install } = useExtensionAccess();
  return <section><h1>Расширения</h1>
    {read ? <Catalog /> : <p role="alert">Нет доступа к каталогу расширений.</p>}
    {install && <InstallForm />}
  </section>;
}
