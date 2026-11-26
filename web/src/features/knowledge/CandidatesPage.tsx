import { useState, type FormEvent } from "react";
import { ApiError } from "../../api/errors";
import type { CandidateView, ReviewCandidate } from "../../api/generated/learning";
import { useKnowledgePermissions } from "../../api/hooks/knowledge";
import { useCandidate, useCandidateList } from "../../api/hooks/learning";
import { useAuth } from "../../app/providers/AuthProvider";
import { useScope } from "../../app/providers/ScopeProvider";
import { EmptyState } from "../../components/data/EmptyState";
import { JsonView } from "../../components/data/JsonView";
import { KeyValue } from "../../components/data/KeyValue";
import { ConflictPanel } from "../../components/feedback/ConflictPanel";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { ConfirmDialog } from "../../components/primitives/ConfirmDialog";
import { Dialog } from "../../components/primitives/Dialog";
import { escapeText } from "../../lib/safeText";

type ReviewFields = Omit<ReviewCandidate, "workspace_id" | "candidate_id" | "expected_row_version">;
type Proposal = CandidateView["proposals"][number];

function ReviewForm({ proposal, submit }: { proposal: Proposal | null; submit(body: ReviewFields): void }) {
  const [verdict, setVerdict] = useState<ReviewCandidate["verdict"]>(proposal ? "edit" : "approve");

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const note = String(form.get("note") ?? "").trim();
    const trigger = String(form.get("trigger") ?? "").trim();
    const action = String(form.get("action") ?? "").trim();
    if (verdict === "edit" && !trigger && !action) return;
    submit({
      verdict, ...(note && { note }), ...(proposal && { proposal_id: proposal.id }),
      ...(trigger && { edited_trigger: trigger }), ...(action && { edited_action: action }),
    });
  }

  return <form onSubmit={onSubmit}>
    <label>Решение <select value={verdict} onChange={e => setVerdict(e.target.value as ReviewCandidate["verdict"])}>
      {!proposal && <option value="approve">Одобрить</option>}
      <option value="reject">Отклонить</option>
      <option value="edit">Изменить формулировку</option>
      {!proposal && <option value="comment">Комментировать</option>}
    </select></label>
    {verdict === "edit" && <>
      <label>Условие <input name="trigger" maxLength={500} defaultValue={proposal?.trigger} /></label>
      <label>Действие <textarea name="action" maxLength={1000} defaultValue={proposal?.action} /></label>
    </>}
    <label>Заметка <textarea name="note" maxLength={2000} /></label>
    <Button type="submit">Сохранить решение</Button>
  </form>;
}

function CandidateDetails({ workspace, id, curate, select }: {
  workspace: string; id: string; curate: boolean; select(id: string): void;
}) {
  const [proposalsAfter, setProposalsAfter] = useState<string | null>(null);
  const [signalsAfter, setSignalsAfter] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState<Proposal | null | undefined>(undefined);
  const [promoting, setPromoting] = useState(false);
  const [resolution, setResolution] = useState<"keep_both" | "supersede">("keep_both");
  const [submittedVersion, setSubmittedVersion] = useState<number>();
  const { detail, signals, review, promote } = useCandidate(workspace, id, proposalsAfter, signalsAfter);
  if (detail.error) return <ErrorPanel error={detail.error} />;
  const c = detail.data;
  if (!c) return <p role="status">Загрузка кандидата…</p>;
  const mutationError = review.error ?? promote.error;
  const isConflict = mutationError instanceof ApiError && (mutationError.isConflict() || mutationError.status === 412);
  const canPromote = c.state === "candidate" || c.state === "observed";
  return <article>
    <h2>{escapeText(c.trigger)}</h2>
    <p>{escapeText(c.action)}</p>
    {c.review_hint && <p>{escapeText(c.review_hint)}</p>}
    <dl>
      <KeyValue label="Статус" value={c.state} />
      <KeyValue label="Source association" value={`${c.confidence} (${c.confidence_tier})`} />
      <KeyValue label="Покрытие исходов" value={`${c.known_outcome_total} / ${c.n_total}`} />
      <KeyValue label="Неизвестные исходы" value={c.unknown_outcome_total} />
      <KeyValue label="Урок уже показывался" value={c.exposed_total} />
      <KeyValue label="Неизвестный показ уроков" value={c.exposure_unknown_total} />
      <KeyValue label="Независимые подтверждения" value={c.independent_known_total} />
      <KeyValue label="Актуальность" value={`${c.freshness} (${c.days_since} дн.)`} />
    </dl>
    <h3>Пороги</h3>
    <JsonView value={c.gates} />
    {curate && c.state !== "promoted" && <Button onClick={() => setReviewing(null)}>Рецензировать</Button>}
    {curate && canPromote && <Button onClick={() => { setResolution("keep_both"); setPromoting(true); }}>Создать урок</Button>}
    {c.proposals.length > 0 && <h3>Варианты формулировки</h3>}
    {c.proposals.map(proposal => {
      const addressed = c.reviews.some(r => r.proposal_id === proposal.id && r.reviewer_kind === "human" &&
        (r.verdict === "edit" || r.verdict === "reject"));
      return <section key={proposal.id}>
        <h4>{proposal.relation === "conflict" ? "CONFLICT" : "UPDATE"}</h4>
        <p>{escapeText(proposal.trigger)}</p><p>{escapeText(proposal.action)}</p>
        <Button onClick={() => select(proposal.source_candidate_id)}>Открыть вариант</Button>
        {curate && !addressed && <Button onClick={() => setReviewing(proposal)}>Рецензировать вариант</Button>}
      </section>;
    })}
    {c.proposals_next && <Button onClick={() => setProposalsAfter(c.proposals_next ?? null)}>Следующие варианты</Button>}
    {c.similar.length > 0 && <section>
      <h3>Похожие кандидаты</h3>
      <ul>{c.similar.map(item => <li key={item.candidate_id}>
        <Button onClick={() => select(item.candidate_id)}>{escapeText(item.candidate_id)}</Button>
        {" "}{item.tsim} / {item.asim}
      </li>)}</ul>
    </section>}
    {c.reviews.length > 0 && <section><h3>Рецензии</h3><ul>{c.reviews.map(r =>
      <li key={r.id}>{escapeText(r.verdict)} {r.note && escapeText(r.note)}</li>)}</ul></section>}
    <h3>Сигналы</h3>
    {signals.error && <ErrorPanel error={signals.error} />}
    {signals.data?.items.map(signal => <section key={signal.signal_id}>
      <p>{escapeText(signal.activity.source_kind)} · {escapeText(signal.activity.outcome)} · {escapeText(signal.evidence_dependency)}</p>
      <JsonView value={signal.activity.detector_evidence} />
    </section>)}
    {signals.data?.next_cursor && <Button onClick={() => setSignalsAfter(signals.data?.next_cursor ?? null)}>Следующие сигналы</Button>}
    {curate && reviewing !== undefined && <Dialog open title="Рецензировать кандидата" onClose={() => setReviewing(undefined)}>
      <ReviewForm proposal={reviewing} submit={body => {
        setSubmittedVersion(c.row_version);
        review.submit({ rowVersion: c.row_version, body });
        setReviewing(undefined);
      }} />
    </Dialog>}
    {curate && promoting && <ConfirmDialog open title="Создать урок" description={c.trigger} confirmLabel="Подтвердить создание"
      requireReason={c.state === "observed"} onClose={() => setPromoting(false)} onConfirm={reason => {
        setSubmittedVersion(c.row_version);
        promote.submit({ rowVersion: c.row_version, body: {
          ...(c.state === "observed" && { override_low_confidence: true, override_reason: reason }),
          ...(c.conflicts_with_id && { resolve_conflict: resolution }),
        } });
        setPromoting(false);
      }}>
      {c.conflicts_with_id && <label>Конфликт формулировок <select value={resolution}
        onChange={e => setResolution(e.target.value as typeof resolution)}>
        <option value="keep_both">Сохранить оба</option><option value="supersede">Заменить прежний урок</option>
      </select></label>}
    </ConfirmDialog>}
    {mutationError && (isConflict ? <ConflictPanel error={mutationError} submitted={{ row_version: submittedVersion }} current={c}
      onReload={() => { void detail.refetch(); }} /> : <ErrorPanel error={mutationError} />)}
  </article>;
}

function Candidates({ workspace, project }: { workspace: string; project: string | null }) {
  const identity = useKnowledgePermissions(workspace);
  const [after, setAfter] = useState<string | null>(null);
  const [state, setState] = useState("candidate");
  const [selected, select] = useState<string | null>(null);
  const list = useCandidateList(workspace, project, state, after);
  const curate = identity?.principal.kind === "human" && identity.modules.learning &&
    identity.effective_permissions.includes("lesson.curate");
  return <>
    <label>Статус кандидатов <select value={state} onChange={event => {
      setState(event.target.value); setAfter(null); select(null);
    }}>
      <option value="candidate">Кандидаты</option><option value="observed">Наблюдения</option>
      <option value="promoted">Продвинутые</option><option value="rejected">Отклонённые</option>
      <option value="deprecated">Устаревшие</option>
    </select></label>
    {list.error && <ErrorPanel error={list.error} />}
    {list.data?.items.length === 0 && <EmptyState title="Кандидатов нет" />}
    {list.data && list.data.items.length > 0 && <ul>{list.data.items.map(c =>
      <li key={c.candidate_id}><Button onClick={() => select(c.candidate_id)}>
        {escapeText(c.display_key)} {escapeText(c.trigger)}
      </Button></li>)}</ul>}
    {list.data?.next_cursor && <Button onClick={() => setAfter(list.data?.next_cursor ?? null)}>Следующие кандидаты</Button>}
    {selected && <CandidateDetails key={selected} workspace={workspace} id={selected} curate={curate === true} select={select} />}
  </>;
}

export default function CandidatesPage() {
  const { scope } = useScope();
  const { me } = useAuth();
  if (!me?.modules.learning) return null;
  return <section><h1>Обучение</h1>{scope.workspaceId ?
    <Candidates key={JSON.stringify([scope.workspaceId, scope.projectId])} workspace={scope.workspaceId}
      project={scope.projectId} /> : <p>Выберите рабочее пространство.</p>}</section>;
}
