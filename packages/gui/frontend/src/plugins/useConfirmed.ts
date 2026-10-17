import { useState } from "react";
import { ApiError } from "../transport/ApiError";

export interface Pending {
  title: string;
  risk: string;
  summary: string;
  confirm: string;
  /** Repeats the very same request with the token. */
  resend: (confirm: string) => Promise<void>;
}

/**
 * A request that may answer 428 `CONFIRMATION_REQUIRED`: the summary and risk of the answer go into `pending` (shown
 * by a dialog) and the same request is repeated with `details.confirm` only when the operator confirms. A new 428
 * for the repeat (the request changed meanwhile) replaces `pending` and shows its summary again.
 */
export function useConfirmed() {
  const [pending, setPending] = useState<Pending | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function attempt(title: string, send: (confirm?: string) => Promise<void>, confirm?: string): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await send(confirm);
      setPending(null);
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "CONFIRMATION_REQUIRED" && typeof caught.details.confirm === "string") {
        setPending({
          title,
          risk: String(caught.details.risk ?? "medium"),
          summary: String(caught.details.summary ?? ""),
          confirm: caught.details.confirm,
          resend: (token) => attempt(title, send, token),
        });
      } else {
        setPending(null);
        setError(caught);
      }
    } finally {
      setBusy(false);
    }
  }

  return {
    pending,
    error,
    busy,
    /** Sends the request; `send(confirm?)` must throw the ApiError of a failed answer. */
    run: (title: string, send: (confirm?: string) => Promise<void>) => attempt(title, send),
    cancel: () => setPending(null),
    clearError: () => setError(null),
  };
}
