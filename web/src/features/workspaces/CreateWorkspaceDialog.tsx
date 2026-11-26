import { useState } from "react";
import type { CreateWorkspace } from "../../api/generated/workspace";
import { useCommand } from "../../api/hooks/workspace";
import { useAuth } from "../../app/providers/AuthProvider";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Dialog } from "../../components/primitives/Dialog";

export function CreateScopeDialog({ workspaceId }: { workspaceId: string | null }) {
  const [open, setOpen] = useState(false);
  const { refreshIdentity } = useAuth();
  const mutation = useCommand(workspaceId, () => { setOpen(false); refreshIdentity(); });
  const label = workspaceId ? "Создать проект" : "Создать пространство";
  return <>
    <Button onClick={() => { mutation.reset(); setOpen(true); }}>{label}</Button>
    <Dialog open={open} title={label} onClose={() => { if (!mutation.isPending) setOpen(false); }}>
      <form onSubmit={event => {
        event.preventDefault();
        const fields = new FormData(event.currentTarget);
        const body: CreateWorkspace = { slug: String(fields.get("slug")), title: String(fields.get("title")) };
        mutation.mutate(workspaceId
          ? { path: `/workspaces/${encodeURIComponent(workspaceId)}/projects`, body: { ...body, description: fields.get("description") } }
          : { path: "/workspaces", body });
      }}>
        <label>Slug<input required name="slug" /></label>
        <label>Название<input required maxLength={200} name="title" /></label>
        {workspaceId && <label>Описание<textarea name="description" maxLength={4000} /></label>}
        {mutation.error && <ErrorPanel error={mutation.error} />}
        <Button type="submit" disabled={mutation.isPending}>Создать</Button>
      </form>
    </Dialog>
  </>;
}

export default function CreateWorkspaceDialog() {
  return <CreateScopeDialog workspaceId={null} />;
}
