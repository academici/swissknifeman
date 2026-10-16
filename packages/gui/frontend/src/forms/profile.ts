// Reads a node of the closed profile of aicore (config.schema.json) into what the renderer draws: a leaf, a table
// or a map. There is no validation here (D6): constraints are hints, the backend preview decides.
import type { Scalar } from "./types";

/** The keywords the renderer understands; a node with any other keyword is shown read-only as unsupported. */
export const SUPPORTED = new Set([
  "type", "title", "description", "default", "enum", "minimum", "maximum", "minLength", "pattern", "items",
  "properties", "additionalProperties", "patternProperties", "x-skm-secret", "x-skm-layers",
]);
const LEAF_TYPES = new Set(["string", "integer", "number", "boolean", "array"]);

export type LeafType = "string" | "integer" | "number" | "boolean" | "array";

export interface LeafSpec {
  kind: "leaf";
  /** Dotted key; inside a map template the entry name is `*`. */
  key: string;
  name: string;
  type: LeafType | "unknown";
  itemType?: "string" | "integer" | "number" | "boolean";
  enum?: Scalar[];
  minimum?: number;
  maximum?: number;
  minLength?: number;
  pattern?: string;
  secret: boolean;
  layers: string[] | null;
  description: string | null;
  title: string | null;
  unsupported: string[];
}

export interface TableSpec {
  kind: "table";
  key: string;
  name: string;
  title: string | null;
  description: string | null;
  children: NodeSpec[];
  unsupported: string[];
}

export interface MapSpec {
  kind: "map";
  key: string;
  name: string;
  title: string | null;
  description: string | null;
  pattern: string | null;
  /** An entry that is one leaf. */
  valueLeaf: LeafSpec | null;
  /** An entry that is a table of leaves. */
  valueTable: LeafSpec[] | null;
  unsupported: string[];
}

export type NodeSpec = LeafSpec | TableSpec | MapSpec;

type Json = Record<string, unknown>;

const isObject = (value: unknown): value is Json => typeof value === "object" && value !== null && !Array.isArray(value);
const text = (value: unknown): string | null => (typeof value === "string" && value !== "" ? value : null);
const number = (value: unknown): number | undefined => (typeof value === "number" ? value : undefined);

function unsupportedOf(node: Json): string[] {
  return Object.keys(node).filter((keyword) => !SUPPORTED.has(keyword)).sort();
}

function leafOf(node: Json, key: string, name: string): LeafSpec {
  const unsupported = unsupportedOf(node);
  const type = typeof node.type === "string" && LEAF_TYPES.has(node.type) ? (node.type as LeafType) : "unknown";
  if (type === "unknown") unsupported.push("type");
  const spec: LeafSpec = {
    kind: "leaf", key, name, type, secret: node["x-skm-secret"] === true,
    layers: Array.isArray(node["x-skm-layers"]) ? node["x-skm-layers"].filter((layer): layer is string => typeof layer === "string") : null,
    description: text(node.description), title: text(node.title), unsupported,
  };
  if (Array.isArray(node.enum)) spec.enum = node.enum.filter((item): item is Scalar => ["string", "number", "boolean"].includes(typeof item));
  const minimum = number(node.minimum);
  const maximum = number(node.maximum);
  const minLength = number(node.minLength);
  if (minimum !== undefined) spec.minimum = minimum;
  if (maximum !== undefined) spec.maximum = maximum;
  if (minLength !== undefined) spec.minLength = minLength;
  if (typeof node.pattern === "string") spec.pattern = node.pattern;
  if (type === "array") {
    const items = isObject(node.items) ? node.items : null;
    const itemType = items && typeof items.type === "string" ? items.type : null;
    if (itemType === "string" || itemType === "integer" || itemType === "number" || itemType === "boolean") spec.itemType = itemType;
    else spec.unsupported.push("items");
  }
  return spec;
}

function join(base: string, name: string): string {
  return base ? `${base}.${name}` : name;
}

function tableOf(node: Json, key: string, name: string): TableSpec | MapSpec {
  const unsupported = unsupportedOf(node);
  const patterns = isObject(node.patternProperties) ? node.patternProperties : null;
  if (patterns && Object.keys(patterns).length > 0) {
    const [pattern, value] = Object.entries(patterns)[0] as [string, unknown];
    if (Object.keys(patterns).length > 1) unsupported.push("patternProperties");
    const entry = isObject(value) ? value : {};
    const spec: MapSpec = {
      kind: "map", key, name, title: text(node.title), description: text(node.description), pattern,
      valueLeaf: null, valueTable: null, unsupported,
    };
    if (isObject(entry.properties)) {
      spec.valueTable = Object.entries(entry.properties).map(([prop, child]) =>
        leafOf(isObject(child) ? child : {}, join(join(key, "*"), prop), prop));
    } else {
      spec.valueLeaf = leafOf(entry, join(key, "*"), "*");
    }
    return spec;
  }
  const properties = isObject(node.properties) ? node.properties : {};
  return {
    kind: "table", key, name, title: text(node.title), description: text(node.description), unsupported,
    children: Object.entries(properties).map(([child, value]) => nodeOf(isObject(value) ? value : {}, join(key, child), child)),
  };
}

function nodeOf(node: Json, key: string, name: string): NodeSpec {
  return node.type === "object" ? tableOf(node, key, name) : leafOf(node, key, name);
}

/** The nodes below the root of a module schema, in schema order. */
export function parseSchema(schema: unknown): NodeSpec[] {
  if (!isObject(schema)) return [];
  const properties = isObject(schema.properties) ? schema.properties : {};
  return Object.entries(properties).map(([name, value]) => nodeOf(isObject(value) ? value : {}, name, name));
}

/** Every leaf of the nodes (not inside maps), in order. */
export function leavesOf(nodes: NodeSpec[]): LeafSpec[] {
  return nodes.flatMap((node) => (node.kind === "leaf" ? [node] : node.kind === "table" ? leavesOf(node.children) : []));
}

/** The leaf template of a map entry with the entry name filled in. */
export function entryLeaves(spec: MapSpec, entry: string): LeafSpec[] {
  const fill = (leaf: LeafSpec): LeafSpec => ({ ...leaf, key: leaf.key.replace("*", entry), name: leaf.name === "*" ? entry : leaf.name });
  return spec.valueTable ? spec.valueTable.map(fill) : spec.valueLeaf ? [fill(spec.valueLeaf)] : [];
}

/** A short text of the constraints of a leaf, shown as a hint. */
export function hintOf(spec: LeafSpec): string {
  const parts: string[] = [];
  if (spec.minimum !== undefined) parts.push(`min ${spec.minimum}`);
  if (spec.maximum !== undefined) parts.push(`max ${spec.maximum}`);
  if (spec.minLength !== undefined) parts.push(`min length ${spec.minLength}`);
  if (spec.pattern !== undefined) parts.push(`pattern ${spec.pattern}`);
  if (spec.enum) parts.push(`one of ${spec.enum.join(", ")}`);
  return parts.join(" · ");
}
