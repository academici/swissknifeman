import { AlertDialog } from "@base-ui/react/alert-dialog";
import { useId, useRef, type FormEvent, type PropsWithChildren } from "react";
import { escapeText } from "../../lib/safeText";

export function ConfirmDialog({
  open, title, description, confirmLabel = "Подтвердить", requireReason = false,
  destructive = false, onClose, onConfirm, children,
}: PropsWithChildren<{
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  requireReason?: boolean;
  destructive?: boolean;
  onClose(): void;
  onConfirm(reason: string): void;
}>) {
  const field = useId();
  const cancel = useRef<HTMLButtonElement>(null);

  function confirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const reason = String(new FormData(event.currentTarget).get("reason") ?? "").trim();
    if (requireReason && !reason) return;
    event.currentTarget.reset();
    onConfirm(reason);
  }

  return (
    <AlertDialog.Root open={open} onOpenChange={(nextOpen) => {
      if (!nextOpen) onClose();
    }}>
      <AlertDialog.Portal>
        <AlertDialog.Backdrop className="dialog-backdrop" />
        <AlertDialog.Popup className="dialog-popup" initialFocus={destructive ? cancel : undefined}>
          <AlertDialog.Title>{escapeText(title)}</AlertDialog.Title>
          {description && <AlertDialog.Description>{escapeText(description)}</AlertDialog.Description>}
          <form onSubmit={confirm}>
            {children}
            {requireReason && (
              <>
                <label htmlFor={field}>Причина</label>
                <textarea id={field} name="reason" required />
              </>
            )}
            <div className="confirm-actions">
              <button type="submit" data-tone={destructive ? "danger" : undefined}>
                {escapeText(confirmLabel)}
              </button>
              <AlertDialog.Close ref={cancel}>Отмена</AlertDialog.Close>
            </div>
          </form>
        </AlertDialog.Popup>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}
