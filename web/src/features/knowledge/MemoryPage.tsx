import { useState } from "react";
import { ApiError } from "../../api/errors";
import type { Uuid } from "../../api/generated/kernel";
import { useHandoffPredecessor, useKnowledgePermissions, useMemory } from "../../api/hooks/knowledge";
import { useAuth } from "../../app/providers/AuthProvider";
import { useScope } from "../../app/providers/ScopeProvider";
import { ConflictPanel } from "../../components/feedback/ConflictPanel";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { escapeText } from "../../lib/safeText";

function Recall({ project, reset }: { project: string; reset(): void }) {
  const [shared, setShared] = useState(false);
  const [draft, setDraft] = useState<{ body: string; predecessor: Uuid | null } | null>(null);
  const [submitted, setSubmitted] = useState("");
  const { recall, remember } = useMemory(project, shared);
  const identity = useKnowledgePermissions(project);
  const writable = identity?.modules.knowledge && identity.effective_permissions.includes("memory.write");
  const conflict = remember.error instanceof ApiError && remember.error.code === "VERSION_CONFLICT" ? remember.error : undefined;
  const predecessor = useHandoffPredecessor(project, conflict?.requestId);
  const canReplace = predecessor.isSuccess && !predecessor.isFetching;
  return <>
    <label><input type="checkbox" checked={shared} onChange={e => setShared(e.target.checked)} />Включить общую память</label>
    {recall.error && <ErrorPanel error={recall.error} />}
    {recall.data && <ul>{recall.data.items.map(entry => <li key={entry.id}>
      <strong>{escapeText(entry.kind)}</strong> · {escapeText(entry.scope.namespace ?? entry.scope.kind)}
      <p>{escapeText(entry.body)}</p>
      {writable && !draft && entry.kind === "active_handoff" && entry.scope.kind === "project" &&
        <Button onClick={() => setDraft({ body: entry.body, predecessor: entry.id })}>Изменить передачу</Button>}
    </li>)}</ul>}
    {recall.data?.items.length === 0 && <p>Записей нет.</p>}
    {recall.data?.truncated && <p>Показана часть найденных записей.</p>}
    {writable && !draft && <Button onClick={() => setDraft({ body: "", predecessor: null })}>Новая передача</Button>}
    {conflict && <ConflictPanel error={conflict} submitted={submitted}
      current={predecessor.isSuccess ? predecessor.data?.body ?? "Активной передачи нет." : "Загрузка текущей передачи"}
      onReload={() => { void predecessor.refetch(); }} />}
    {conflict && predecessor.error && <ErrorPanel error={predecessor.error} />}
    {writable && draft && <form onSubmit={e => {
      e.preventDefault();
      if (remember.status === "pending" || remember.status === "success" || (conflict && !canReplace)) return;
      setSubmitted(draft.body);
      remember.submit({ ...draft, predecessor: conflict ? predecessor.data?.id ?? null : draft.predecessor });
    }}>
      <label>Текст передачи<textarea required maxLength={800} value={draft.body}
        disabled={remember.status === "pending" || remember.status === "success"}
        onChange={e => setDraft({ ...draft, body: e.target.value })} /></label>
      <Button type="submit" disabled={remember.status === "pending" || remember.status === "success" || (conflict && !canReplace)}>
        {conflict ? "Сохранить с учётом текущей версии" : "Сохранить"}
      </Button>
    </form>}
    {remember.error && !conflict && <ErrorPanel error={remember.error} />}
    {remember.status === "success" && <><p role="status">Передача сохранена.</p><Button onClick={reset}>Готово</Button></>}
  </>;
}

export default function MemoryPage() {
  const { scope } = useScope();
  const [revision, reset] = useState(0);
  const { me } = useAuth();
  if (!me?.modules.knowledge) return null;
  return <section><h1>Память</h1>{scope.projectId ?
    <Recall key={scope.projectId + ":" + revision} project={scope.projectId} reset={() => reset(n => n + 1)} /> : <p>Выберите проект.</p>}</section>;
}
