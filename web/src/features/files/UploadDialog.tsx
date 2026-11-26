import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import { useAuth } from "../../app/providers/AuthProvider";
import { ApiError } from "../../api/errors";
import { ClassificationValues, type AddFile, type AddFileResult, type AddFileVersion, type AddFileVersionResult, type Classification, type GetFileView } from "../../api/generated/artifacts";
import type { Uuid } from "../../api/generated/kernel";
import { useBlobTransport } from "../../api/hooks/artifacts";
import { segment, sendCommand, type Command } from "../../api/hooks/workspace";
import { newKey } from "../../api/idempotency";
import { keys } from "../../api/keys";
import { escapeText } from "../../lib/safeText";
import { ConflictPanel } from "../../components/feedback/ConflictPanel";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Dialog } from "../../components/primitives/Dialog";

type Rule = NonNullable<AddFile["acknowledge"]>[number];
const acknowledgeable: readonly Rule[] = ["CS-SECRET-NAME", "CS-SECRET-CONTENT", "CS-ABSOLUTE-PATH", "CS-HOME-PATH", "CS-BINARY", "CS-NOT-SCANNED", "CS-MEDIA-MISMATCH", "CS-EXECUTABLE"];

function blockedRules(error: unknown): Rule[] {
  if (!(error instanceof ApiError) || error.status !== 422 || error.code !== "CONTENT_UNSAFE") return [];
  if (error.details.reason === "portable_document_blocked") return [];
  const findings = error.details.findings;
  if (!Array.isArray(findings)) return [];
  const rules = new Set<Rule>();
  for (const item of findings) {
    if (item?.level !== "block") continue;
    const rule = acknowledgeable.find(rule => rule === item.rule);
    if (!rule) return [];
    rules.add(rule);
  }
  return [...rules];
}

interface UploadProps {
  workspaceId: string;
  projectId: string | null;
  existing?: GetFileView;
}

function UploadForm({ workspaceId, projectId, existing, close }: UploadProps & { close(): void }) {
  const { transport } = useAuth();
  const bytes = useBlobTransport();
  const client = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [stageKey, setStageKey] = useState(newKey);
  const [staged, setStaged] = useState<AddFile["blob"] | null>(null);
  const [title, setTitle] = useState("");
  const [classification, setClassification] = useState<Classification | "">("");
  const [unsafe, setUnsafe] = useState<ApiError | null>(null);
  const rules = blockedRules(unsafe);
  const belowFloor = unsafe?.details.reason === "classification_below_acknowledge_minimum";
  const canAcknowledge = rules.length > 0 && !(existing && belowFloor);
  const [confirmed, setConfirmed] = useState(false);
  // Pin the version the operator opened, even if SSE refreshes the parent.
  const [rowVersion] = useState(existing?.row_version);
  const lastCommit = useRef<{ payload: string; key: string } | null>(null);
  function commit<T>(command: Command) {
    const payload = JSON.stringify(command);
    if (lastCommit.current?.payload !== payload) lastCommit.current = { payload, key: newKey() };
    return sendCommand<T>(transport, { ...command, signal: bytes.sessionSignal() }, lastCommit.current.key);
  }
  const mutation = useMutation({
    retry: false,
    mutationFn: async () => {
      if (!file) throw new Error("Файл не выбран");
      const blob = staged ?? await bytes.stage(workspaceId, file, stageKey);
      setStaged(blob);
      const common = {
        blob, original_filename: file.name, declared_media_type: file.type || null, source: { kind: "upload" as const },
        ...(confirmed && rules.length ? { acknowledge: rules } : {}),
      } satisfies Omit<AddFileVersion, "file_id" | "expected_row_version">;
      if (existing && rowVersion !== undefined) {
        return commit<AddFileVersionResult>({
          path: `/files/${segment(existing.file_id)}/versions`, version: rowVersion, body: common,
        });
      }
      const body: AddFile = {
        ...common, workspace_id: workspaceId as Uuid, project_id: projectId as Uuid | null,
        title, origin: "upload", ...(classification ? { classification } : {}),
      };
      const resource = projectId ? "/projects/" + segment(projectId) : "/workspaces/" + segment(workspaceId);
      return commit<AddFileResult>({ path: resource + "/files", body });
    },
    onError: error => {
      if (!(error instanceof ApiError) || error.code !== "CONTENT_UNSAFE") return;
      const blocked = blockedRules(error);
      setUnsafe(error);
      setConfirmed(false);
      if (!existing && blocked.length && classification !== "restricted") setClassification("confidential");
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: keys.workspace(workspaceId) });
      close();
    },
  });
  const label = existing ? "Добавить версию" : "Загрузить файл";
  const conflict = mutation.error instanceof ApiError && mutation.error.code === "VERSION_CONFLICT" ? mutation.error : null;
  const canSubmit = unsafe === null || canAcknowledge;
  const submitDisabled = !file || !canSubmit || (canAcknowledge && !confirmed) || !!conflict;
  function submit(e: FormEvent) {
    e.preventDefault();
    if (submitDisabled || mutation.isPending) return;
    mutation.mutate();
  }
  return <Dialog open title={label} onClose={() => { if (!mutation.isPending) close(); }}>
    <form onSubmit={submit}>
      <fieldset disabled={mutation.isPending}>
        <label>Файл<input type="file" onChange={e => {
          const selected = e.target.files?.[0] ?? null;
          setFile(selected); setTitle(selected?.name ?? ""); setStaged(null); setStageKey(newKey());
          setConfirmed(false); setUnsafe(null); mutation.reset();
        }} /></label>
        {!existing && <>
          <label>Название<input required maxLength={300} value={title} onChange={e => { setTitle(e.target.value); mutation.reset(); }} /></label>
          <label>Классификация<select value={classification} onChange={e => { setClassification(e.target.value as Classification | ""); mutation.reset(); }}>
            <option value="">По умолчанию</option>
            {ClassificationValues.map(c => <option key={c}>{c}</option>)}
          </select></label>
        </>}
        {mutation.error && !conflict && <ErrorPanel error={mutation.error} />}
        {conflict && <ConflictPanel error={conflict} submitted={rowVersion} current={conflict.details} onReload={() => {
          void client.invalidateQueries({ queryKey: keys.workspace(workspaceId) });
          close();
        }} />}
        {Array.isArray(unsafe?.details.findings) && <ul>{unsafe.details.findings.map((finding, index) =>
          typeof finding?.rule === "string" && <li key={index}>{escapeText(finding.rule)}
            {typeof finding.detail === "string" && <> · {escapeText(finding.detail)}</>}</li>)}</ul>}
        {belowFloor && <p>{existing
          ? "Классификация текущего файла ниже минимума для подтверждения. Выберите другой файл для этой версии."
          : "Выберите более высокую классификацию для подтверждения."}</p>}
        {canAcknowledge && <label><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />Подтверждаю указанные риски</label>}
        {canSubmit && <Button type="submit" disabled={submitDisabled}>{canAcknowledge ? "Отправить с подтверждением" : label}</Button>}
      </fieldset>
    </form>
  </Dialog>;
}

export default function UploadDialog(props: UploadProps) {
  const [open, setOpen] = useState(false);
  return <>
    <Button onClick={() => setOpen(true)}>{props.existing ? "Добавить версию" : "Загрузить файл"}</Button>
    {open && <UploadForm {...props} close={() => setOpen(false)} />}
  </>;
}
