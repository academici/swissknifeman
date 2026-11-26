import { escapeText } from "../../lib/safeText";

export function Toast({ message, requestId, onDismiss }: {
  message: string;
  requestId?: string | undefined;
  onDismiss(): void;
}) {
  return (
    <div className="toast">
      <span role="status">
        {escapeText(message)}{requestId && <> · <code>{escapeText(requestId)}</code></>}
      </span>
      <button type="button" onClick={onDismiss}>Закрыть</button>
    </div>
  );
}
