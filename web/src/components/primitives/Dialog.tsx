import { Dialog as BaseDialog } from "@base-ui/react/dialog";
import type { PropsWithChildren } from "react";
import { escapeText } from "../../lib/safeText";

export function Dialog({ open, title, onClose, children }: PropsWithChildren<{
  open: boolean;
  title: string;
  onClose(): void;
}>) {
  return (
    <BaseDialog.Root open={open} disablePointerDismissal onOpenChange={(nextOpen) => {
      if (!nextOpen) onClose();
    }}>
      <BaseDialog.Portal>
        <BaseDialog.Backdrop className="dialog-backdrop" />
        <BaseDialog.Popup className="dialog-popup">
          <BaseDialog.Title>{escapeText(title)}</BaseDialog.Title>
          {children}
          <BaseDialog.Close>Закрыть</BaseDialog.Close>
        </BaseDialog.Popup>
      </BaseDialog.Portal>
    </BaseDialog.Root>
  );
}
