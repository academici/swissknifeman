import type { Problem } from "./generated/api";

const waitingCodes: ReadonlySet<string> = new Set([
  "NOTHING_TO_CLAIM",
  "MANUAL_PENDING",
  "APPROVAL_REQUIRED",
  "WAITING_FOR_ANSWER",
  "SLOT_BUSY",
]);

type ErrorFields = Pick<Problem, "status" | "detail" | "details" | "retryable" | "instance"> & {
  code: string;
  category: string;
  requestId: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly category: string;
  readonly detail: string;
  readonly details: Problem["details"];
  readonly retryable: boolean;
  readonly requestId: string;
  readonly instance: string;

  constructor(fields: ErrorFields) {
    super(fields.detail);
    this.name = "ApiError";
    this.status = fields.status;
    this.code = fields.code;
    this.category = fields.category;
    this.detail = fields.detail;
    this.details = fields.details;
    this.retryable = fields.retryable;
    this.requestId = fields.requestId;
    this.instance = fields.instance;
  }

  static fromResponse(status: number, document: unknown, requestId: string, instance: string): ApiError {
    if (isRecord(document) && typeof document.code === "string" && typeof document.category === "string") {
      return new ApiError({
        status,
        code: document.code,
        category: document.category,
        detail: typeof document.detail === "string" ? document.detail : document.code,
        details: isRecord(document.details) ? document.details : {},
        retryable: document.retryable === true,
        requestId: typeof document.request_id === "string" ? document.request_id : requestId,
        instance: typeof document.instance === "string" ? document.instance : instance,
      });
    }
    return new ApiError({
      status, code: "INTERNAL_ERROR", category: "internal", detail: `HTTP ${status}`,
      details: {}, retryable: false, requestId, instance,
    });
  }

  static unavailable(requestId: string, instance: string): ApiError {
    return new ApiError({
      status: 0, code: "BACKEND_UNAVAILABLE", category: "backend", detail: "Сервер недоступен",
      details: {}, retryable: true, requestId, instance,
    });
  }

  isConflict(): boolean {
    return this.status === 409 || this.category === "conflict";
  }

  isWaiting(): boolean {
    return this.category === "waiting" || waitingCodes.has(this.code);
  }
}
