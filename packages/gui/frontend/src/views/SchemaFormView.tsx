import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { Run, RunRequest, ViewData } from "../contracts";
import { useCatalog } from "../app/catalog";
import { ErrorPanel } from "../app/ErrorView";
import { ApiError } from "../transport/ApiError";
import { useTransport } from "../transport/context";
import { PLAN_ENUMS } from "./plan-enums";

type SchemaForm = Extract<ViewData, { view: "schema-form" }>;
type Doc = Record<string, unknown>;

const RUN_API = "urn:swissknifeman:gui:run-api:v1";
const ENDED = new Set(["denied", "failed_to_start", "succeeded", "failed", "cancelled", "timed_out", "lost"]);
/** Identity and lifecycle fields are never edited by a form: they stay read-only whatever the annotation says (I7). */
export const LOCKED_ROOTS = new Set(["$schema", "id", "status", "result", "updated_at", "units", "artifacts", "sections"]);
/** What the form of a contribution writes with and reads again from. */
const EDITORS: Record<string, { command: string; query: string }> = {
  "gui-planner.item": { command: "gui-planner.item-set", query: "gui-planner.item-form" },
};
const MESSAGES: Record<string, string> = {
  ITEM_IN_PROGRESS: "The item is being executed. Edit it after it stops.",
  FIELD_NOT_EDITABLE: "One of the changed fields cannot be edited here.",
  FIELD_OWNED: "One of the changed fields belongs to the planner lifecycle.",
  SCHEMA_INVALID: "The planner refused the values: they do not fit the item schema.",
  PLAN_LOCKED: "Another process is writing the plan. Save again in a moment.",
};

const parts = (pointer: string) => pointer.split("/").slice(1);
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
const isObject = (value: unknown): value is Doc => typeof value === "object" && value !== null && !Array.isArray(value);

export function valueAt(doc: Doc, pointer: string): unknown {
  let current: unknown = doc;
  for (const key of parts(pointer)) {
    if (!isObject(current)) return undefined;
    current = current[key];
  }
  return current;
}

/** The RFC 7386 merge patch that turns `old` into `value`: a removed object key is `null`, an array or a scalar replaces. */
function diff(old: unknown, value: unknown): unknown {
  if (value === undefined) return null;
  if (!isObject(value) || !isObject(old)) return value;
  const out: Doc = {};
  for (const key of Object.keys(old)) if (!(key in value)) out[key] = null;
  for (const [key, entry] of Object.entries(value)) if (!same(old[key], entry)) out[key] = diff(old[key], entry);
  return out;
}

function putAt(patch: Doc, keys: string[], value: unknown): void {
  let object = patch;
  for (const key of keys.slice(0, -1)) {
    const next = object[key];
    if (isObject(next)) object = next;
    else object = object[key] = {};
  }
  object[keys[keys.length - 1]!] = value;
}

/** A merge patch (RFC 7386) of the changed fields only, down to the nested key: a removed value is `null`, the
 * unchanged fields and the locked roots never. Empty when nothing changed. */
export function buildPatch(doc: Doc, edits: Record<string, unknown>): Doc {
  const patch: Doc = {};
  for (const [pointer, value] of Object.entries(edits)) {
    const keys = parts(pointer);
    if (keys[0] === undefined || LOCKED_ROOTS.has(keys[0]) || same(valueAt(doc, pointer), value)) continue;
    if (value === "" && valueAt(doc, pointer) === undefined) continue;
    putAt(patch, keys, diff(valueAt(doc, pointer), value));
  }
  return patch;
}

interface Model {
  id: string;
  provider: string;
}

function useModels(projectId: string | undefined, enabled: boolean) {
  const transport = useTransport();
  return useQuery({
    queryKey: ["models", projectId],
    enabled: enabled && Boolean(projectId),
    queryFn: async (): Promise<Model[]> => {
      const answer = await transport.request<ViewData>("POST", "/v1/queries/gui-planner.models", { context: { project_id: projectId }, params: {} });
      if (answer.view !== "resource-list") return [];
      return answer.rows.map((row) => ({ id: row.id, provider: String(row.cells.provider ?? "") }));
    },
  });
}

function Readonly({ value }: { value: unknown }) {
  if (value === undefined || value === null) return <span className="muted">—</span>;
  if (typeof value === "object") return <pre>{JSON.stringify(value, null, 2)}</pre>;
  return <>{String(value)}</>;
}

interface FieldProps {
  pointer: string;
  widget: string;
  doc: Doc;
  edits: Record<string, unknown>;
  texts: Record<string, string>;
  models: Model[] | undefined;
  onEdit: (pointer: string, value: unknown, text?: string) => void;
  onPick: (model: string) => void;
}

function FieldEditor({ pointer, widget, doc, edits, texts, models, onEdit, onPick }: FieldProps) {
  const id = `f${pointer.replaceAll("/", "-")}`;
  const original = valueAt(doc, pointer);
  const value = pointer in edits ? edits[pointer] : original;
  const choices = PLAN_ENUMS[pointer];
  if (widget === "model-picker" && models) {
    const provider = String(edits["/review/reviewer/provider"] ?? valueAt(doc, "/review/reviewer/provider") ?? "");
    const current = typeof value === "string" && value ? `${provider}/${value}` : "";
    const known = models.some((model) => model.id === current);
    return (
      <>
        <select id={id} value={current} onChange={(event) => onPick(event.target.value)}>
          {current === "" && <option value="">—</option>}
          {!known && current !== "" && <option value={current}>{current}</option>}
          {models.map((model) => (
            <option key={model.id} value={model.id}>
              {model.id}
            </option>
          ))}
        </select>
        {!known && current !== "" && <span className="drift"> drift: not in the model catalog (kept as it is)</span>}
      </>
    );
  }
  if (widget === "select" || (widget === "model-picker" && !models)) {
    const providers = pointer === "/review/reviewer/provider" && models ? [...new Set(models.map((model) => model.provider))] : undefined;
    const options = choices ?? providers;
    if (options) {
      const text = typeof value === "string" ? value : "";
      return (
        <select id={id} value={text} onChange={(event) => onEdit(pointer, event.target.value)}>
          {text === "" && <option value="">—</option>}
          {text !== "" && !options.includes(text) && <option value={text}>{text}</option>}
          {options.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      );
    }
    return <input id={id} type="text" value={typeof value === "string" ? value : ""} onChange={(event) => onEdit(pointer, event.target.value)} />;
  }
  if (widget === "textarea") {
    return <textarea id={id} rows={4} value={typeof value === "string" ? value : ""} onChange={(event) => onEdit(pointer, event.target.value)} />;
  }
  if (widget === "number") {
    return (
      <input id={id} type="number" value={typeof value === "number" ? value : ""}
             onChange={(event) => event.target.value !== "" && onEdit(pointer, Number(event.target.value))} />
    );
  }
  if (widget === "toggle") {
    return <input id={id} type="checkbox" checked={value === true} onChange={(event) => onEdit(pointer, event.target.checked)} />;
  }
  const listOfText = widget === "list" && (original === undefined || (Array.isArray(original) && original.every((entry) => typeof entry === "string")));
  if (listOfText) {
    const lines = Array.isArray(value) ? (value as string[]).join("\n") : "";
    return (
      <textarea id={id} rows={4} aria-description="one entry per line" value={pointer in texts ? texts[pointer] : lines}
                onChange={(event) => onEdit(pointer, event.target.value.split("\n").map((line) => line.trim()).filter(Boolean), event.target.value)} />
    );
  }
  if (widget === "json" || widget === "list" || widget === "map") {
    const shown = pointer in texts ? texts[pointer] : value === undefined ? "" : JSON.stringify(value, null, 2);
    return (
      <textarea id={id} rows={6} className="json" value={shown}
                onChange={(event) => {
                  const text = event.target.value;
                  try {
                    onEdit(pointer, text.trim() === "" ? undefined : JSON.parse(text), text);
                  } catch {
                    onEdit(pointer, INVALID, text);
                  }
                }} />
    );
  }
  return <input id={id} type="text" value={typeof value === "string" ? value : ""} onChange={(event) => onEdit(pointer, event.target.value)} />;
}

const INVALID = Symbol("invalid json");

interface Pending {
  confirm: string;
  risk: string;
  summary: string;
  patch: Doc;
  revision: string;
}

/** The edit form of a document: fields from the `forms[]` annotation in the catalog, a draft per changed field, and a
 * save that is a compare-and-swap write on the revision the form was built on. */
export function SchemaFormView({ data, projectId, context = {} }: { data: SchemaForm; projectId?: string; context?: Record<string, string> }) {
  // "Saved." outlives the form: a save changes the revision, which remounts the form with the current document
  const [saved, setSaved] = useState(false);
  return <Form key={data.revision} data={data} projectId={projectId} context={context} saved={saved} setSaved={setSaved} />;
}

function Form({ data, projectId, context, saved, setSaved }: {
  data: SchemaForm;
  projectId?: string;
  context: Record<string, string>;
  saved: boolean;
  setSaved: (saved: boolean) => void;
}) {
  const transport = useTransport();
  const queryClient = useQueryClient();
  const catalog = useCatalog();
  const editor = EDITORS[data.form];
  const doc = data.document as Doc;
  const [edits, setEdits] = useState<Record<string, unknown>>({});
  const [texts, setTexts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [conflict, setConflict] = useState<Doc | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const form = catalog.data?.contributions.flatMap((entry) => entry.document.forms ?? []).find((candidate) => candidate.id === data.form);
  const needsModels = Boolean(form?.fields.some((field) => field.widget === "model-picker"));
  const models = useModels(projectId, needsModels);

  if (catalog.isPending) return <div className="muted">Loading the form…</div>;
  if (catalog.isError) return <ErrorPanel error={catalog.error} />;
  if (!form) return <div className="muted">The form {data.form} is not in the catalog.</div>;
  const annotated = form;

  const invalid = Object.values(edits).some((value) => value === INVALID);
  const patch = buildPatch(doc, edits);
  const changed = Object.keys(patch).length > 0;

  function edit(pointer: string, value: unknown, text?: string) {
    setSaved(false);
    setEdits((current) => ({ ...current, [pointer]: value }));
    if (text !== undefined) setTexts((current) => ({ ...current, [pointer]: text }));
    setNotice(null);
  }

  function pick(id: string) {
    const [provider, ...rest] = id.split("/");
    setSaved(false);
    setEdits((current) => ({ ...current, "/review/reviewer/provider": provider, "/review/reviewer/model": rest.join("/") }));
    setNotice(null);
  }

  function reset() {
    setEdits({});
    setTexts({});
    setConflict(null);
    setFailure(null);
    setNotice(null);
    void queryClient.invalidateQueries({ queryKey: ["query"] });
  }

  async function waitFor(runId: string): Promise<Run> {
    for (let attempt = 0; attempt < 200; attempt += 1) {
      const run = await transport.request<Run>("GET", `/v1/runs/${encodeURIComponent(runId)}`);
      if (ENDED.has(run.state)) return run;
      await new Promise((done) => setTimeout(done, 300));
    }
    throw new Error("The save did not finish in time.");
  }

  async function write(next: Doc, revision: string, confirm?: string) {
    if (!editor) return;
    const body: RunRequest = {
      $schema: RUN_API,
      kind: "run_request",
      context: { ...context, ...(projectId ? { project_id: projectId } : {}) },
      input: { patch: JSON.stringify(next), expected_revision: revision },
      dry_run: false,
      ...(confirm ? { confirm } : {}),
    };
    setBusy(true);
    setFailure(null);
    setNotice(null);
    try {
      const started = await transport.request<Run>("POST", `/v1/commands/${encodeURIComponent(editor.command)}/runs`, body);
      setPending(null);
      const run = await waitFor(started.run_id);
      if (run.state === "succeeded") {
        reset();
        setSaved(true);
        return;
      }
      const code = String(run.error?.details?.plugin_code ?? run.error?.code ?? run.state);
      if (code === "PLAN_REVISION_CONFLICT") setConflict(next);
      else setNotice(MESSAGES[code] ?? `The save failed (${code}).`);
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "CONFIRMATION_REQUIRED" && typeof caught.details.confirm === "string") {
        setPending({ confirm: caught.details.confirm, risk: String(caught.details.risk ?? "medium"),
                     summary: String(caught.details.summary ?? "Save the item"), patch: next, revision });
      } else {
        setFailure(caught);
      }
    } finally {
      setBusy(false);
    }
  }

  async function reapply(kept: Doc) {
    // The same patch on the revision the document has now; only an explicit click gets here.
    if (!editor) return;
    setConflict(null);
    try {
      const fresh = await transport.request<SchemaForm>("POST", `/v1/queries/${encodeURIComponent(editor.query)}`, {
        context: { ...context, ...(projectId ? { project_id: projectId } : {}) },
        params: Object.fromEntries(["plan_id", "item_id"].filter((key) => key in context).map((key) => [key, context[key]])),
      });
      await write(kept, fresh.revision);
    } catch (caught) {
      setFailure(caught);
    }
  }

  const groups = [...(annotated.groups ?? [])].sort((a, b) => (a.order ?? 500) - (b.order ?? 500));
  const known = new Set(groups.map((group) => group.id));
  const sections = [...groups, ...(annotated.fields.some((field) => !field.group || !known.has(field.group)) ? [{ id: "", title: "Other" }] : [])];

  return (
    <form className="schema-form" onSubmit={(event) => { event.preventDefault(); void write(patch, data.revision); }}>
      {!editor && <div className="muted">There is no editor for this form; it is shown read-only.</div>}
      {sections.map((group) => {
        const fields = annotated.fields
          .filter((field) => !field.hidden && (group.id === "" ? !field.group || !known.has(field.group) : field.group === group.id))
          .sort((a, b) => (a.order ?? 500) - (b.order ?? 500));
        if (fields.length === 0) return null;
        return (
          <fieldset key={group.id || "other"}>
            <legend>{group.title}</legend>
            {fields.map((field) => {
              const readonly = !editor || field.readonly || LOCKED_ROOTS.has(parts(field.pointer)[0] ?? "");
              const label = field.pointer.slice(1);
              return (
                <div className="field" key={field.pointer}>
                  <label htmlFor={`f${field.pointer.replaceAll("/", "-")}`}>{label}</label>
                  {readonly ? (
                    <span data-testid={`ro${field.pointer.replaceAll("/", "-")}`} className="readonly">
                      <Readonly value={valueAt(doc, field.pointer)} />
                    </span>
                  ) : (
                    <FieldEditor pointer={field.pointer} widget={field.widget ?? "text"} doc={doc} edits={edits} texts={texts}
                                 models={needsModels ? models.data : undefined} onEdit={edit} onPick={pick} />
                  )}
                  {invalid && edits[field.pointer] === INVALID && <span className="cfg-notice" role="alert"> not valid JSON</span>}
                </div>
              );
            })}
          </fieldset>
        );
      })}
      {editor && (
        <div className="buttons">
          <button type="submit" disabled={busy || !changed || invalid}>
            Save
          </button>
          <button type="button" disabled={busy} onClick={reset}>
            Discard
          </button>
          {!changed && !invalid && <span className="muted"> no changes</span>}
        </div>
      )}
      {saved && <div className="cfg-notice" role="status">Saved.</div>}
      {notice && <div className="cfg-notice" role="status">{notice}</div>}
      {failure ? <ErrorPanel error={failure} /> : null}
      {pending && (
        <div className="dialog" role="dialog" aria-label="Confirm the save">
          <p>
            <strong>Confirm</strong> ({pending.risk} risk): {pending.summary}
          </p>
          <button type="button" disabled={busy} onClick={() => void write(pending.patch, pending.revision, pending.confirm)}>
            Confirm and save
          </button>
          <button type="button" onClick={() => setPending(null)}>
            Cancel
          </button>
        </div>
      )}
      {conflict && (
        <div className="dialog conflict-view" role="dialog" aria-label="The plan changed">
          <h3>The plan changed since you opened the form</h3>
          <p>
            Reload drops your changes and shows the current item. Reapply saves your changes ({Object.keys(conflict).join(", ")}) on top of
            the current item.
          </p>
          <div className="buttons">
            <button type="button" onClick={reset}>
              Reload
            </button>
            <button type="button" onClick={() => void reapply(conflict)}>
              Reapply
            </button>
          </div>
        </div>
      )}
    </form>
  );
}
