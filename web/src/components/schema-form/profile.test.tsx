import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { toNode, type SchemaNode } from "./profile";
import { own } from "./values";

const load = (path: string): unknown => JSON.parse(readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), "../../../../src/skm/schemas", `${path}.v1.json`), "utf8",
));
const ui = (widget: string) => ({ "x-skm": { ui: { widget } } });
const string = { type: "string" };
const object = { type: "object", properties: { name: string } };
const slider = { type: "integer", minimum: 0, maximum: 5 };

describe("JSON Schema profile", () => {
  it.each([
    [string, "leaf/string", "text"],
    ...["text", "path", "textarea", "markdown", "code"].map((widget): [unknown, string, string] => [
      { ...string, ...ui(widget) }, "leaf/string", widget,
    ]),
    [{ type: "integer", ...ui("number") }, "leaf/number", "number"],
    [{ type: "number" }, "leaf/number", "number"],
    [{ ...slider, ...ui("slider") }, "leaf/number", "slider"],
    [{ type: "number", minimum: 0, ...ui("slider") }, "leaf/number", "number"],
    [{ type: "boolean" }, "leaf/boolean", "checkbox"],
    [{ type: "boolean", ...ui("switch") }, "leaf/boolean", "switch"],
    [{ type: "boolean", ...ui("toggle") }, "leaf/boolean", "toggle"],
    [{ enum: [1, false, "x", null] }, "leaf/enum", "radio"],
    [{ enum: [1, 2, 3, 4, 5] }, "leaf/enum", "select"],
    [{ enum: ["x"], ...ui("select") }, "leaf/enum", "select"],
    [{ enum: ["x"], ...ui("radio") }, "leaf/enum", "radio"],
    [{ const: false }, "leaf/enum", "radio"],
    [{ type: "array", items: string }, "array/scalar", "list"],
    [{ type: "array", items: string, ...ui("tags") }, "array/scalar", "tags"],
    [{ type: "array", items: object }, "array/object", "list"],
    [{ type: "array", items: object, ...ui("table") }, "array/object", "table"],
    [object, "object", "fieldset"],
    [{ ...object, ...ui("collapsed") }, "object", "collapsed"],
    [{ type: "object", additionalProperties: string, propertyNames: { pattern: "^x" } }, "map", "map"],
    [{ type: "object", additionalProperties: string, ...ui("map") }, "map", "map"],
    [{ $ref: "urn:skm:config:secret-ref:v1" }, "secretRef", "secret"],
    [{ ...string, "x-skm": { sensitivity: "secret" } }, "secretRef", "secret"],
    [{ ...string, ...ui("secret") }, "secretRef", "secret"],
  ])("maps %j to %s (%s)", (schema, kind, widget) => {
    expect(toNode(schema)).toMatchObject({ kind, widget });
  });

  it.each([
    [{ ...string, if: {}, then: {}, else: {} }, ["if", "then", "else"]],
    [{ ...string, allOf: [{}] }, ["allOf"]],
    [{ ...string, not: {} }, ["not"]],
    [{ ...object, patternProperties: { x: string } }, ["patternProperties"]],
    [{ ...string, anyOf: [string] }, ["anyOf"]],
    [{ oneOf: [object] }, ["oneOf"]],
    [{ type: "null" }, ["type"]],
    [{ type: "unknown" }, ["type"]],
    [{ type: ["string", "null"] }, ["type"]],
    [{ ...object, ...ui("json") }, ["x-skm.ui.widget: json"]],
    [true, ["schema"]],
    [{ $ref: "urn:skm:missing:v1" }, ["$ref"]],
    [{ $ref: "#/%ZZ" }, ["$ref"]],
  ])("reports an unsupported schema %j", (schema, keywords) => {
    expect(toNode(schema)).toMatchObject({ kind: "unsupported", widget: "json", keywords });
  });

  it("expands root, local and external pointer URNs with resource-local scope and overlays UI", () => {
    const externalUrn = "urn:example:schema";
    const external = { $id: externalUrn, ...object, $defs: { "a/~": {
      $ref: "#/$defs/label", title: "External", "x-skm": { ui: { title: "External UI", group: "External group" } },
    }, label: string } };
    const schema = {
      type: "object",
      $defs: { label: { type: "integer" } },
      required: ["a/b~"],
      properties: {
        last: { $ref: externalUrn },
        "a/b~": { $ref: `${externalUrn}#/$defs/a~1%7E0`,
          "x-skm": { ui: { title: "Local UI", order: 1, advanced: true, help_url: "https://example.org/" } } },
        sameOrder: { $ref: "#/$defs/label", "x-skm": { ui: { order: 1 } } },
        sibling: { $ref: `${externalUrn}#/$defs/a~1~0` },
      },
    };

    const node = toNode(schema, { [externalUrn]: external }, "/root");
    expect(node.kind).toBe("object");
    if (node.kind !== "object") return;
    expect(node.properties.map(({ key }) => key)).toEqual(["a/b~", "sameOrder", "last", "sibling"]);
    expect(node.properties).toMatchObject([
      { required: true, node: { pointer: "/root/a~1b~0", kind: "leaf/string", title: "Local UI",
        ui: { group: "External group", order: 1, advanced: true, helpUrl: "https://example.org/" } } },
      { node: { kind: "leaf/number" } },
      { node: { kind: "object" } },
      { node: { kind: "leaf/string" } },
    ]);
  });

  it("terminates actual specification refs and handles its tagged branches", () => {
    const spec = load("planning/specification");
    const urn = "urn:skm:planning:specification:v1";
    const registry = { [urn]: spec };
    const node = toNode(spec);
    expect(node.kind).toBe("object");
    expect(property(property(node, "items"), "review")).toMatchObject({
      kind: "oneOf", discriminator: "mode",
      variants: [{ tags: ["required"] }, { tags: ["self"] }, { tags: ["waived"] }],
    });
    for (const definition of ["authority", "read", "check", "unit_command", "material"]) {
      expect(toNode({ $ref: `${urn}#/$defs/${definition}` }, registry)).toMatchObject({ kind: "oneOf", discriminator: "kind" });
    }
    const read = toNode({ $ref: `${urn}#/$defs/read` }, registry);
    expect(read.kind === "oneOf" && read.variants.at(-1)?.node).toMatchObject({ kind: "unsupported", keywords: ["allOf"] });
  });

  it("bounds self and mutual cycles and allows independent repeated refs", () => {
    const a = "urn:example:a";
    const b = "urn:example:b";
    const registry = {
      [a]: { $id: a, type: "object", $defs: { loop: { $ref: "#/$defs/loop" } },
        properties: { local: { $ref: "#/$defs/loop" }, other: { $ref: b }, self: { $ref: "#" } } },
      [b]: { $id: b, type: "object", properties: { other: { $ref: a }, name: string } },
    };
    const node = toNode(registry[a], registry);
    for (const key of ["local", "self"]) {
      expect(property(node, key)).toMatchObject({ kind: "unsupported", keywords: ["$ref"] });
    }
    expect(property(property(node, "other"), "other")).toMatchObject({ kind: "unsupported", keywords: ["$ref"] });

    const spec = load("planning/specification");
    const defs = own(spec, "$defs");
    const review = own(defs, "review");
    const branches = own(review, "oneOf");
    if (!Array.isArray(branches)) throw new Error("Missing review variants");
    const recursiveSpec = {
      ...(spec as object),
      $defs: {
        ...(defs as object),
        review: { ...(review as object), oneOf: branches.map((branch: unknown, index) => index === 0 ? {
          ...(branch as object),
          properties: { ...(own(branch, "properties") as object), target: { $ref: "#/$defs/item" } },
        } : branch) },
      },
    };
    const reviewNode = property(property(toNode(recursiveSpec), "items"), "review");
    expect(reviewNode?.kind).toBe("oneOf");
    if (reviewNode?.kind === "oneOf") {
      expect(property(reviewNode.variants[0]?.node, "target")).toMatchObject({ kind: "unsupported", keywords: ["$ref"] });
    }
  });

  it("bounds an acyclic chain of excessive depth", () => {
    const defs = Object.fromEntries(Array.from({ length: 80 }, (_, index) => [
      String(index), index === 79 ? string : { $ref: `#/$defs/${index + 1}` },
    ]));
    expect(toNode({ $defs: defs, $ref: "#/$defs/0" })).toMatchObject({ kind: "unsupported", keywords: ["$ref"] });
  });

  it("uses the actual config metadata and secret reference schemas", () => {
    const keySpec = load("config/key-spec");
    const secret = load("config/secret-ref");
    const keyUrn = "urn:skm:config:key-spec:v1";
    expect(toNode(secret)).toMatchObject({ kind: "secretRef" });
    const widget = toNode({ $ref: `${keyUrn}#/properties/ui/properties/widget` }, { [keyUrn]: keySpec });
    expect(widget).toMatchObject({ kind: "leaf/enum", widget: "select", options: [
      "toggle", "number", "select", "text", "textarea", "path", "tags", "map", "json", "secret",
    ] });
    const hooks = load("settings/hooks");
    const integrationUrn = "urn:skm:integrations:defs:v1";
    const registry = { [integrationUrn]: load("integrations/defs") };
    const section = toNode(hooks, registry);
    expect(property(section, "subscriptions")).toMatchObject({ kind: "unsupported", keywords: ["x-skm.ui.widget: json"] });
    expect(toNode({ $ref: `${integrationUrn}#/$defs/hook_subscription` }, registry))
      .toMatchObject({ kind: "unsupported", keywords: ["allOf"] });
  });

  it("accepts enum tags, rejects ambiguous tags, and preserves unsupported variants", () => {
    const tag = (keyword: object) => ({ type: "object", properties: { kind: keyword } });
    const first = tag({ enum: ["a", "b"] });
    const schema = { "x-skm-discriminator": "kind", oneOf: [first, { ...tag({ const: "c" }), allOf: [{}] }] };
    expect(toNode(schema)).toMatchObject({ kind: "oneOf", variants: [
      { tags: ["a", "b"], node: { kind: "object" } },
      { tags: ["c"], node: { kind: "unsupported" } },
    ] });
    expect(toNode({ ...schema, oneOf: [first, tag({ const: "b" })] })).toMatchObject({ kind: "unsupported" });
  });

  it("applies the discriminator type before checking oneOf tag overlap", () => {
    const branch = (kind: object) => ({ type: "object", properties: { kind } });
    const schema = { "x-skm-discriminator": "kind", oneOf: [
      branch({ type: "string", enum: ["auto", false] }),
      branch({ type: "boolean", const: false }),
    ] };
    expect(toNode(schema)).toMatchObject({ kind: "oneOf", variants: [{ tags: ["auto"] }, { tags: [false] }] });
    expect(toNode({ ...schema, oneOf: [schema.oneOf[0], branch({ type: "string", const: true })] }))
      .toMatchObject({ kind: "unsupported" });
  });
});

function property(node: SchemaNode | undefined, key: string): SchemaNode | undefined {
  if (node?.kind === "array/object" || node?.kind === "array/scalar") return property(node.item, key);
  return node?.kind === "object" ? node.properties.find((child) => child.key === key)?.node : undefined;
}
