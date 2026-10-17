import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import type { Command, CommandList, Field, Run, RunRequest } from "../contracts";
import { ErrorPanel } from "../app/ErrorView";
import { ApiError } from "../transport/ApiError";
import { useTransport } from "../transport/context";

type Value = string | number | boolean;
const RUN_API = "urn:swissknifeman:gui:run-api:v1";

export function useCommands() {
  const transport = useTransport();
  return useQuery({
    queryKey: ["commands"],
    queryFn: () => transport.request<CommandList>("GET", "/v1/commands"),
    staleTime: 60_000,
  });
}

function initial(fields: Field[], defaults: Record<string, unknown>): Record<string, Value | ""> {
  const values: Record<string, Value | ""> = {};
  for (const field of fields) {
    const given = defaults[field.name] ?? field.default;
    values[field.name] = typeof given === "string" || typeof given === "number" || typeof given === "boolean" ? given : field.type === "boolean" ? false : "";
  }
  return values;
}

/** Typed values for the request: numbers parsed, empty optional fields left out. The UI never builds argv (I2). */
export function inputOf(fields: Field[], values: Record<string, Value | "">): Record<string, Value> {
  const input: Record<string, Value> = {};
  for (const field of fields) {
    const value = values[field.name];
    if (value === "" || value === undefined) continue;
    if ((field.type === "integer" || field.type === "number") && typeof value === "string") input[field.name] = Number(value);
    else input[field.name] = value;
  }
  return input;
}

function FieldInput({ field, value, onChange }: { field: Field; value: Value | ""; onChange: (value: Value | "") => void }) {
  const id = `field-${field.name}`;
  const label = (
    <label htmlFor={id}>
      {field.title}
      {field.required ? " *" : ""}
    </label>
  );
  if (field.type === "boolean") {
    return (
      <div className="field field-boolean">
        <input id={id} type="checkbox" checked={value === true} onChange={(event) => onChange(event.target.checked)} />
        {label}
      </div>
    );
  }
  if (field.type === "enum") {
    return (
      <div className="field">
        {label}
        <select id={id} value={String(value)} required={field.required} onChange={(event) => onChange(event.target.value)}>
          <option value="">—</option>
          {(field.enum ?? []).map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </div>
    );
  }
  const numeric = field.type === "integer" || field.type === "number";
  return (
    <div className="field">
      {label}
      <input
        id={id}
        type={numeric ? "number" : "text"}
        step={field.type === "integer" ? 1 : undefined}
        min={field.minimum}
        max={field.maximum}
        pattern={field.pattern}
        required={field.required}
        value={String(value)}
        onChange={(event) => onChange(event.target.value)}
      />
      {field.description ? <div className="muted">{field.description}</div> : null}
    </div>
  );
}

interface Pending {
  dryRun: boolean;
  confirm: string;
  risk: string;
  summary: string;
}

/** The input form of a command: typed fields, Run and Dry run, a confirmation dialog on 428, then the run page. */
export function CommandRunner({
  commandId,
  projectId,
  context,
  defaults = {},
}: {
  commandId: string;
  projectId?: string;
  context?: Record<string, string>;
  defaults?: Record<string, unknown>;
}) {
  const commands = useCommands();
  const command = commands.data?.commands.find((entry) => entry.id === commandId);
  if (commands.isPending) return <div className="muted">Loading the command…</div>;
  if (commands.isError) return <ErrorPanel error={commands.error} />;
  if (!command) return <div className="muted">The command {commandId} is not in the catalog.</div>;
  return <CommandForm key={command.id} command={command} projectId={projectId} context={context} defaults={defaults} />;
}

export function CommandForm({
  command,
  projectId,
  context,
  defaults = {},
}: {
  command: Command;
  projectId?: string;
  context?: Record<string, string>;
  defaults?: Record<string, unknown>;
}) {
  const transport = useTransport();
  const navigate = useNavigate();
  const fields = command.input ?? [];
  const [values, setValues] = useState(() => initial(fields, defaults));
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const needsProject = command.scope !== "fleet";

  async function send(dryRun: boolean, confirm?: string) {
    const body: RunRequest = {
      $schema: RUN_API,
      kind: "run_request",
      context: needsProject && projectId ? { ...context, project_id: projectId } : {},
      input: inputOf(fields, values),
      dry_run: dryRun,
      ...(confirm ? { confirm } : {}),
    };
    setBusy(true);
    setError(null);
    try {
      const run = await transport.request<Run>("POST", `/v1/commands/${encodeURIComponent(command.id)}/runs`, body);
      setPending(null);
      void navigate(`/runs/${run.run_id}`);
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "CONFIRMATION_REQUIRED" && typeof caught.details.confirm === "string") {
        setPending({ dryRun, confirm: caught.details.confirm, risk: String(caught.details.risk ?? command.risk),
                     summary: String(caught.details.summary ?? command.title) });
      } else {
        setError(caught);
      }
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent, dryRun: boolean) {
    event.preventDefault();
    void send(dryRun);
  }

  return (
    <form className="command-form" onSubmit={(event) => submit(event, false)}>
      <h3>{command.title}</h3>
      {command.description ? <p className="muted">{command.description}</p> : null}
      {needsProject && !projectId ? <div className="muted">Choose a project to run this command.</div> : null}
      {fields.map((field) => (
        <FieldInput key={field.name} field={field} value={values[field.name] ?? ""}
                    onChange={(value) => setValues((current) => ({ ...current, [field.name]: value }))} />
      ))}
      <div className="buttons">
        <button type="submit" disabled={busy || (needsProject && !projectId)}>
          Run
        </button>
        {command.supports?.includes("dry-run") && (
          <button type="button" disabled={busy || (needsProject && !projectId)} onClick={(event) => submit(event, true)}>
            Dry run
          </button>
        )}
        <span className={`risk risk-${command.risk}`}>risk {command.risk}</span>
      </div>
      {error ? <ErrorPanel error={error} /> : null}
      {pending && (
        <div className="dialog" role="dialog" aria-label="Confirm the run">
          <p>
            <strong>Confirm</strong> ({pending.risk} risk): {pending.summary}
          </p>
          <button type="button" disabled={busy} onClick={() => void send(pending.dryRun, pending.confirm)}>
            Confirm and run
          </button>
          <button type="button" onClick={() => setPending(null)}>
            Cancel
          </button>
        </div>
      )}
    </form>
  );
}
