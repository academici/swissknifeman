import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import type { GrantRequest, GrantResult } from "../contracts/generated/plugin-api";
import { ErrorPanel } from "../app/ErrorView";
import { useProjects } from "../pages/Projects";
import { useTransport } from "../transport/context";
import { invalidatePlugins, paths, PLUGIN_API, type PluginDoc } from "./api";
import { useConfirmed, type Pending } from "./useConfirmed";

/** Effects a grant can cover: the declared ones except `read` (free) and `terminal` (reserved). */
export function grantableEffects(plugin: PluginDoc): GrantRequest["capability"][] {
  return plugin.permissions.filter((entry) => entry.declared && entry.effect !== "read" && entry.effect !== "terminal").map((entry) => entry.effect);
}

export const EXPIRIES = [
  { id: "none", label: "no expiry", days: 0 },
  { id: "1d", label: "1 day", days: 1 },
  { id: "7d", label: "7 days", days: 7 },
  { id: "30d", label: "30 days", days: 30 },
] as const;

/** RFC 3339 UTC without fractions: `2026-10-16T12:00:00Z`. */
export function expiryAt(days: number, now: Date = new Date()): string | null {
  if (days === 0) return null;
  return new Date(now.getTime() + days * 86_400_000).toISOString().replace(/\.\d{3}Z$/, "Z");
}

/** The confirmation of a 428: the summary of the backend is shown and only the button repeats the request. */
export function ConfirmDialog({ pending, busy, action, onCancel }: { pending: Pending; busy: boolean; action: string; onCancel: () => void }) {
  return (
    <div className="dialog confirm-dialog" role="dialog" aria-label={pending.title}>
      <p>
        <strong>{pending.title}</strong> ({pending.risk} risk): {pending.summary}
      </p>
      <button type="button" disabled={busy} onClick={() => void pending.resend(pending.confirm)}>
        {action}
      </button>
      <button type="button" onClick={onCancel}>
        Cancel
      </button>
    </div>
  );
}

export function GrantDialog({ plugin, projectId, onClose }: { plugin: PluginDoc; projectId?: string | null; onClose: () => void }) {
  const transport = useTransport();
  const queryClient = useQueryClient();
  const projects = useProjects();
  const effects = grantableEffects(plugin);
  const [capability, setCapability] = useState<GrantRequest["capability"] | "">(effects[0] ?? "");
  const [project, setProject] = useState(projectId ?? "");
  const [expiry, setExpiry] = useState<(typeof EXPIRIES)[number]["id"]>("none");
  const confirmed = useConfirmed();

  function submit(event: FormEvent) {
    event.preventDefault();
    if (capability === "") return;
    // the body is made once: the confirmation is bound to it, a later retry must not move the expiry
    const body: GrantRequest = {
      $schema: PLUGIN_API,
      kind: "grant_request",
      capability,
      project_id: project === "" ? null : project,
      expires_at: expiryAt(EXPIRIES.find((entry) => entry.id === expiry)?.days ?? 0),
    };
    void confirmed.run(`Grant ${capability} to ${plugin.id}`, async (confirm) => {
      await transport.request<GrantResult>("POST", paths.grants(plugin.id), confirm ? { ...body, confirm } : body);
      invalidatePlugins(queryClient);
      onClose();
    });
  }

  return (
    <form className="dialog grant-dialog" role="dialog" aria-label={`Grant for ${plugin.id}`} onSubmit={submit}>
      <h3>Grant for {plugin.id}</h3>
      {effects.length === 0 ? (
        <div className="muted">This plugin declares no effect that needs a grant.</div>
      ) : (
        <>
          <label>
            Effect
            <select value={capability} onChange={(event) => setCapability(event.target.value as GrantRequest["capability"])}>
              {effects.map((effect) => (
                <option key={effect} value={effect}>
                  {effect}
                </option>
              ))}
            </select>
          </label>
          <label>
            Project
            <select value={project} onChange={(event) => setProject(event.target.value)}>
              <option value="">all projects</option>
              {projects.data?.projects.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Expires
            <select value={expiry} onChange={(event) => setExpiry(event.target.value as typeof expiry)}>
              {EXPIRIES.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.label}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={confirmed.busy || capability === ""}>
            Grant
          </button>
        </>
      )}
      <button type="button" onClick={onClose}>
        Close
      </button>
      {confirmed.error ? <ErrorPanel error={confirmed.error} /> : null}
      {confirmed.pending && <ConfirmDialog pending={confirmed.pending} busy={confirmed.busy} action="Confirm and grant" onCancel={confirmed.cancel} />}
    </form>
  );
}
