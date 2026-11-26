import { useState } from "react";
import type { LessonView } from "../../api/generated/knowledge";
import { useKnowledgePermissions, useLessons } from "../../api/hooks/knowledge";
import { useAuth } from "../../app/providers/AuthProvider";
import { useScope } from "../../app/providers/ScopeProvider";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { escapeText } from "../../lib/safeText";

function conflicts(lesson: LessonView): string {
  if (!("potential_conflict_ids" in lesson) || !Array.isArray(lesson.potential_conflict_ids)) return "Неизвестно";
  return lesson.potential_conflict_ids.filter((id): id is string => typeof id === "string").map(escapeText).join(", ") || "Нет";
}

function Lessons({ workspace, project }: { workspace: string; project: string | null }) {
  const identity = useKnowledgePermissions(workspace);
  const [after, setAfter] = useState<string | null>(null);
  const [selected, select] = useState<LessonView | null>(null);
  const [reason, setReason] = useState("");
  const { lessons, deprecate } = useLessons(workspace, project, after);
  const curate = identity?.principal.kind === "human" && identity.modules.knowledge &&
    identity.effective_permissions.includes("lesson.curate");
  return <>
    {lessons.error && <ErrorPanel error={lessons.error} />}
    {lessons.data?.items.map(lesson => <article key={lesson.id}>
      <h2>{escapeText(lesson.trigger)}</h2><p>{escapeText(lesson.action)}</p>
      <dl>
        <dt>Применимость</dt><dd>{escapeText(lesson.applicability?.applies_to ?? "Неизвестно")}</dd>
        <dt>Проверенные версии</dt><dd>{escapeText(lesson.applicability?.validated_versions?.map(pair => pair.join(" ")).join(", ") || "Неизвестно")}</dd>
        <dt>Актуальность</dt><dd>{escapeText("freshness" in lesson && typeof lesson.freshness === "string" ? lesson.freshness : "Неизвестно")}</dd>
        <dt>Возможные конфликты</dt><dd>{conflicts(lesson)}</dd>
        <dt>Source association</dt><dd>{lesson.confidence} ({escapeText(lesson.confidence_tier)})</dd>
        <dt>Проверка</dt><dd>{escapeText(lesson.review_flag)}</dd>
        <dt>Статус</dt><dd>{escapeText(lesson.state)}</dd>
      </dl>
      {curate && lesson.state === "curated" && <Button onClick={() => { select(lesson); setReason(""); }}>Пометить устаревшим</Button>}
    </article>)}
    {lessons.data?.items.length === 0 && <p>Уроков нет.</p>}
    {lessons.data?.next_cursor && <Button onClick={() => setAfter(lessons.data.next_cursor)}>Далее</Button>}
    {curate && selected && <form onSubmit={e => {
      e.preventDefault(); deprecate.submit({ lesson: selected, reason }); select(null);
    }}>
      <label>Причина для «{escapeText(selected.trigger)}»<input required maxLength={500} value={reason}
        onChange={e => setReason(e.target.value)} /></label>
      <Button type="submit">Подтвердить</Button>
    </form>}
    {deprecate.error && <ErrorPanel error={deprecate.error} />}
  </>;
}

export default function LessonsPage() {
  const { scope } = useScope();
  const { me } = useAuth();
  if (!me?.modules.knowledge) return null;
  return <section><h1>Уроки</h1>{scope.workspaceId ?
    <Lessons key={JSON.stringify([scope.workspaceId, scope.projectId])} workspace={scope.workspaceId} project={scope.projectId} /> :
    <p>Выберите рабочее пространство.</p>}</section>;
}
