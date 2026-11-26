import {
  appendPointer, getAtPointer, isRecord, isSecretReference, jsonEqual, matchesPattern, own, pointerTokens,
} from "./values";

type Schema = Readonly<Record<string, unknown>>;
export type SchemaRegistry = Readonly<Record<string, unknown>>;

interface Ui {
  group: string | undefined;
  order: number;
  widget: string | undefined;
  advanced: boolean;
  title: string | undefined;
  helpUrl: string | undefined;
}

interface BaseNode {
  pointer: string;
  title: string | undefined;
  description: string | undefined;
  ui: Ui;
  schema: Schema;
}

export interface Property {
  key: string;
  required: boolean;
  node: SchemaNode;
}

interface Variant {
  tags: readonly unknown[];
  node: SchemaNode;
}

export type StringNode = BaseNode & { kind: "leaf/string"; widget: "text" | "path" | "textarea" | "markdown" | "code" };
export type NumberNode = BaseNode & { kind: "leaf/number"; widget: "number" | "slider" };
export type BooleanNode = BaseNode & { kind: "leaf/boolean"; widget: "checkbox" | "switch" | "toggle" };
export type EnumNode = BaseNode & { kind: "leaf/enum"; widget: "radio" | "select"; options: readonly unknown[] };
export type ArrayNode = BaseNode & { kind: "array/scalar" | "array/object"; widget: "list" | "tags" | "table"; item: SchemaNode };
export type ObjectNode = BaseNode & {
  kind: "object";
  widget: "fieldset" | "collapsed";
  properties: readonly Property[];
  entry?: SchemaNode;
};
export type MapNode = BaseNode & { kind: "map"; widget: "map"; entry: SchemaNode };
export type OneOfNode = BaseNode & {
  kind: "oneOf";
  widget: "select";
  discriminator: string;
  variants: readonly Variant[];
  redact: (value: unknown) => unknown;
};
export type SecretNode = BaseNode & { kind: "secretRef"; widget: "secret" };
export type UnsupportedNode = BaseNode & {
  kind: "unsupported";
  widget: "json";
  keywords: readonly string[];
  redact: (value: unknown) => unknown;
};

export type SchemaNode = StringNode | NumberNode | BooleanNode | EnumNode | ArrayNode | ObjectNode | MapNode |
  OneOfNode | SecretNode | UnsupportedNode;

const secretUrn = "urn:skm:config:secret-ref:v1";
const maxSchemaDepth = 64;
const masked = "•••";
const unsupportedKeywords = [
  "if", "then", "else", "allOf", "not", "patternProperties", "anyOf", "dependentSchemas", "prefixItems",
  "dependentRequired", "contains", "unevaluatedItems", "unevaluatedProperties", "$dynamicRef",
] as const;
const supportedTypes = new Set<unknown>(["string", "integer", "number", "boolean", "array", "object"]);

function string(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function isSecret(schema: Schema): boolean {
  return schema.$id === secretUrn || isSecretRef(schema.$ref) || schema["x-skm-secret"] === true ||
    own(schema["x-skm"], "sensitivity") === "secret" || own(own(schema["x-skm"], "ui"), "widget") === "secret";
}

function isSecretRef(ref: unknown): boolean {
  return ref === secretUrn || ref === `${secretUrn}#`;
}

interface Context {
  registry: SchemaRegistry;
  document: Schema;
  active: readonly Schema[];
  depth: number;
}

interface SchemaLocation {
  schema: Schema;
  document: Schema;
}

function resolve(ref: string, context: Pick<Context, "registry" | "document">): SchemaLocation | undefined {
  const hash = ref.indexOf("#");
  const urn = hash === -1 ? ref : ref.slice(0, hash);
  const document = (urn === "" && hash === 0) || urn === context.document.$id
    ? context.document
    : urn.startsWith("urn:") ? own(context.registry, urn) : undefined;
  if (!isRecord(document)) return undefined;
  try {
    const fragment = hash === -1 ? "" : decodeURIComponent(ref.slice(hash + 1));
    const tokens = pointerTokens(fragment);
    if (!tokens) return undefined;
    let schema: unknown = document;
    let resource = document;
    for (const token of tokens) {
      schema = getAtPointer(schema, appendPointer("", token));
      if (isRecord(schema) && typeof schema.$id === "string") resource = schema;
    }
    if (isRecord(schema)) return { schema, document: resource };
  } catch {
    // A malformed URI fragment is an unresolved reference.
  }
}

function uiFor(schema: Schema): Ui {
  const ui = own(schema["x-skm"], "ui");
  const order = own(ui, "order");
  return {
    group: string(own(ui, "group")),
    order: typeof order === "number" && Number.isFinite(order) ? order : Infinity,
    widget: string(own(ui, "widget")),
    advanced: own(ui, "advanced") === true,
    title: string(own(ui, "title")),
    helpUrl: string(own(ui, "help_url")),
  };
}

function baseFor(schema: Schema, pointer: string): BaseNode {
  const ui = uiFor(schema);
  return { pointer, ui, schema, title: ui.title ?? string(schema.title), description: string(schema.description) };
}

function mergeReference(target: Schema, wrapper: Schema): Schema {
  const siblings = { ...wrapper };
  delete siblings.$ref;
  const targetMeta = isRecord(target["x-skm"]) ? target["x-skm"] : {};
  const localMeta = isRecord(siblings["x-skm"]) ? siblings["x-skm"] : {};
  const targetUi = isRecord(targetMeta.ui) ? targetMeta.ui : {};
  const localUi = isRecord(localMeta.ui) ? localMeta.ui : {};
  const merged = { ...target, ...siblings, "x-skm": { ...targetMeta, ...localMeta, ui: { ...targetUi, ...localUi } } };
  // Shape-affecting $ref siblings are an intersection, outside this renderer's profile.
  const annotations = ["$id", "$schema", "$defs", "$comment", "title", "description", "default", "examples",
    "deprecated", "readOnly", "writeOnly"];
  return Object.keys(siblings).some((key) => !key.startsWith("x-") && !annotations.includes(key))
    ? { ...merged, allOf: [target, siblings] }
    : merged;
}

function redactionSchemas(sources: readonly SchemaLocation[], registry: SchemaRegistry): SchemaLocation[] | undefined {
  const schemas: SchemaLocation[] = [];
  const seen = new Map<Schema, Set<Schema>>();

  function visit(raw: unknown, document: Schema, depth: number): boolean {
    if (!isRecord(raw)) return true;
    if (typeof raw.$id === "string") document = raw;
    const documents = seen.get(raw) ?? new Set<Schema>();
    if (documents.has(document)) return true;
    if (depth >= maxSchemaDepth || Object.hasOwn(raw, "$dynamicRef")) return false;
    documents.add(document);
    seen.set(raw, documents);
    schemas.push({ schema: raw, document });
    if (isSecret(raw)) return true;

    if (Object.hasOwn(raw, "$ref")) {
      const target = typeof raw.$ref === "string" ? resolve(raw.$ref, { registry, document }) : undefined;
      if (!target || !visit(target.schema, target.document, depth + 1)) return false;
    }
    const dependencies = isRecord(raw.dependentSchemas) ? Object.values(raw.dependentSchemas) : [];
    // Include every possible branch, even when the current value fails its condition or omits its trigger.
    const branches: readonly unknown[] = [
      raw.if, raw.then, raw.else, raw.not, ...dependencies,
      ...[raw.allOf, raw.oneOf, raw.anyOf].flatMap((entries): unknown[] => Array.isArray(entries) ? entries : []),
    ];
    return branches.every((branch) => visit(branch, document, depth + 1));
  }

  return sources.every(({ schema, document }) => visit(schema, document, 0)) ? schemas : undefined;
}

function propertySchemas(schema: Schema, key: string): unknown[] {
  const patterns = isRecord(schema.patternProperties) ? Object.entries(schema.patternProperties) : [];
  const matched = patterns.filter(([pattern]) => matchesPattern(key, pattern));
  const property = own(schema.properties, key);
  return [
    property, ...matched.map(([, child]) => child), schema.unevaluatedProperties,
    property === undefined && matched.length === 0 ? schema.additionalProperties : undefined,
  ];
}

function itemSchemas(schema: Schema, index: number): unknown[] {
  return [
    Array.isArray(schema.prefixItems) && index < schema.prefixItems.length ? schema.prefixItems[index] : schema.items,
    schema.contains, schema.unevaluatedItems,
  ];
}

function schemasBelow(schema: Schema, key: string | undefined): unknown[] {
  if (key === undefined) return [
    ...[schema.properties, schema.patternProperties].flatMap((entries) => isRecord(entries) ? Object.values(entries) : []),
    ...(Array.isArray(schema.prefixItems) ? schema.prefixItems : []),
    schema.additionalProperties, schema.unevaluatedProperties, schema.items, schema.contains, schema.unevaluatedItems,
  ];
  const index = Number(key);
  return [
    ...propertySchemas(schema, key),
    ...(Number.isSafeInteger(index) && index >= 0 && String(index) === key ? itemSchemas(schema, index) : []),
  ];
}

export function schemaTouchesSecret(schema: unknown, registry: SchemaRegistry, path: readonly string[]): boolean {
  const seen = new Map<Schema, Set<Schema>>();

  function visit(source: SchemaLocation, depth: number): boolean {
    if (depth >= maxSchemaDepth) return true;
    const key = path[depth];
    if (key === undefined) {
      const documents = seen.get(source.schema) ?? new Set<Schema>();
      if (documents.has(source.document)) return false;
      documents.add(source.document);
      seen.set(source.schema, documents);
    }
    const schemas = redactionSchemas([source], registry);
    return !schemas || schemas.some(({ schema, document }) => isSecret(schema) ||
      schemasBelow(schema, key).some((child) => isRecord(child) && visit({ schema: child, document }, depth + 1)));
  }

  return isRecord(schema) && visit({ schema, document: schema }, 0);
}

function redactedValue(
  value: unknown, sources: readonly SchemaLocation[], registry: SchemaRegistry, depth: number,
): unknown {
  if (value === undefined || value === null) return value;
  if (depth >= maxSchemaDepth) return masked;
  const schemas = redactionSchemas(sources, registry);
  if (!schemas) return masked;
  if (schemas.some(({ schema }) => isSecret(schema))) return isSecretReference(value) ? value : masked;

  const redactChild = (entry: unknown, children: (schema: Schema) => readonly unknown[]) =>
    redactedValue(entry, schemas.flatMap(({ schema, document }) =>
      children(schema).filter(isRecord).map((child) => ({ schema: child, document })),
    ), registry, depth + 1);

  if (Array.isArray(value) && schemas.some(({ schema }) => schema.type === "array" ||
    ["prefixItems", "items", "contains", "unevaluatedItems"].some((key) => Object.hasOwn(schema, key)))) {
    return value.map((entry: unknown, index) => redactChild(entry, (schema) => itemSchemas(schema, index)));
  }
  if (isRecord(value) && schemas.some(({ schema }) => schema.type === "object" ||
    ["properties", "patternProperties", "additionalProperties", "unevaluatedProperties"].some((key) => Object.hasOwn(schema, key)))) {
    return Object.fromEntries(Object.entries(value).map(([key, entry]) =>
      [key, redactChild(entry, (schema) => propertySchemas(schema, key))]));
  }
  if (schemas.some(({ schema }) => choices(schema)?.some((choice) => jsonEqual(choice, value)) ||
    (typeof value !== "object" && schema.type === typeof value) ||
    (schema.type === "integer" && typeof value === "number"))) return value;
  return masked;
}

function redactor(schema: Schema, { document, registry }: Context) {
  return (value: unknown) => redactedValue(value, [{ schema, document }], registry, 0);
}

function fallback(base: BaseNode, context: Context, ...keywords: string[]): UnsupportedNode {
  return {
    ...base, kind: "unsupported", widget: "json", keywords,
    redact: redactor(base.schema, context),
  };
}

function choices(schema: Schema): readonly unknown[] | undefined {
  return Array.isArray(schema.enum) && schema.enum.length > 0 ? schema.enum :
    Object.hasOwn(schema, "const") ? [schema.const] : undefined;
}

function matchesType(value: unknown, type: unknown): boolean {
  if (Array.isArray(type)) return type.some((entry: unknown) => matchesType(value, entry));
  switch (type) {
    case undefined: return true;
    case "null": return value === null;
    case "array": return Array.isArray(value);
    case "object": return isRecord(value);
    case "integer": return Number.isInteger(value);
    case "string":
    case "boolean":
    case "number": return typeof value === type;
    default: return false;
  }
}

function oneOf(base: BaseNode, context: Context): SchemaNode {
  const { schema, pointer } = base;
  const discriminator = string(schema["x-skm-discriminator"]);
  if (!discriminator || !Array.isArray(schema.oneOf) || schema.oneOf.length === 0) {
    return fallback(base, context, "oneOf");
  }
  const variants: Variant[] = [];
  for (const branch of schema.oneOf as unknown[]) {
    const node = compile(branch, pointer, context);
    const resolved = node.kind === "object" ? node.properties.find(({ key }) => key === discriminator)?.node : undefined;
    const property = resolved?.schema ?? own(node.schema.properties, discriminator);
    const tags = resolved?.kind !== "secretRef" && resolved?.kind !== "unsupported" && isRecord(property) && !isSecret(property)
      ? choices(property)?.filter((tag) => matchesType(tag, property.type)) : undefined;
    if (!tags?.length || (node.kind !== "object" && node.kind !== "unsupported") ||
      tags.some((tag) => variants.some((variant) => variant.tags.some((other) => jsonEqual(other, tag))))) {
      return fallback(base, context, "oneOf", "x-skm-discriminator");
    }
    variants.push({ node, tags });
  }
  return { ...base, kind: "oneOf", widget: "select", discriminator, variants, redact: redactor(schema, context) };
}

function object(base: BaseNode, context: Context): SchemaNode {
  const { schema, pointer, ui } = base;
  const entry = isRecord(schema.additionalProperties) ? compile(schema.additionalProperties, pointer, context) : undefined;
  if (isRecord(schema.properties)) {
    const required = Array.isArray(schema.required) ? schema.required : [];
    const properties = Object.entries(schema.properties).map(([key, child]) => ({
      key, node: compile(child, appendPointer(pointer, key), context), required: required.includes(key),
    }));
    properties.sort((left, right) => left.node.ui.order - right.node.ui.order);
    return { ...base, kind: "object", widget: ui.widget === "collapsed" ? "collapsed" : "fieldset",
      properties, ...(entry && { entry }) };
  }
  if (entry) return { ...base, kind: "map", widget: "map", entry };
  return fallback(base, context, "object");
}

function classify(base: BaseNode, context: Context, secret: boolean): SchemaNode {
  const { schema, ui, pointer } = base;
  const widget = ui.widget;
  const unsupported: string[] = unsupportedKeywords.filter((keyword) => Object.hasOwn(schema, keyword));
  if (widget === "json") unsupported.push("x-skm.ui.widget: json");
  if (schema.type !== undefined && !supportedTypes.has(schema.type)) unsupported.push("type");
  if (secret && Object.hasOwn(schema, "oneOf")) unsupported.push("oneOf");
  if (unsupported.length) return fallback(base, context, ...unsupported);
  if (secret) return { ...base, kind: "secretRef", widget: "secret" };
  if (Object.hasOwn(schema, "oneOf")) return oneOf(base, context);
  const options = choices(schema);
  if (options) {
    return { ...base, kind: "leaf/enum", widget: widget === "select" || (widget !== "radio" && options.length > 4)
      ? "select" : "radio", options };
  }
  switch (schema.type) {
    case "string":
      return { ...base, kind: "leaf/string",
        widget: widget === "path" || widget === "textarea" || widget === "markdown" || widget === "code" ? widget : "text" };
    case "number":
    case "integer":
      return { ...base, kind: "leaf/number", widget: widget === "slider" &&
        typeof schema.minimum === "number" && typeof schema.maximum === "number" && schema.maximum >= schema.minimum
        ? "slider" : "number" };
    case "boolean":
      return { ...base, kind: "leaf/boolean", widget: widget === "switch" || widget === "toggle" ? widget : "checkbox" };
    case "array": {
      if (!isRecord(schema.items)) return fallback(base, context, "items");
      const item = compile(schema.items, appendPointer(pointer, 0), context);
      if (item.kind === "array/scalar" || item.kind === "array/object") return fallback(base, context, "items");
      const isScalar = item.kind.startsWith("leaf/") || item.kind === "secretRef";
      return { ...base, kind: isScalar ? "array/scalar" : "array/object",
        widget: isScalar && widget === "tags" ? "tags" : !isScalar && widget === "table" ? "table" : "list", item };
    }
    case "object":
      return object(base, context);
    default:
      return fallback(base, context, "schema");
  }
}

function compile(raw: unknown, pointer: string, context: Context): SchemaNode {
  if (!isRecord(raw)) return fallback(baseFor({}, pointer), context, "schema");
  let schema = raw;
  const initialDocument = typeof raw.$id === "string" ? raw : context.document;
  let document = initialDocument;
  let active = [...context.active, raw];
  let depth = context.depth;
  let secret = isSecret(raw);
  const wrappers: Schema[] = [];
  while (Object.hasOwn(schema, "$ref")) {
    const current = { ...context, document, active, depth };
    const target = typeof schema.$ref === "string" ? resolve(schema.$ref, current) : undefined;
    if (!target && isSecretRef(schema.$ref)) break;
    if (!target || depth >= maxSchemaDepth || active.includes(target.schema)) {
      return fallback(baseFor(raw, pointer), { ...context, document: initialDocument }, "$ref");
    }
    wrappers.push(schema);
    schema = target.schema;
    secret ||= isSecret(schema);
    document = target.document;
    active = [...active, schema];
    depth += 1;
  }

  for (const wrapper of wrappers.reverse()) schema = mergeReference(schema, wrapper);
  const base = baseFor(schema, pointer);
  const nested = { ...context, document, active, depth: depth + 1 };
  if (depth >= maxSchemaDepth) return fallback(base, nested, "schema depth");
  const node = classify(base, nested, secret);
  if ((node.kind === "unsupported" || node.kind === "oneOf") && wrappers.length > 0) {
    return { ...node, redact: redactor(raw, { ...context, document: initialDocument }) };
  }
  return node;
}

/** Registry keys are schema URNs. Pointers describe instance locations, not schema locations. */
export function toNode(schema: unknown, registry: SchemaRegistry = {}, pointer = ""): SchemaNode {
  return compile(schema, pointer, { registry, document: isRecord(schema) ? schema : {}, active: [], depth: 0 });
}
