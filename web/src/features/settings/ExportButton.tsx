import { useState } from "react";
import { exportSettings, type SettingsScope } from "../../api/hooks/settings";
import { useAuth } from "../../app/providers/AuthProvider";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";

export function ExportButton({ scope }: { scope: SettingsScope }) {
  const { transport } = useAuth();
  const [format, setFormat] = useState<"toml" | "json">("toml");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();

  async function download() {
    setError(undefined);
    setBusy(true);
    try {
      const { document } = await exportSettings(transport, scope, format);
      const text = typeof document === "string" ? document : JSON.stringify(document, null, 2);
      const blob = new Blob([text], { type: format === "json" ? "application/json" : "application/toml" });
      const url = URL.createObjectURL(blob);
      const link = documentAnchor(url, format);
      try {
        link.click();
      } finally {
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 0);
      }
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <label>Формат экспорта <select value={format} disabled={busy}
        onChange={(event) => setFormat(event.currentTarget.value === "json" ? "json" : "toml")}>
        <option value="toml">TOML</option>
        <option value="json">JSON</option>
      </select></label>{" "}
      <Button disabled={busy} onClick={() => void download()}>Экспорт</Button>
      {error != null && <ErrorPanel error={error} onRetry={() => void download()} />}
    </div>
  );
}

function documentAnchor(url: string, format: "toml" | "json") {
  const link = document.createElement("a");
  link.href = url;
  link.download = `settings.${format}`;
  document.body.append(link);
  return link;
}
