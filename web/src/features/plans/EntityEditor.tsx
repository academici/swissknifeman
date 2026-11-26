import { useEffect, useId, useRef } from "react";
import specification from "../../../../src/skm/schemas/planning/specification.v1.json";
import type { ExplainReportDefsKeyReport } from "../../api/generated/settings";
import { useDraftWorkPolicy } from "../../api/hooks/planning";
import { layerLabel } from "../../components/schema-form/ProvenanceBadge";
import { SchemaForm } from "../../components/schema-form/SchemaForm";
import { getAtPointer, isRecord, own, removeAtPointer, setAtPointer, type SchemaIssue } from "../../components/schema-form/values";
import { escapeText } from "../../lib/safeText";

export const entityKinds = {
  phases: "phase", items: "item", units: "unit", checks: "check", decisions: "decision",
  requirements: "requirement", criteria: "criterion", materials: "material",
} as const;
export type EntityList = keyof typeof entityKinds;
export type EntityKind = typeof entityKinds[EntityList];
export type EntityValue = Record<string, unknown>;

const urn = specification.$id;

function editableSchema(schema: EntityValue, fixedField: string | undefined): EntityValue {
  const properties = isRecord(schema.properties) ? { ...schema.properties } : {};
  const hidden = ["id", "work_policy", ...(fixedField ? [fixedField] : [])];
  for (const field of hidden) delete properties[field];
  // A check owner is a string matching either a phase or an item key.
  if (isRecord(properties.owner) && properties.owner.anyOf) properties.owner = { type: "string" };
  return {
    ...schema,
    ...(schema.properties ? { properties } : {}),
    ...(Array.isArray(schema.required) ? { required: schema.required.filter((field) => !hidden.includes(field)) } : {}),
    ...(Array.isArray(schema.oneOf) ? { oneOf: schema.oneOf.map((branch: EntityValue) => editableSchema(branch, fixedField)) } : {}),
  };
}

const registry = { [urn]: {
  ...specification,
  $defs: {
    ...specification.$defs,
    ...Object.fromEntries(Object.values(entityKinds).map((kind) => [kind, editableSchema(specification.$defs[kind], undefined)])),
    saved_item: editableSchema(specification.$defs.item, "phase"),
    saved_check: editableSchema(specification.$defs.check, "owner"),
  },
} };

const roles = ["scout", "executor", "reviewer", "triager", "advisor", "researcher", "registrar"] as const;
const intensities = ["light", "medium", "heavy"];

export function fieldIssues(issues: unknown): SchemaIssue[] {
  if (!Array.isArray(issues)) return [];
  return issues.flatMap((issue: unknown) => {
    const pointer = own(issue, "pointer"), message = own(issue, "message");
    return typeof pointer === "string" && typeof message === "string"
      ? [{ pointer, message, code: "SCHEMA_INVALID" }] : [];
  });
}

function PolicyField({ label, value, pointer, report, role, inherited, issues, readOnly, onChange }: {
  label: string;
  value: unknown;
  pointer: string;
  report: ExplainReportDefsKeyReport | undefined;
  role?: string;
  inherited: unknown;
  issues: readonly SchemaIssue[];
  readOnly: boolean;
  onChange(value: string): void;
}) {
  const issueId = useId();
  const setting = role ? own(report?.value, role) : report?.value;
  const sources = report?.contributions.filter((entry) =>
    (entry.status === "winner" || entry.status === "used") && (!role || own(entry.value, role) === setting));
  const source = sources?.at(-1)?.layer ?? report?.winner;
  const inheritedValue = typeof inherited === "string" ? inherited : setting;
  return <div data-pointer={escapeText(pointer)}>
    <label>{label} <select value={typeof value === "string" ? value : ""} onChange={(event) => onChange(event.target.value)}
      disabled={readOnly} aria-invalid={issues.length ? true : undefined} aria-describedby={issues.length ? issueId : undefined}>
      <option value="">Наследовать</option>
      {intensities.map((intensity) => <option key={intensity}>{intensity}</option>)}
    </select></label>
    {typeof value === "string" && <small> Запрошено {escapeText(value)}.</small>}
    {typeof inheritedValue === "string" && <small> Наследуется {escapeText(inheritedValue)}
      {typeof inherited === "string" ? " от Item" : source && ` · ${escapeText(layerLabel(source))}`}.</small>}
    {report?.locked_by && <small> Блокировка · {escapeText(layerLabel(report.locked_by))}.</small>}
    {!!issues.length && <ul role="alert" id={issueId}>{issues.map((issue, i) =>
      <li key={i}>{escapeText(issue.message)}</li>)}</ul>}
  </div>;
}

function WorkPolicy({ planId, value, item, pointer, issues, readOnly, onChange }: {
  planId: string; value: EntityValue; item: EntityValue | undefined; pointer: string;
  issues: readonly SchemaIssue[]; readOnly: boolean; onChange(value: EntityValue): void;
}) {
  const explain = useDraftWorkPolicy(planId);
  const reports = explain.data?.keys;
  const roleReport = reports?.find((entry) => entry.key === "execution.work_policy.role_intensity");
  const verificationReport = reports?.find((entry) => entry.key === "execution.work_policy.verification_intensity");
  function field(path: string, label: string, report: ExplainReportDefsKeyReport | undefined, role?: string) {
    const absolute = pointer + path;
    return <PolicyField key={path} label={label} value={getAtPointer(value, path)} pointer={absolute}
      inherited={getAtPointer(item, path)} report={report} {...(role === undefined ? {} : { role })}
      issues={issues.filter((issue) => issue.pointer === absolute)} readOnly={readOnly}
      onChange={(next) => {
        const updated = next ? setAtPointer(value, path, next) : removeAtPointer(value, path);
        if (isRecord(updated)) onChange(updated);
      }} />;
  }
  return <fieldset data-pointer={`${pointer}/work_policy`}>
    <legend>Интенсивность работы</legend>
    {explain.isPending && <small>Загрузка настроек наследования…</small>}
    {explain.error && <small>Источник наследования недоступен.</small>}
    {issues.filter((issue) => ["/work_policy", "/work_policy/role_intensity"].some((path) => issue.pointer === pointer + path))
      .map((issue, index) => <p role="alert" key={index}>{escapeText(issue.message)}</p>)}
    {roles.map((role) => field(`/work_policy/role_intensity/${role}`, role, roleReport, role))}
    {field("/work_policy/verification_intensity", "verification_intensity", verificationReport)}
  </fieldset>;
}

export function EntityEditor({ planId, kind, pointer, value, item, issues, focus, readOnly, onChange }: {
  planId: string;
  kind: EntityKind;
  pointer: string;
  value: EntityValue;
  item: EntityValue | undefined;
  issues: readonly SchemaIssue[];
  focus: { pointer: string } | null;
  readOnly: boolean;
  onChange(value: EntityValue): void;
}) {
  const root = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!focus || !root.current) return;
    const path = escapeText(focus.pointer);
    const fields = Array.from(root.current.querySelectorAll<HTMLElement>("[data-pointer]"));
    const match = fields.filter((field) => {
      const location = field.dataset.pointer ?? "";
      return path === location || path.startsWith(location + "/");
    }).sort((left, right) => (right.dataset.pointer?.length ?? 0) - (left.dataset.pointer?.length ?? 0))[0] ?? root.current;
    for (let parent = match.closest("details"); parent; parent = parent.parentElement?.closest("details") ?? null) parent.open = true;
    const previous = match.style.outline;
    match.style.outline = "2px solid var(--focus)";
    match.scrollIntoView?.({ block: "nearest" });
    const control = match.querySelector<HTMLElement>("input, textarea, select, button");
    if (control && !control.matches(":disabled")) control.focus();
    else { match.tabIndex = -1; match.focus(); }
    return () => { match.style.outline = previous; };
  }, [pointer, focus]);

  const fixed = value.id && kind === "item" ? "phase" : value.id && kind === "check" ? "owner" : undefined;
  const definition = fixed ? `saved_${kind}` : kind;
  const withPolicy = kind === "item" || kind === "unit";
  const entityIssues = issues.filter((issue) => issue.pointer === pointer || issue.pointer.startsWith(pointer + "/"));
  const policyPointer = pointer + "/work_policy";
  const policyFields = [policyPointer, policyPointer + "/role_intensity", policyPointer + "/verification_intensity",
    ...roles.map((role) => `${policyPointer}/role_intensity/${role}`)];
  return <section ref={root} aria-label="Поля сущности">
    {fixed && <p>{fixed} · {escapeText(String(value[fixed] ?? ""))}</p>}
    <SchemaForm schema={{ $ref: `${urn}#/$defs/${definition}` }} registry={registry} pointer={pointer}
      label={kind} value={value} readOnly={readOnly}
      issues={entityIssues.filter((issue) => !withPolicy || !policyFields.includes(issue.pointer))}
      onChange={(next) => {
        if (isRecord(next)) onChange({ ...next, ...(value.id === undefined ? {} : { id: value.id }), ...(fixed ? { [fixed]: value[fixed] } : {}) });
      }} />
    {withPolicy && <WorkPolicy planId={planId} value={value} item={item} pointer={pointer} issues={entityIssues}
      readOnly={readOnly} onChange={onChange} />}
  </section>;
}
