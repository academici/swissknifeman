// @vitest-environment node
import { describe, expect, it } from "vitest";
import { emptyDraft, parseInteger, parseNumber, previewRequest, rebase, setValue, threeWay, toPatch, unsetValue, valueOf } from "./draft";
import { changed, projectView } from "./test-fixtures";

function draft() {
  const made = emptyDraft(projectView, "project");
  if (!made) throw new Error("no draft");
  return made;
}

describe("draft", () => {
  it("starts from the revision and the layer values of the view", () => {
    const start = draft();
    expect(start.revision).toBe("sha256:" + "2".repeat(64));
    expect(start.base["limits.max"]).toBe(6);
    expect(start.base["mode"]).toBeNull();
    expect(emptyDraft(projectView, "machine")?.revision).toBe("sha256:" + "1".repeat(64));
  });

  it("makes no draft for a layer that is not writable", () => {
    const view = changed(projectView, (copy) => { copy.layers[2]!.writable = false; copy.layers[2]!.revision = null; });
    expect(emptyDraft(view, "project")).toBeNull();
  });

  it("builds the patch in the order of editing", () => {
    let next = setValue(draft(), "mode", "fast");
    next = setValue(next, "limits.max", 7);
    next = unsetValue(next, "profiles.fast.level");
    next = setValue(next, "mode", "safe"); // edited again: it moves to the end
    expect(toPatch(next)).toEqual([
      { op: "set", key: "limits.max", value: 7 },
      { op: "unset", key: "profiles.fast.level" },
      { op: "set", key: "mode", value: "safe" },
    ]);
    expect(previewRequest(next)).toMatchObject({
      $schema: "urn:swissknifeman:gui:config-mutation:v1", kind: "preview_request", module: "config-demo", layer: "project",
      expected_revision: "sha256:" + "2".repeat(64),
    });
  });

  it("takes an operation back when it changes nothing", () => {
    expect(setValue(draft(), "limits.max", 6).ops.size).toBe(0);
    expect(unsetValue(draft(), "mode").ops.size).toBe(0); // not in the file
    expect(valueOf(unsetValue(draft(), "limits.max"), "limits.max")).toBeNull();
  });

  it("parses numbers by type only", () => {
    expect(parseInteger("12")).toBe(12);
    expect(parseInteger("-3")).toBe(-3);
    for (const text of ["", "1.5", "abc", "1e3", " "]) expect(parseInteger(text)).toBeNull();
    expect(parseNumber("0.25")).toBe(0.25);
    expect(parseNumber("x")).toBeNull();
    expect(parseNumber("")).toBeNull();
  });

  it("compares three ways by key", () => {
    let mine = setValue(draft(), "limits.max", 7); // base 6
    mine = setValue(mine, "mode", "fast"); // base null
    mine = setValue(mine, "limits.ratio", 0.1); // base null
    const current = {
      ...mine.base,
      "limits.max": 9, // both changed, differently
      mode: "fast", // both made the same change
      "profiles.fast.level": 5, // only the file changed
    };
    const states = Object.fromEntries(threeWay(mine, current).map((state) => [state.key, state.status]));
    expect(states).toEqual({ "limits.max": "conflict", mode: "same", "limits.ratio": "same", "profiles.fast.level": "theirs" });
  });

  it("reapplies the draft on the new revision without the operations that became no-ops", () => {
    let mine = setValue(draft(), "limits.max", 7);
    mine = setValue(mine, "mode", "fast");
    const fresh = changed(projectView, (copy) => {
      copy.layers[2]!.revision = "sha256:" + "3".repeat(64);
      copy.entries.find((entry) => entry.key === "mode")!.layer_values.project = "fast";
    });
    const next = rebase(mine, fresh)!;
    expect(next.revision).toBe("sha256:" + "3".repeat(64));
    expect(toPatch(next)).toEqual([{ op: "set", key: "limits.max", value: 7 }]);
  });
});
