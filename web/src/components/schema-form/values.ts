import type { SchemaNode } from "./profile";

export function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function own(value: unknown, key: string): unknown {
  return isRecord(value) && Object.hasOwn(value, key) ? value[key] : undefined;
}

export function appendPointer(pointer: string, key: string | number): string {
  return `${pointer}/${String(key).replaceAll("~", "~0").replaceAll("/", "~1")}`;
}

export function pointerTokens(pointer: string): string[] | undefined {
  if (pointer === "") return [];
  if (!pointer.startsWith("/")) return undefined;
  const tokens = pointer.slice(1).split("/");
  if (tokens.some((token) => /~(?:[^01]|$)/u.test(token))) return undefined;
  return tokens.map((token) => token.replaceAll("~1", "/").replaceAll("~0", "~"));
}

function arrayIndex(key: string): number {
  return /^(0|[1-9][0-9]*)(?![\s\S])/u.test(key) ? Number(key) : -1;
}

export function getAtPointer(value: unknown, pointer: string): unknown {
  return pointerTokens(pointer)?.reduce<unknown>((current, key) => {
    if (Array.isArray(current)) {
      const index = arrayIndex(key);
      return index >= 0 && index < current.length ? current[index] : undefined;
    }
    return own(current, key);
  }, value);
}

function updateAt(
  current: unknown,
  tokens: readonly string[],
  replace: (value: unknown) => unknown,
  remove: boolean,
  offset = 0,
): unknown {
  const key = tokens[offset];
  if (key === undefined) return replace(current);
  const last = offset === tokens.length - 1;
  if (Array.isArray(current)) {
    const index = arrayIndex(key);
    if (index < 0 || index > current.length || (index === current.length && remove)) return current;
    if (remove && last) return current.filter((_, itemIndex) => itemIndex !== index);
    const next = updateAt(current[index], tokens, replace, remove, offset + 1);
    if (index < current.length && next === current[index]) return current;
    const copy: unknown[] = [...current];
    copy[index] = next;
    return copy;
  }
  if (remove && (!isRecord(current) || !Object.hasOwn(current, key))) return current;
  const record = isRecord(current) ? current : {};
  if (remove && last) {
    const copy = { ...record };
    delete copy[key];
    return copy;
  }
  const previous = own(record, key);
  const next = updateAt(previous, tokens, replace, remove, offset + 1);
  return next === previous && (remove || Object.hasOwn(record, key)) ? current : { ...record, [key]: next };
}

/** Missing containers are objects. Numeric tokens index arrays only when the container is an array. */
export function setAtPointer(value: unknown, pointer: string, next: unknown): unknown {
  const tokens = pointerTokens(pointer);
  return tokens ? updateAt(value, tokens, () => next, false) : value;
}

export function removeAtPointer(value: unknown, pointer: string): unknown {
  const tokens = pointerTokens(pointer);
  return tokens ? updateAt(value, tokens, () => undefined, true) : value;
}

export function jsonEqual(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (Array.isArray(left)) {
    return Array.isArray(right) && left.length === right.length &&
      left.every((value: unknown, index) => jsonEqual(value, right[index]));
  }
  if (!isRecord(left) || !isRecord(right)) return false;
  const keys = Object.keys(left);
  return keys.length === Object.keys(right).length &&
    keys.every((key) => Object.hasOwn(right, key) && jsonEqual(left[key], right[key]));
}

export interface SchemaIssue {
  pointer: string;
  code: string;
  message: string;
}

export function schemaIssues(error: unknown): SchemaIssue[] {
  if (own(error, "status") !== 422 || own(error, "code") !== "SCHEMA_INVALID") return [];
  const issues = own(own(error, "details"), "issues");
  if (!Array.isArray(issues)) return [];
  return issues.filter((issue): issue is SchemaIssue =>
    typeof own(issue, "pointer") === "string" &&
    typeof own(issue, "code") === "string" &&
    typeof own(issue, "message") === "string",
  );
}

const secretReference = /^secret:\/\/(env\/[A-Z_][A-Z0-9_]{0,127}|file\/[^\s]{1,1024}|keyring\/[A-Za-z0-9._-]{1,128}\/[A-Za-z0-9._@-]{1,128})(?![\s\S])/u;

export function isSecretReference(value: unknown): value is string {
  return typeof value === "string" && secretReference.test(value) && !/[\p{Cc}\p{Bidi_Control}]/u.test(value);
}

export function matchesPattern(value: string, pattern: unknown): boolean {
  if (typeof pattern !== "string") return true;
  try {
    return new RegExp(pattern, "u").test(value);
  } catch {
    return true;
  }
}

function matchesFormat(value: string, format: unknown): boolean {
  switch (format) {
    case "uri":
      try {
        return !/\s/u.test(value) && Boolean(new URL(value));
      } catch {
        return false;
      }
    case "date-time": {
      const parts = /^(\d{4})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])T([01]\d|2[0-3]):[0-5]\d:(?:[0-5]\d|60)(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/iu.exec(value);
      if (!parts || parts[0] !== value) return false;
      const calendar = new Date(0);
      calendar.setUTCFullYear(Number(parts[1]), Number(parts[2]), 0);
      return Number(parts[3]) <= calendar.getUTCDate();
    }
    case "uuid":
      return /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/iu.test(value) && value.length === 36;
    default:
      return true;
  }
}

export function advisoryHints(node: SchemaNode, value: unknown, required: boolean): string[] {
  const { schema } = node;
  if (value === undefined) return required ? ["Обязательное поле"] : [];

  switch (node.kind) {
    case "leaf/string": {
      if (typeof value !== "string") return ["Ожидается строка"];
      const hints = [];
      const length = [...value].length;
      if (typeof schema.minLength === "number" && length < schema.minLength) hints.push(`Минимум ${schema.minLength} символов`);
      if (typeof schema.maxLength === "number" && length > schema.maxLength) hints.push(`Максимум ${schema.maxLength} символов`);
      if (!matchesPattern(value, schema.pattern)) hints.push("Строка не соответствует шаблону");
      if (!matchesFormat(value, schema.format)) hints.push(`Ожидается формат ${String(schema.format)}`);
      return hints;
    }
    case "leaf/number": {
      if (typeof value !== "number" || !Number.isFinite(value)) return ["Ожидается число"];
      const hints = [];
      if (schema.type === "integer" && !Number.isInteger(value)) hints.push("Ожидается целое число");
      if (typeof schema.minimum === "number" && value < schema.minimum) hints.push(`Минимум ${schema.minimum}`);
      if (typeof schema.maximum === "number" && value > schema.maximum) hints.push(`Максимум ${schema.maximum}`);
      if (typeof schema.exclusiveMinimum === "number" && value <= schema.exclusiveMinimum) hints.push(`Больше ${schema.exclusiveMinimum}`);
      if (typeof schema.exclusiveMaximum === "number" && value >= schema.exclusiveMaximum) hints.push(`Меньше ${schema.exclusiveMaximum}`);
      if (typeof schema.multipleOf === "number" && schema.multipleOf > 0) {
        const quotient = value / schema.multipleOf;
        if (!Number.isFinite(quotient) || Math.abs(quotient - Math.round(quotient)) > 1e-10) {
          hints.push(`Число должно быть кратно ${schema.multipleOf}`);
        }
      }
      return hints;
    }
    case "leaf/boolean":
      return typeof value === "boolean" ? [] : ["Ожидается логическое значение"];
    case "leaf/enum":
      return node.options.some((option) => jsonEqual(option, value)) ? [] : ["Выберите допустимое значение"];
    case "array/scalar":
    case "array/object": {
      if (!Array.isArray(value)) return ["Ожидается массив"];
      const hints = [];
      if (typeof schema.minItems === "number" && value.length < schema.minItems) hints.push(`Минимум ${schema.minItems} элементов`);
      if (typeof schema.maxItems === "number" && value.length > schema.maxItems) hints.push(`Максимум ${schema.maxItems} элементов`);
      return hints;
    }
    case "object":
    case "map":
    case "oneOf":
      return isRecord(value) ? [] : ["Ожидается объект"];
    case "secretRef":
      return isSecretReference(value) ? [] : [secretFormatHint];
    case "unsupported":
      return [];
  }
}

export const secretFormatHint = "Ожидается ссылка secret://env/…, secret://file/… или secret://keyring/…";

export function selectedVariant(node: Extract<SchemaNode, { kind: "oneOf" }>, value: unknown): number {
  const tag = own(value, node.discriminator);
  return node.variants.findIndex((variant) => variant.tags.some((option) => jsonEqual(option, tag)));
}

export function initialValue(node: SchemaNode): unknown {
  if (node.kind === "secretRef") {
    return isSecretReference(node.schema.default) ? node.schema.default : undefined;
  }
  if (Object.hasOwn(node.schema, "default")) return node.schema.default;
  switch (node.kind) {
    case "leaf/string": return "";
    case "leaf/number": return typeof node.schema.minimum === "number" ? node.schema.minimum : 0;
    case "leaf/boolean": return false;
    case "leaf/enum": return node.options[0];
    case "array/scalar":
    case "array/object": return [];
    case "map": return {};
    case "object":
      return Object.fromEntries(node.properties.filter(({ node: child }) =>
        child.kind === "secretRef" ? isSecretReference(child.schema.default) :
          Object.hasOwn(child.schema, "const") || Object.hasOwn(child.schema, "default"),
      ).map(({ key, node: child }) => [key, initialValue(child)]));
    case "oneOf": return {};
    case "unsupported": return null;
  }
}
