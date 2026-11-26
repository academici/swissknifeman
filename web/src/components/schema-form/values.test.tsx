import { describe, expect, it } from "vitest";
import { toNode } from "./profile";
import { advisoryHints, appendPointer, getAtPointer, pointerTokens, removeAtPointer, schemaIssues, setAtPointer } from "./values";

describe("RFC 6901 JSON Pointers", () => {
  it("handles the root, empty property names, ~0/~1 ordering and nested arrays", () => {
    const value = { "": { "~01": [{ "a/b~": 1 }] }, " ": false };
    const pointer = appendPointer("//~001/0", "a/b~");
    expect(pointer).toBe("//~001/0/a~1b~0");
    expect(pointerTokens("/~01/~1/~0/")).toEqual(["~1", "/", "~", ""]);
    expect(getAtPointer(value, "")).toBe(value);
    expect(getAtPointer(value, pointer)).toBe(1);
    expect(getAtPointer(value, "/ ")).toBe(false);
    const updated = setAtPointer(value, pointer, 2);
    expect(getAtPointer(updated, pointer)).toBe(2);
    expect(getAtPointer(value, pointer)).toBe(1);
    expect(removeAtPointer(updated, pointer)).toEqual({ "": { "~01": [{}] }, " ": false });
    expect(setAtPointer(value, "", null)).toBe(null);
    expect(removeAtPointer(value, "")).toBeUndefined();
  });

  it("appends at the end, splices on remove and declines sparse or invalid array indices", () => {
    const value = { array: ["a", "b"] };
    expect(setAtPointer(value, "/array/2", "c")).toEqual({ array: ["a", "b", "c"] });
    expect(removeAtPointer(value, "/array/0")).toEqual({ array: ["b"] });
    for (const token of ["00", "-1", "-", "3", "9007199254740993", "0\n", "~2", "~", "length"]) {
      const pointer = `/array/${token}`;
      expect(getAtPointer(value, pointer)).toBeUndefined();
      expect(setAtPointer(value, pointer, "c")).toBe(value);
      expect(removeAtPointer(value, pointer)).toBe(value);
    }
    expect(removeAtPointer(value, "/array/0/unknown")).toBe(value);
    expect(setAtPointer(value, "array/0", "c")).toBe(value);
  });

  it("treats prototype names as own JSON properties", () => {
    expect(getAtPointer({}, "/constructor")).toBeUndefined();
    expect(getAtPointer({}, "/__proto__")).toBeUndefined();
    const written = setAtPointer({}, "/__proto__/constructor/0", true);
    expect(Object.getPrototypeOf(written)).toBe(Object.prototype);
    expect(getAtPointer(written, "/__proto__/constructor/0")).toBe(true);
    expect(removeAtPointer(written, "/__proto__")).toEqual({});
  });
});

describe("validation inputs", () => {
  it("extracts only well-formed issues from HTTP 422 SCHEMA_INVALID", () => {
    const issue = { pointer: "/items/0/title", code: "minLength", message: "Too short" };
    const error = { status: 422, code: "SCHEMA_INVALID", details: { issues: [issue, null, { ...issue, pointer: 0 }] } };
    expect(schemaIssues(error)).toEqual([issue]);
    expect(schemaIssues({ ...error, status: 400 })).toEqual([]);
    expect(schemaIssues({ ...error, code: "OTHER" })).toEqual([]);
    expect(schemaIssues({ ...error, details: {} })).toEqual([]);
  });

  it("checks required, types, Unicode lengths, numeric bounds and multiples as hints", () => {
    const text = toNode({ type: "string", minLength: 2, maxLength: 3, pattern: "^a" });
    expect(advisoryHints(text, undefined, true)).toEqual(["Обязательное поле"]);
    expect(advisoryHints(text, undefined, false)).toEqual([]);
    expect(advisoryHints(text, 1, false)).toEqual(["Ожидается строка"]);
    expect(advisoryHints(text, "😀", true)).toEqual(["Минимум 2 символов", "Строка не соответствует шаблону"]);
    expect(advisoryHints(text, "a😀😀😀", true)).toEqual(["Максимум 3 символов"]);
    expect(advisoryHints(toNode({ type: "string", pattern: "[" }), "x", false)).toEqual([]);
    const integer = toNode({ type: "integer", minimum: 0, exclusiveMinimum: 1, maximum: 4, multipleOf: 2 });
    expect(advisoryHints(integer, -0.5, false)).toHaveLength(4);
    expect(advisoryHints(integer, 6, false)).toEqual(["Максимум 4"]);
    expect(advisoryHints(toNode({ type: "number", multipleOf: 0.1 }), 0.3, false)).toEqual([]);
    expect(advisoryHints(toNode({ type: "boolean" }), "false", false)).toEqual(["Ожидается логическое значение"]);
  });

  it.each([
    ["uri", "https://example.com/path", "/relative/path"],
    ["date-time", "2024-02-29T16:00:00+02:00", "2025-02-29T16:00:00+02:00"],
    ["uuid", "123e4567-e89b-12d3-a456-426614174000", "00000000-invalid"],
  ])("advises on %s", (format, good, bad) => {
    const node = toNode({ type: "string", format });
    expect(advisoryHints(node, good, false)).toEqual([]);
    expect(advisoryHints(node, bad, false)).toEqual([`Ожидается формат ${format}`]);
  });
});
