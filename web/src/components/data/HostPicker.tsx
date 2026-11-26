import { operatorError, useHosts } from "../../api/hooks/workspace";
import { useScope } from "../../app/providers/ScopeProvider";
import { ErrorPanel } from "../feedback/ErrorPanel";
import { escapeText } from "../../lib/safeText";
import { Pagination } from "./Pagination";

export function HostPicker({ value, onChange, disabled, empty = "Выберите хост" }: {
  value: string;
  onChange(hostId: string): void;
  disabled?: boolean;
  empty?: string;
}) {
  const { scope } = useScope();
  const { query, cursor } = useHosts(scope.workspaceId);
  const hosts = query.data?.items ?? [];
  return <>
    <label>Хост
      <select value={value} disabled={disabled || query.isPending} onChange={event => onChange(event.currentTarget.value)}>
        <option value="">{empty}</option>
        {value && !hosts.some(host => host.host_id === value) && <option value={value}>{escapeText(value)}</option>}
        {hosts.map(host => <option key={host.host_id} value={host.host_id}>
          {escapeText(`${host.name} · ${host.platform.os}/${host.platform.arch}`)}
          {host.state === "retired" && " · выведен из эксплуатации"}
        </option>)}
      </select>
    </label>
    {query.isPending && <p role="status">Загрузка хостов…</p>}
    {query.isError && <ErrorPanel error={operatorError(query.error)} onRetry={() => void query.refetch()} />}
    {query.data && <Pagination {...cursor} next={query.data.next} busy={Boolean(disabled)} />}
  </>;
}
