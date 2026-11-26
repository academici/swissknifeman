import { useState } from "react";
import { copyText } from "../../lib/clipboard";
import { escapeText } from "../../lib/safeText";

export function CodeBlock({ text }: { text: string }) {
  const visibleText = escapeText(text);
  const [notice, setNotice] = useState("");

  async function copy() {
    try {
      await copyText(visibleText);
      setNotice("Скопировано");
    } catch {
      setNotice("Не удалось скопировать");
    }
  }

  return (
    <div className="code-block">
      <pre tabIndex={0}><code>{visibleText}</code></pre>
      <div className="code-actions">
        <button type="button" onClick={() => { void copy(); }}>Копировать код</button>
        <span role="status">{notice}</span>
      </div>
    </div>
  );
}
