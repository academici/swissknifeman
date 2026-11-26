import type { ApiErrorBody, Issue } from "../contracts";

/** A failed API request: the `api-error/v1` envelope as an exception. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly retryable: boolean;
  readonly correlationId: string | null;
  readonly details: Record<string, string | number | boolean | null>;
  readonly issues: Issue[];

  constructor(status: number, body: Partial<ApiErrorBody> & { code: string; message: string }) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.retryable = Boolean(body.retryable);
    this.correlationId = body.correlation_id ?? null;
    this.details = Object.fromEntries(
      Object.entries(body.details ?? {}).filter((entry): entry is [string, string | number | boolean | null] => entry[1] !== undefined),
    );
    this.issues = [...(body.issues ?? [])];
  }

  static from(status: number, document: unknown): ApiError {
    const error = (document as { error?: Partial<ApiErrorBody> } | null)?.error;
    if (error && typeof error.code === "string" && typeof error.message === "string") {
      return new ApiError(status, error as ApiErrorBody);
    }
    return new ApiError(status, { code: status === 401 ? "AUTH_REQUIRED" : "INTERNAL", message: `HTTP ${status}` });
  }
}
