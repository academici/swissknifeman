import { useState } from "react";
import { copyText } from "../../lib/clipboard";
import { escapeText } from "../../lib/safeText";

export function CopyId({ id }: { id: string }) {
  const [notice, setNotice] = useState("");
  const visibleId = escapeText(id);
  async function copy() {
    try {
      await copyText(visibleId);
      setNotice("Идентификатор скопирован");
    } catch {
      setNotice("Не удалось скопировать");
    }
  }
  return (
    <span className="copy-id">
      <code>{visibleId}</code>{" "}
      <button type="button" aria-label="Копировать идентификатор" onClick={() => { void copy(); }}>Копировать</button>
      <span className="visually-hidden" role="status">{notice}</span>
    </span>
  );
}
