import { useEffect, useRef, useState } from "react";
import { downloadBlob } from "../../api/hooks/artifacts";
import { useRunReport } from "../../api/hooks/exports";
import { useScope } from "../../app/providers/ScopeProvider";
import { Button } from "../../components/primitives/Button";
import { escapeText } from "../../lib/safeText";

export function ExportAction({ runId }: { runId: string }) {
  const report = useRunReport();
  const { scope } = useScope();
  const active = useRef<AbortController | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setBusy(false);
    setFailed(false);
    return () => {
      active.current?.abort();
      active.current = null;
    };
  }, [runId, report, scope.projectId, scope.workspaceId]);

  async function download() {
    if (active.current) return;
    const controller = new AbortController();
    active.current = controller;
    setBusy(true);
    setFailed(false);
    try {
      const blob = await report(runId, controller.signal);
      controller.signal.throwIfAborted();
      downloadBlob(blob, `run-${escapeText(runId)}.md`);
    } catch {
      if (!controller.signal.aborted) setFailed(true);
    } finally {
      if (active.current === controller) {
        active.current = null;
        setBusy(false);
      }
    }
  }

  return <>
    <Button disabled={busy} onClick={() => void download()}>Export Markdown</Button>
    {failed && <p role="alert">Не удалось скачать отчёт.</p>}
  </>;
}
