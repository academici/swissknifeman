import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import type { Uuid } from "../../api/generated/kernel";
import type { CreatePlan, CreatePlanResult, DesignPlan } from "../../api/generated/planning";
import { isUuid, planPath, useCreatePlan, useDesignPlan, useDraft, useOpenDraft, usePlan, usePlanProject, useSaveDraft, useTemplate, useTemplates } from "../../api/hooks/planning";
import { SafeLink } from "../../components/content/SafeLink";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Dialog } from "../../components/primitives/Dialog";
import { Skeleton } from "../../components/primitives/Skeleton";
import { SchemaForm } from "../../components/schema-form/SchemaForm";
import { isRecord } from "../../components/schema-form/values";
import { escapeText } from "../../lib/safeText";
import { DesignResearch } from "./DesignResearch";
import { PlanCommandError } from "./RevisionsTab";

function validInputs(value: unknown): value is NonNullable<CreatePlan["template_inputs"]> {
  return isRecord(value) && Object.values(value).every((entry) =>
    typeof entry === "string" || typeof entry === "boolean" || Number.isInteger(entry));
}

export default function CreatePlanWizard({ projectId, canDesign, canResearch, onClose }: {
  projectId: string; canDesign: boolean; canResearch: boolean; onClose(): void;
}) {
  const navigate = useNavigate();
  const [intake, setIntake] = useState(false);
  const [title, setTitle] = useState("");
  const [key, setKey] = useState("");
  const [inputs, setInputs] = useState<unknown>({});
  const templates = useTemplates(projectId);
  const template = useTemplate(projectId, key);
  const create = useCreatePlan(projectId);
  const created = create.data;
  const open = useOpenDraft();
  const project = usePlanProject(projectId);
  const plan = usePlan(created?.plan_id ?? "", false);
  const busy = create.isPending || open.isPending || project.isFetching || plan.isFetching;

  const go = (plan: string, draft: string) => { void navigate(planPath(plan) + "/drafts/" + encodeURIComponent(draft)); };
  function openEmpty(plan: Uuid) {
    open.mutate({ plan_id: plan, base: "empty" }, { onSuccess: (draft) => go(plan, draft.draft_id) });
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || !title.trim() || (key && !template.isSuccess) || !validInputs(inputs)) return;
    create.mutate({ title: title.trim(), ...(key ? { template_key: key, template_inputs: inputs } : {}) }, {
      onSuccess: (result) => {
        if (intake) return;
        if (result.draft_id) go(result.plan_id, result.draft_id);
        else openEmpty(result.plan_id);
      },
    });
  }
  if (intake && created) {
    return <IntakeStep projectId={projectId} created={created} canResearch={canResearch} onClose={onClose} />;
  }
  return (
    <Dialog open title="Создать план" onClose={() => { if (!busy) onClose(); }}>
      {created ? <div>
        <SafeLink href={planPath(created.plan_id)}>{created.alias}</SafeLink>
        {open.error && <PlanCommandError error={open.error} submitted={open.variables} reload={() => {
          void plan.refetch().then((result) => { if (result.isSuccess) open.reset(); });
        }} />}
        {busy ? <Skeleton /> : <Button onClick={() => openEmpty(created.plan_id)}>Открыть черновик</Button>}
      </div> : <form onSubmit={submit}>
        <label>Название плана <input required maxLength={300} value={title} onChange={(e) => setTitle(e.target.value)} /></label>
        <label>Шаблон <select value={key} onChange={(e) => { setKey(e.target.value); setInputs({}); }}>
          <option value="">Пустой план</option>
          {templates.data?.map((name) => <option key={name} value={name}>{escapeText(name)}</option>)}
        </select></label>
        {templates.error && <ErrorPanel error={templates.error} onRetry={() => void templates.refetch()} />}
        {key && (template.isError ? <ErrorPanel error={template.error} onRetry={() => void template.refetch()} />
          : template.data ? <SchemaForm schema={template.data} value={inputs} onChange={setInputs} serverError={create.error} /> : <Skeleton />)}
        {canDesign && <label><input type="checkbox" checked={intake} disabled={busy}
          onChange={event => setIntake(event.target.checked)} />Заполнить дизайн-бриф</label>}
        {create.error && <PlanCommandError error={create.error} submitted={create.variables} reload={() => {
          void project.refetch().then((result) => { if (result.isSuccess) create.reset(); });
        }} />}
        <Button type="submit" disabled={busy || !title.trim() || (!!key && !template.isSuccess) || !validInputs(inputs)}>Создать</Button>
      </form>}
    </Dialog>
  );
}

function IntakeStep({ projectId, created, canResearch, onClose }: {
  projectId: string; created: CreatePlanResult; canResearch: boolean; onClose(): void;
}) {
  const navigate = useNavigate();
  const planId = created.plan_id;
  const [goal, setGoal] = useState("");
  const [context, setContext] = useState("");
  const [constraints, setConstraints] = useState("");
  const [versionIds, setVersionIds] = useState("");
  const [references, setReferences] = useState<NonNullable<DesignPlan["research_references"]>>([]);
  const design = useDesignPlan(planId);
  const open = useOpenDraft();
  const draftId = created.draft_id ?? open.data?.draft_id ?? "";
  const version = created.edit_version ?? open.data?.edit_version;
  const save = useSaveDraft(planId, draftId);
  const current = useDraft(planId, draftId, false);
  const [reloadedVersion, setReloadedVersion] = useState<number>();
  const [existingBrief, setExistingBrief] = useState(false);
  const busy = design.isPending || open.isPending || save.isPending || current.isFetching;
  const draftUrl = `${planPath(planId)}/drafts/${encodeURIComponent(draftId)}`;
  const fileIds = [...new Set(versionIds.trim().toLowerCase().split(/[,\s]+/).filter(Boolean))];
  const rules = [...new Set(constraints.split("\n").map(line => line.trim()).filter(Boolean))];
  const validFileIds = fileIds.filter(isUuid);
  const validFiles = fileIds.length <= 100 && fileIds.length === validFileIds.length;
  const validRules = rules.length <= 100 && rules.every(line => line.length <= 4000);

  function attach() {
    const editVersion = reloadedVersion ?? version;
    if (busy || !editVersion || !design.data || !draftId || existingBrief) return;
    save.mutate({
      expected_edit_version: editVersion,
      merge_patch: { design_brief_id: design.data.design_brief_id },
    }, { onSuccess: () => { void navigate(draftUrl); } });
  }

  return <Dialog open title="Дизайн-бриф" onClose={() => { if (!busy) onClose(); }}>
    <p><SafeLink href={planPath(planId)}>{created.alias}</SafeLink></p>
    {design.data ? <>
      <p>Бриф сохранён <code>{escapeText(design.data.design_brief_id)}</code></p>
      {!draftId ? <Button disabled={busy} onClick={() => open.mutate({ plan_id: planId, base: "empty" })}>
        Открыть черновик</Button> : <>
        <Button disabled={busy || existingBrief || !version} onClick={attach}>Связать бриф с черновиком</Button>
        <SafeLink href={draftUrl}>Перейти к черновику</SafeLink>
      </>}
      {open.error && <ErrorPanel error={open.error} />}
      {save.error && <PlanCommandError error={save.error} submitted={save.variables} reload={() => {
        void current.refetch().then(response => {
          if (!response.isSuccess) return;
          const draft = response.data.data;
          if (draft.document.design_brief_id === design.data.design_brief_id) {
            void navigate(draftUrl);
          } else {
            setExistingBrief(!!draft.document.design_brief_id);
            setReloadedVersion(draft.edit_version);
            save.reset();
          }
        });
      }} />}
      {current.error && <ErrorPanel error={current.error} />}
      {existingBrief && <p role="alert">У черновика уже есть дизайн-бриф.</p>}
    </> : <form onSubmit={event => {
      event.preventDefault();
      if (busy || !goal.trim() || !validFiles || !validRules) return;
      design.mutate({ goal: goal.trim(), context_md: context, constraints: rules,
        rag_file_version_ids: validFileIds, research_references: references });
    }}>
      <fieldset disabled={busy}>
        <label>Цель <textarea required maxLength={20000} value={goal} onChange={event => setGoal(event.target.value)} /></label>
        <label>Контекст (Markdown) <textarea maxLength={100000} value={context}
          onChange={event => setContext(event.target.value)} /></label>
        <label>Ограничения, по одному в строке <textarea value={constraints}
          onChange={event => setConstraints(event.target.value)} /></label>
        {!validRules && <p role="alert">Введите до 100 ограничений, до 4000 символов в каждом.</p>}
        <label>ID версий файлов RAG <input value={versionIds} onChange={event => setVersionIds(event.target.value)} /></label>
        {!validFiles && <p role="alert">Укажите до 100 UUID через запятую или пробел.</p>}
      </fieldset>
      {canResearch && <fieldset disabled={busy}>
        <DesignResearch projectId={projectId} planId={planId} references={references} onChange={setReferences} />
      </fieldset>}
      {design.error && <ErrorPanel error={design.error} />}
      <Button type="submit" disabled={busy || !goal.trim() || !validFiles || !validRules}>Сохранить бриф</Button>
    </form>}
  </Dialog>;
}
