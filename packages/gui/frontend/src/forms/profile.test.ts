// @vitest-environment node
import { describe, expect, it } from "vitest";
import { entryLeaves, hintOf, leavesOf, parseSchema, type MapSpec } from "./profile";
import { SCHEMA } from "./test-fixtures";

describe("profile", () => {
  const nodes = parseSchema(SCHEMA);

  it("classifies leaves, tables and maps in schema order", () => {
    expect(nodes.map((node) => `${node.kind}:${node.key}`)).toEqual([
      "leaf:title", "leaf:verbose", "leaf:mode", "table:limits", "leaf:sources", "map:profiles", "leaf:token", "leaf:cache_dir",
    ]);
    expect(leavesOf(nodes).map((leaf) => leaf.key)).toEqual(["title", "verbose", "mode", "limits.max", "limits.ratio", "sources", "token", "cache_dir"]);
  });

  it("reads the supported keywords", () => {
    const leaves = Object.fromEntries(leavesOf(nodes).map((leaf) => [leaf.key, leaf]));
    expect(leaves["limits.max"]).toMatchObject({ type: "integer", minimum: 1, maximum: 100, unsupported: [] });
    expect(leaves["mode"]?.enum).toEqual(["fast", "safe"]);
    expect(leaves["token"]?.secret).toBe(true);
    expect(leaves["cache_dir"]?.layers).toEqual(["defaults", "machine"]);
    expect(leaves["sources"]).toMatchObject({ type: "array", itemType: "string" });
    expect(hintOf(leaves["limits.max"]!)).toBe("min 1 · max 100");
  });

  it("reads a map with a table of leaves and fills the entry name", () => {
    const map = nodes.find((node) => node.kind === "map") as MapSpec;
    expect(map.pattern).toBe("^[a-z][a-z0-9-]*$");
    expect(entryLeaves(map, "fast").map((leaf) => leaf.key)).toEqual(["profiles.fast.level", "profiles.fast.label"]);
  });

  it("marks a keyword it does not know instead of failing", () => {
    const [leaf] = parseSchema({ properties: { url: { type: "string", format: "uri", oneOf: [] } } });
    expect(leaf).toMatchObject({ kind: "leaf", unsupported: ["format", "oneOf"] });
    const [odd] = parseSchema({ properties: { odd: { type: "null" } } });
    expect(odd).toMatchObject({ type: "unknown" });
    expect(parseSchema(null)).toEqual([]);
  });
});
