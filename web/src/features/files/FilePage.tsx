import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, useParams } from "react-router";
import type { FileVersionView, GetFileVersionView, GetFileView } from "../../api/generated/artifacts";
import { ApiError } from "../../api/errors";
import { downloadBlob, useBlobTransport } from "../../api/hooks/artifacts";
import { allowed, segment, useCommand, usePage, useRead, withParams } from "../../api/hooks/workspace";
import { keys } from "../../api/keys";
import { useAuth } from "../../app/providers/AuthProvider";
import { useScope } from "../../app/providers/ScopeProvider";
import { CodeBlock } from "../../components/content/CodeBlock";
import { Markdown } from "../../components/content/Markdown";
import { KeyValue } from "../../components/data/KeyValue";
import { Pagination } from "../../components/data/Pagination";
import { Table } from "../../components/data/Table";
import { ConflictPanel } from "../../components/feedback/ConflictPanel";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { ConfirmDialog } from "../../components/primitives/ConfirmDialog";
import { escapeText } from "../../lib/safeText";
import { QueryView } from "../workspaces/WorkspacesPage";
import UploadDialog from "./UploadDialog";

function VersionActions({ version }: { version: FileVersionView }) {
  const bytes = useBlobTransport();
  const mime = (version.declared_media_type ?? version.detected_media_type).split(";")[0]?.toLowerCase() ?? "";
  const isText = mime.startsWith("text/") || ["application/json", "application/xml", "application/xhtml+xml", "image/svg+xml"].includes(mime);
  const preview = useMutation({
    mutationFn: async () => (await bytes.content(version.file_version_id)).text(),
  });
  const download = useMutation({
    mutationFn: async () => downloadBlob(await bytes.content(version.file_version_id), escapeText(version.original_filename)),
  });
  return <>
    <Button disabled={download.isPending} onClick={() => download.mutate()}>Скачать</Button>
    {isText && <Button disabled={preview.isPending} onClick={() => preview.data === undefined ? preview.mutate() : preview.reset()}>
      {preview.data === undefined ? "Предпросмотр" : "Закрыть предпросмотр"}
    </Button>}
    {preview.data !== undefined && (mime === "text/markdown" ? <Markdown text={preview.data} /> : <CodeBlock text={preview.data} />)}
    {(preview.error || download.error) && <ErrorPanel error={preview.error ?? download.error} />}
  </>;
}

function VersionDetails({ id, file }: { id: string; file: GetFileView }) {
  const { scope } = useScope();
  const key = keys.forScope(scope).file(file.file_id);
  const query = useRead<GetFileVersionView>(key, "/file-versions/" + segment(id));
  return <QueryView query={query}>{version => <section><h3>Версия {version.version_no}</h3>
    <dl><KeyValue label="Имя файла" value={version.original_filename} /><KeyValue label="SHA-256" value={version.digest} />
      <KeyValue label="Размер в байтах" value={version.size_bytes} /><KeyValue label="Проверка" value={version.safety_verdict} /></dl>
    <VersionActions version={version} />
  </section>}</QueryView>;
}

function FileDetail({ file, reload }: { file: GetFileView; reload(): void }) {
  const { me } = useAuth();
  const ws = file.workspace_id;
  const path = "/files/" + segment(file.file_id);
  const { scope } = useScope();
  const scoped = keys.forScope(scope);
  const { query, cursor } = usePage<FileVersionView>(path + "/versions", scoped.file(file.file_id));
  const [selected, setSelected] = useState<string | null>(null);
  const [trashVersion, setTrashVersion] = useState<number | null>(null);
  const action = useCommand(ws);
  const conflict = action.error instanceof ApiError && action.error.code === "VERSION_CONFLICT"
    ? action.error : null;
  const canWrite = allowed(me, "file.write", file.project_id, ws);
  return <>
    <h2>{escapeText(file.title)}</h2>
    <dl><KeyValue label="Классификация" value={file.classification} /><KeyValue label="Состояние" value={file.state} />
      <KeyValue label="Источник" value={file.origin} /><KeyValue label="Текущая версия" value={file.current_version.version_no} /></dl>
    {canWrite && (file.state === "active" ? <>
      {allowed(me, "file.write", ws) && <UploadDialog workspaceId={ws} projectId={file.project_id} existing={file} />}
      <Button disabled={action.isPending} onClick={() => setTrashVersion(file.row_version)}>В корзину</Button>
    </> : <Button disabled={action.isPending} onClick={() => action.mutate({ path: path + "/restore", version: file.row_version, body: {} })}>Восстановить</Button>)}
    <ConfirmDialog open={trashVersion !== null} title="Переместить файл в корзину?" destructive requireReason
      onClose={() => setTrashVersion(null)} onConfirm={reason => {
        if (trashVersion !== null) action.mutate({ path: path + "/trash", version: trashVersion, body: { reason } });
        setTrashVersion(null);
      }} />
    {conflict
      ? <ConflictPanel error={conflict} submitted={action.variables?.version} current={conflict.details} onReload={() => { action.reset(); reload(); }} />
      : action.error && <ErrorPanel error={action.error} />}
    <h2>Версии</h2>
    <QueryView query={query}>{page => <>
      <Table rows={page.items} rowKey={row => row.file_version_id} empty="Нет версий" columns={[
        { id: "version", header: "Версия", cell: row => <Button onClick={() => setSelected(row.file_version_id)}>Версия {row.version_no}</Button> },
        { id: "filename", header: "Имя файла", cell: row => escapeText(row.original_filename) },
        { id: "digest", header: "SHA-256", cell: row => escapeText(row.digest) },
        { id: "content", header: "Содержимое", cell: row => <VersionActions key={row.file_version_id} version={row} /> },
      ]} /><Pagination {...cursor} next={page.next} />
    </>}</QueryView>
    {selected && <VersionDetails key={selected} id={selected} file={file} />}
  </>;
}

export default function FilePage() {
  const { fileId = "" } = useParams();
  const { scope } = useScope();
  const path = "/files/" + segment(fileId);
  const query = useRead<GetFileView>(keys.forScope(scope).file(fileId), path);
  return <section><h1>Файл</h1><QueryView query={query}>{file => {
    if (scope.workspaceId !== file.workspace_id || (file.project_id && scope.projectId !== file.project_id)) {
      return <Navigate replace to={withParams(path, { workspace_id: file.workspace_id, project_id: file.project_id })} />;
    }
    return <FileDetail key={file.file_id} file={file} reload={() => { void query.refetch(); }} />;
  }}</QueryView></section>;
}
