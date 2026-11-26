import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";

/**
 * Focus handling of an inline dialog: when it appears the dialog takes the focus, when it goes away the focus returns to
 * the element that had it before (the button that opened the dialog), if that element is still in the page. Escape calls
 * `onEscape` and does not reach an outer dialog.
 */
export function useDialog<T extends HTMLElement>(onEscape?: () => void) {
  const ref = useRef<T>(null);
  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    ref.current?.focus();
    return () => {
      if (opener?.isConnected) opener.focus();
    };
  }, []);
  const onKeyDown = (event: KeyboardEvent<T>) => {
    if (event.key === "Escape" && onEscape) {
      event.stopPropagation();
      onEscape();
    }
  };
  return { ref, tabIndex: -1, onKeyDown };
}

/** A `div` with `role="dialog"`, an accessible name and the focus handling of {@link useDialog}. */
export function Dialog({ className, label, onEscape, children }: { className?: string; label: string; onEscape?: () => void; children: ReactNode }) {
  const dialog = useDialog<HTMLDivElement>(onEscape);
  return (
    <div className={className ? `dialog ${className}` : "dialog"} role="dialog" aria-label={label} {...dialog}>
      {children}
    </div>
  );
}
