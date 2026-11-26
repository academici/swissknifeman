// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/errors";
import { SchemaForm, type SchemaFormProps } from "./SchemaForm";
import { isSecretReference } from "./values";

afterEach(cleanup);

const text = { type: "string" };
const object = (properties: Record<string, unknown>, required: string[] = []) => ({ type: "object", properties, required });
const ui = (widget: string, extras: object = {}) => ({ "x-skm": { ui: { widget, ...extras } } });
const variantSchema = {
  title: "Проверка", "x-skm-discriminator": "kind",
  oneOf: [
    object({ kind: { const: "auto" }, shared: text, command: text }, ["kind", "command"]),
    object({ kind: { enum: ["manual", "reviewed"] }, shared: text, reason: { ...text, default: "review" } }),
    { ...object({ kind: { const: "imported" }, extra: text }), allOf: [{}] },
  ],
};

function Editable({ value: initial, ...props }: SchemaFormProps) {
  const [value, setValue] = useState(initial);
  return <SchemaForm {...props} value={value} onChange={(next) => { setValue(next); props.onChange?.(next); }} />;
}

function serverError(issues: { pointer: string; message: string; code?: string }[]) {
  return ApiError.fromResponse(422, {
    code: "SCHEMA_INVALID", category: "validation", details: {
      issues: issues.map((issue) => ({ code: "invalid", ...issue })),
    },
  }, "req-form-test", "/config/import");
}

describe("SchemaForm editing", () => {
  it("uses accessible native scalar controls and preserves typed enum values", async () => {
    const schema = object({
      name: { ...text, minLength: 3, description: "Видимое имя" },
      rounds: { type: "integer", minimum: 1, maximum: 8, ...ui("slider") },
      count: { type: "integer" },
      enabled: { type: "boolean" },
      locked: { type: "boolean", ...ui("switch") },
      modes: { enum: [false, 2], ...ui("select") },
      choice: { enum: [1, { x: 2, y: 3 }] },
    }, ["name"]);
    const value = { name: "a", rounds: 2, count: 4, enabled: false, locked: true, modes: false, choice: { y: 3, x: 2 } };
    const change = vi.fn();
    render(<Editable schema={schema} value={value} onChange={change} />);
    const user = userEvent.setup();
    const name = screen.getByRole("textbox", { name: "name" });
    expect((name as HTMLInputElement).labels?.[0]?.htmlFor).toBe(name.id);
    expect(name.getAttribute("aria-required")).toBe("true");
    expect(name.hasAttribute("aria-invalid")).toBe(false);
    expect(screen.getByText("Минимум 3 символов")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    await user.tab();
    expect(document.activeElement).toBe(name);
    fireEvent.change(name, { target: { value: "good" } });
    expect(change).toHaveBeenLastCalledWith({ ...value, name: "good" });

    fireEvent.change(screen.getByRole("slider", { name: "rounds" }), { target: { value: "5" } });
    fireEvent.change(screen.getByRole("spinbutton", { name: "count" }), { target: { value: "" } });
    await user.click(screen.getByRole("checkbox", { name: "enabled" }));
    await user.click(screen.getByRole("switch", { name: "locked" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "modes" }), "1");
    const choice = within(screen.getByRole("group", { name: "choice" }));
    expect((choice.getByRole("radio", { name: '{"x":2,"y":3}' }) as HTMLInputElement).checked).toBe(true);
    await user.click(choice.getByRole("radio", { name: "1" }));
    expect(change).toHaveBeenLastCalledWith({ name: "good", rounds: 5, enabled: true, locked: false, modes: 2, choice: 1 });
  });

  it("adds, edits, reorders and removes scalar and object array entries", async () => {
    const schema = object({
      tags: { type: "array", items: text, ...ui("tags") },
      rows: { type: "array", items: object({ name: text }), ...ui("table") },
    });
    const change = vi.fn();
    render(<Editable schema={schema} value={{ tags: ["first"], rows: [{ name: "original" }] }} onChange={change} />);
    const tags = within(screen.getByRole("group", { name: "tags" }));
    const user = userEvent.setup();
    await user.click(tags.getByRole("button", { name: "Добавить элемент" }));
    await user.type(tags.getByRole("textbox", { name: "Элемент 2" }), "second");
    await user.click(tags.getByRole("button", { name: "Поднять элемент 2" }));
    await user.click(tags.getByRole("button", { name: "Удалить элемент 2" }));
    expect(change).toHaveBeenLastCalledWith({ tags: ["second"], rows: [{ name: "original" }] });

    const rows = within(screen.getByRole("group", { name: "rows" }));
    await user.click(rows.getByRole("button", { name: "Добавить элемент" }));
    const table = within(rows.getByRole("table"));
    const row = table.getAllByRole("row")[2];
    if (!row) throw new Error("Missing added row");
    fireEvent.change(within(row).getByRole("textbox", { name: "name" }), { target: { value: "added" } });
    await user.click(within(row).getByRole("button", { name: "Поднять элемент 2" }));
    expect(change).toHaveBeenLastCalledWith({ tags: ["second"], rows: [{ name: "added" }, { name: "original" }] });
  });

  it("updates map keys containing / and ~ while keeping pattern failures advisory", async () => {
    const schema = { type: "object", additionalProperties: text, propertyNames: { pattern: "^ok/" } };
    const change = vi.fn();
    render(<Editable schema={schema} label="Map" value={{ "ok/~": "yes" }} onChange={change} />);
    const user = userEvent.setup();
    const key = screen.getByRole("textbox", { name: "Новый ключ (Map)" });
    await user.type(key, "bad/~");
    expect(screen.getByText("Ключ не соответствует шаблону")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Добавить запись" }));
    const added = screen.getByRole("textbox", { name: "bad/~" });
    expect(added.parentElement?.getAttribute("data-pointer")).toBe("/bad~1~0");
    await user.type(added, "edited");
    expect(change).toHaveBeenLastCalledWith({ "ok/~": "yes", "bad/~": "edited" });
    await user.click(screen.getByRole("button", { name: "Удалить запись ok/~" }));
    expect(change).toHaveBeenLastCalledWith({ "bad/~": "edited" });
  });

  it("edits fixed fields and dynamic entries in the same object", async () => {
    const schema = { ...object({ fixed: text, reserved: text }), additionalProperties: { type: "number" } };
    const change = vi.fn();
    render(<Editable schema={schema} label="Mixed" value={{ fixed: "left", "x/~": 5 }} onChange={change}
      serverError={serverError([{ pointer: "/x~1~0", message: "Map entry error" }])} />);
    const user = userEvent.setup();
    const fixed = screen.getByRole("textbox", { name: "fixed" });
    const entry = screen.getByRole("spinbutton", { name: "x/~" });
    expect(entry.getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByText("Map entry error").getAttribute("data-issue-pointer")).toBe("/x~1~0");
    expect(fixed.hasAttribute("aria-invalid")).toBe(false);
    fireEvent.change(fixed, { target: { value: "right" } });
    fireEvent.change(entry, { target: { value: "6" } });
    expect(change).toHaveBeenLastCalledWith({ fixed: "right", "x/~": 6 });

    const key = screen.getByRole("textbox", { name: "Новый ключ (Mixed)" });
    const add = screen.getByRole("button", { name: "Добавить запись" });
    await user.type(key, "reserved");
    expect(screen.getByText("Ключ уже существует")).toBeTruthy();
    const callCount = change.mock.calls.length;
    await user.click(add);
    expect(change).toHaveBeenCalledTimes(callCount);
    await user.clear(key);
    await user.type(key, "new");
    await user.click(add);
    expect(change).toHaveBeenLastCalledWith({ fixed: "right", "x/~": 6, new: 0 });
    await user.click(screen.getByRole("button", { name: "Удалить запись x/~" }));
    expect(change).toHaveBeenLastCalledWith({ fixed: "right", new: 0 });
  });

  it.each([false, true])("keeps cleared numeric map rows mounted (fixed properties: %s)", async (mixed) => {
    const schema = {
      ...(mixed ? object({ fixed: text }) : { type: "object" }),
      additionalProperties: { type: "number" },
    };
    const change = vi.fn();
    render(<Editable schema={schema} value={{ amount: 3 }} onChange={change} />);
    const user = userEvent.setup();
    const amount = screen.getByRole("spinbutton", { name: "amount" });
    await user.clear(amount);
    expect(change).toHaveBeenLastCalledWith({ amount: null });
    expect(screen.getByRole("spinbutton", { name: "amount" })).toBe(amount);
    expect(document.activeElement).toBe(amount);
    await user.keyboard("-2.5");
    expect(change).toHaveBeenLastCalledWith({ amount: -2.5 });
    await user.click(screen.getByRole("button", { name: "Удалить запись amount" }));
    expect(change).toHaveBeenLastCalledWith({});
  });

  it("keeps an existing enum tag and switches oneOf while preserving common fields", async () => {
    const change = vi.fn();
    render(<Editable schema={variantSchema} value={{ kind: "reviewed", shared: "keep", reason: "initial" }} onChange={change} />);
    const selection = screen.getByRole("combobox", { name: "kind" }) as HTMLSelectElement;
    expect(selection.selectedOptions[0]?.textContent).toBe("reviewed");
    expect(within(selection).getAllByRole("option").map((option) => option.textContent))
      .toEqual(["auto", "manual", "reviewed", "imported"]);
    const shared = screen.getByRole("textbox", { name: "shared" });
    fireEvent.change(shared, { target: { value: "kept" } });
    expect(change).toHaveBeenLastCalledWith({ kind: "reviewed", shared: "kept", reason: "initial" });
    const user = userEvent.setup();
    await user.selectOptions(selection, within(selection).getByRole("option", { name: "auto" }));
    expect(change).toHaveBeenLastCalledWith({ kind: "auto", shared: "kept" });
    expect(screen.getByRole("textbox", { name: "command" }).getAttribute("aria-required")).toBe("true");
    await user.selectOptions(selection, within(selection).getByRole("option", { name: "reviewed" }));
    expect(change).toHaveBeenLastCalledWith({ kind: "reviewed", shared: "kept", reason: "review" });
    fireEvent.change(screen.getByRole("textbox", { name: "reason" }), { target: { value: "updated" } });
    await user.selectOptions(selection, within(selection).getByRole("option", { name: "manual" }));
    expect(change).toHaveBeenLastCalledWith({ kind: "manual", shared: "kept", reason: "updated" });
    await user.selectOptions(selection, within(selection).getByRole("option", { name: "imported" }));
    expect(screen.getByText(/редактируйте через import/u)).toBeTruthy();
    expect(screen.queryByRole("textbox", { name: "extra" })).toBeNull();
  });

  it("opens advanced and collapsed groups for server issues and binds exact and ancestor pointers", () => {
    const schema = object({
      outer: { ...object({ nested: text }), ...ui("collapsed", { advanced: true }) },
      rows: { type: "array", items: object({ name: text }) },
      map: { type: "object", additionalProperties: text },
      variant: variantSchema,
    });
    const value = { outer: { nested: "v" }, rows: [{ name: "n" }], map: { "a/b~": "x" },
      variant: { kind: "auto", command: "c" } };
    const error = serverError([
      { pointer: "/doc/outer/nested", message: "nested error" },
      { pointer: "/doc/rows/0/name", message: "array error" },
      { pointer: "/doc/map/a~1b~0", message: "map error" },
      { pointer: "/doc/variant/command", message: "branch error" },
      { pointer: "/doc/variant/kind", message: "tag error" },
      { pointer: "/doc/variant/reason", message: "unmounted branch" },
      { pointer: "/doc/rows/9/name", message: "missing row" },
      { pointer: "/elsewhere", message: "outside form" },
      { pointer: "/doc/oops~2", message: "malformed pointer" },
    ]);
    const props = { schema, value, pointer: "/doc", onChange: vi.fn() };
    const { rerender, container } = render(<SchemaForm {...props} />);
    expect([...container.querySelectorAll("details")].map((node) => node.open)).toEqual([false, false]);
    rerender(<SchemaForm {...props} serverError={error} />);
    expect([...container.querySelectorAll("details")].map((node) => node.open)).toEqual([true, true]);
    for (const [role, name, message] of [
      ["textbox", "nested", "nested error"],
      ["textbox", "name", "array error"],
      ["textbox", "a/b~", "map error"],
      ["textbox", "command", "branch error"],
      ["combobox", "kind", "tag error"],
      ["group", "Проверка", "unmounted branch"],
      ["group", "rows", "missing row"],
    ] as const) {
      const control = screen.getByRole(role, { name });
      expect(control.getAttribute("aria-invalid")).toBe("true");
      const details = document.getElementById(control.getAttribute("aria-describedby") ?? "");
      if (!details) throw new Error(`Missing details for ${name}`);
      expect(within(details).getByRole("alert").textContent).toContain(message);
    }
    expect(screen.getByText("outside form").closest("ul")?.textContent).toBe("outside formmalformed pointer");
    fireEvent.change(screen.getByRole("textbox", { name: "nested" }), { target: { value: "edited" } });
    expect(props.onChange).toHaveBeenLastCalledWith({ ...value, outer: { nested: "edited" } });
  });
});

describe("safe schema and error rendering", () => {
  it("masks invalid secrets, accepts only well-formed reference edits, and redacts server echoes", () => {
    const schema = { title: "Credential", $ref: "urn:skm:config:secret-ref:v1" };
    const hidden = "the-plain-token";
    const change = vi.fn();
    const error = serverError([{ pointer: "", message: `Invalid ${hidden}` }]);
    const { container, rerender } = render(<SchemaForm schema={schema} value={hidden} onChange={change} serverError={error} />);
    const input = screen.getByLabelText("Credential") as HTMLInputElement;
    expect(input.type).toBe("password");
    expect(input.autocomplete).toBe("off");
    expect(input.getAttribute("spellcheck")).toBe("false");
    expect(input.value).toBe("");
    expect(container.innerHTML).not.toContain(hidden);
    expect(screen.getByRole("alert").textContent).toBe("Сервер отклонил значение");
    expect(screen.getByText(/Ожидается ссылка/u)).toBeTruthy();
    for (const bad of ["new-plaintext", "file:///var/file", "secret://env/lowercase", "secret://file/~/.secret\u061c"]) {
      fireEvent.change(input, { target: { value: bad } });
      expect(input.value).toBe("");
      expect(container.innerHTML).not.toContain(bad);
    }
    expect(change).not.toHaveBeenCalled();
    for (const reference of ["secret://env/NAME", "secret://file/~/.keys/pass", "secret://keyring/skm/name"]) {
      fireEvent.change(input, { target: { value: reference } });
      expect(change).toHaveBeenLastCalledWith(reference);
    }
    rerender(<SchemaForm schema={schema} value="secret://env/NAME" onChange={change} />);
    expect(input.value).toBe("secret://env/NAME");
  });

  it("neutralizes ancestor and form-level 422 issues while preserving field binding", () => {
    const schema = object({ credentials: object({ token: { $ref: "urn:skm:config:secret-ref:v1" } }), public: text });
    const value = { credentials: { token: "nested-plaintext" }, public: "visible" };
    const { container } = render(<SchemaForm schema={schema} value={value} pointer="/doc" serverError={serverError([
      { pointer: "/doc/credentials/token", message: `Field: ${value.credentials.token}` },
      { pointer: "/doc/credentials", message: `Ancestor: ${JSON.stringify(value.credentials)}` },
      { pointer: "/doc", message: `Document: ${JSON.stringify(value)}` },
      { pointer: "", message: `Form: ${JSON.stringify(value)}` },
      { pointer: "/doc/oops~2", code: value.credentials.token, message: "Unbound issue" },
      { pointer: "/doc/public", message: "Public field error" },
    ])} />);
    expect(container.innerHTML).not.toContain(value.credentials.token);
    const masked = screen.getAllByText("Сервер отклонил значение");
    expect(masked.map((issue) => issue.closest("[data-pointer]")?.getAttribute("data-pointer")))
      .toEqual([undefined, undefined, "/doc/credentials/token", "/doc/credentials", "/doc"]);
    expect(masked.every((issue) => !issue.hasAttribute("data-issue-pointer"))).toBe(true);
    expect(screen.getByText("Public field error").closest("[data-pointer]")?.getAttribute("data-pointer")).toBe("/doc/public");
  });

  it("masks late ancestor and form errors after the last secret map row is removed", async () => {
    const schema = object({ credentials: { type: "object", additionalProperties: { $ref: "urn:skm:config:secret-ref:v1" } } });
    const secret = "previously-submitted-token";
    const props = { schema, value: { credentials: { removed: secret } }, pointer: "/doc" };
    const { container, rerender } = render(<Editable {...props} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Удалить запись removed" }));
    expect(screen.queryByLabelText("removed")).toBeNull();

    rerender(<Editable {...props} serverError={serverError([
      { pointer: "/doc/credentials", message: `Map: ${secret}` },
      { pointer: "/doc", message: `Document: ${secret}` },
      { pointer: "", message: `Form: ${secret}` },
    ])} />);
    expect(screen.getAllByText("Сервер отклонил значение")).toHaveLength(3);
    expect(container.innerHTML).not.toContain(secret);
  });

  it("omits the sensitive map key from a masked alert pointer", () => {
    const schema = { type: "object", additionalProperties: { $ref: "urn:skm:config:secret-ref:v1" } };
    const key = "sensitive/key~";
    render(<SchemaForm schema={schema} value={{ [key]: "secret://env/TOKEN" }} serverError={serverError([
      { pointer: "/sensitive~1key~0", message: "Invalid reference" },
    ])} />);
    const input = screen.getByLabelText(key);
    const alert = screen.getByText("Сервер отклонил значение");
    expect(alert.closest("[id]")?.id).toBe(input.getAttribute("aria-describedby"));
    expect(alert.getAttribute("data-issue-pointer")).toBeNull();
  });

  it("supports typing a masked reference prefix and checks examples in the real SecretRef schema", async () => {
    const schema = load("config/secret-ref") as { examples: string[]; pattern: string };
    const change = vi.fn();
    render(<Editable schema={schema} value={undefined} onChange={change} />);
    const user = userEvent.setup();
    const input = screen.getByLabelText("SecretRef") as HTMLInputElement;
    await user.type(input, "secret://keyring/skm/");
    expect(input.value).toBe("secret://keyring/skm/");
    expect(change).not.toHaveBeenCalled();
    await user.type(input, "test");
    expect(change).toHaveBeenLastCalledWith("secret://keyring/skm/test");
    for (const example of schema.examples) {
      expect(new RegExp(schema.pattern, "u").test(example)).toBe(true);
      expect(isSecretReference(example)).toBe(true);
    }
  });

  it("escapes schema text, enum labels, scalar values, JSON and server errors and shows only safe HTTP links", () => {
    const bad = "<svg onload=alert(1)>\u202e\u0007";
    const visible = "<svg onload=alert(1)>\\u202e\\u0007";
    const urls = ["javascript:alert(1)", "data:text/html,body", "/relative", "https://host/%D8%9C",
      "https://host/a\u0001", "https://user@host/", "https://docs.example.test/guide", "http://help.example.test/"];
    const schema = object({
      main: { ...text, description: bad, ...ui("text", { title: bad, group: bad }) },
      choice: { enum: [bad] },
      unsupported: { ...object({ "<script>": text }), allOf: [{}] },
      ...Object.fromEntries(urls.map((help_url, index) => [String(index), { ...text, ...ui("text", { help_url }) }])),
    });
    const value = { main: bad, choice: bad, unsupported: { "<script>": bad } };
    const { container } = render(<SchemaForm schema={schema} value={value}
      serverError={serverError([{ pointer: "/main", code: bad, message: bad }])} onChange={vi.fn()} />);
    expect(screen.getByRole("textbox", { name: visible })).toHaveProperty("value", visible);
    expect(screen.getByRole("radio", { name: visible })).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toBe(visible);
    expect(container.querySelector("pre")?.textContent).toBe(`{\n  "<script>": "${visible}"\n}`);
    expect(container.querySelector("svg, script, [onload]")).toBeNull();
    expect(container.innerHTML).not.toContain("\u0007");
    expect(container.innerHTML).not.toContain("\u202e");
    expect(screen.getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual(urls.slice(-2));
    expect(screen.getByRole("link", { name: "Справка (https://docs.example.test)" }).getAttribute("rel"))
      .toBe("noopener noreferrer");
  });

  it("preserves escaped characters when the surrounding string is edited", () => {
    const change = vi.fn();
    render(<Editable schema={{ ...text, ...ui("markdown") }} value={"a\u202eb"} onChange={change} />);
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "za\\u202eb" } });
    expect(change).toHaveBeenLastCalledWith("za\u202eb");
    fireEvent.change(input, { target: { value: "za\\u202eb!" } });
    expect(change).toHaveBeenLastCalledWith("za\u202eb!");
  });

  it.each(["textarea", "markdown", "code"])("keeps line breaks in the %s editor and escapes other controls", async (widget) => {
    const change = vi.fn();
    const original = "one\r\ntwo\r\u202e\u0007\u0085";
    render(<Editable schema={{ ...text, ...ui(widget) }} value={original} onChange={change} />);
    const input = screen.getByRole("textbox") as HTMLTextAreaElement;
    const initialDisplay = "one\ntwo\\u000d\\u202e\\u0007\\u0085";
    expect(input.value).toBe(initialDisplay);

    const user = userEvent.setup();
    await user.click(input);
    input.setSelectionRange(input.value.length, input.value.length);
    await user.keyboard("{Enter}");
    expect(input.value).toBe(initialDisplay + "\n");
    await user.paste("three\r\nfour\nfive\u2066");
    expect(input.value).toBe(initialDisplay + "\nthree\nfour\nfive\\u2066");
    expect(change).toHaveBeenLastCalledWith("one\ntwo\r\u202e\u0007\u0085\nthree\nfour\nfive\u2066");
  });

  it("redacts sensitive values inside unsupported and recursive schema fragments", () => {
    const schema = {
      type: "object",
      properties: {
        secret: { ...text, "x-skm": { sensitivity: "secret" } },
        again: { $ref: "#" },
        unsupported: { type: "object", patternProperties: { ".*": { $ref: "urn:skm:config:secret-ref:v1" } } },
      },
    };
    const { container } = render(<SchemaForm schema={schema}
      value={{ again: { secret: "plain-nested" }, unsupported: { key: "plain-map" } }} />);
    const output = container.textContent ?? "";
    expect(output).toContain("$ref");
    expect(output).toContain("patternProperties");
    expect(output).toContain("•••");
    expect(output).not.toMatch(/plain-nested|plain-map/u);
  });

  it("redacts secrets reached through dependentSchemas and masks unknown subtrees", () => {
    const schema = {
      ...object({ trigger: text, public: text, indirect: { $ref: "#/dependentSchemas/trigger/$defs/alias" } }),
      $defs: { hidden: text },
      dependentSchemas: {
        trigger: {
          $id: "urn:example:dependency",
          $defs: { alias: { $ref: "#/$defs/hidden" }, hidden: { ...text, "x-skm": { sensitivity: "secret" } } },
          properties: {
            settings: { ...object({ token: { $ref: "#/$defs/hidden" }, name: text }), allOf: [{}] },
            opaque: { $ref: "urn:example:missing" },
          },
        },
      },
    };
    const value = {
      trigger: "enabled", public: "visible", settings: { token: "dependency-plaintext", name: "known", other: "unknown-plaintext" },
      indirect: "indirect-plaintext", opaque: "unresolved-plaintext",
    };
    const { container } = render(<SchemaForm schema={schema} value={value} />);
    expect(container.querySelector("pre")?.textContent).toBe(JSON.stringify({
      trigger: "enabled", public: "visible", settings: { token: "•••", name: "known", other: "•••" },
      indirect: "•••", opaque: "•••",
    }, null, 2));
  });

  it("uses a redacted read-only widget for unsupported secret schemas, including resolved refs", () => {
    const secretRef = "urn:skm:config:secret-ref:v1";
    const secret = { sensitivity: "secret" };
    const target = "urn:example:unsupported-secret";
    const schema = object({
      conditional: { ...text, "x-skm": secret, if: {}, then: {}, else: {} },
      patterned: { $ref: secretRef, patternProperties: { ".*": text } },
      resolved: { $ref: target, "x-skm": secret },
    });
    const registry = { [target]: { ...text, allOf: [text], not: { const: "example" } } };
    const value = { conditional: "conditional-plaintext", patterned: "patterned-plaintext", resolved: "resolved-plaintext" };
    const { container } = render(<SchemaForm schema={schema} registry={registry} value={value} onChange={vi.fn()} />);
    expect(container.querySelector("input")).toBeNull();
    expect([...container.querySelectorAll("pre")].map((preview) => preview.textContent)).toEqual(['"•••"', '"•••"', '"•••"']);
    expect(screen.getByText(/if, then, else/u)).toBeTruthy();
    expect(screen.getByText(/patternProperties/u)).toBeTruthy();
    expect(screen.getByText(/allOf, not/u)).toBeTruthy();
  });
});

function load(path: string, directory = "src/skm/schemas"): unknown {
  const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
  return JSON.parse(readFileSync(resolve(root, directory, `${path}.v1.json`), "utf8"));
}

function golden(props: SchemaFormProps): string {
  const dom = document.createElement("template");
  dom.innerHTML = renderToStaticMarkup(<SchemaForm {...props} onChange={() => {}} />);
  return dom.innerHTML.split(/(?<=>)(?=<)/u).join("\n") + "\n";
}

describe("golden HTML", () => {
  it("renders the supported widget profile with layout, advisory and server validation", async () => {
    const schema = {
      title: "Profile",
      ...object({
        name: { ...text, minLength: 4, ...ui("text", { group: "Text", order: 2, title: "Name", help_url: "https://docs.example.org/" }) },
        path: { ...text, ...ui("path", { group: "Text", order: 1 }) },
        textarea: { ...text, ...ui("textarea", { group: "Text", order: 3 }) },
        markdown: { ...text, ...ui("markdown", { group: "Text", order: 4 }) },
        code: { ...text, ...ui("code", { group: "Text", order: 5 }) },
        number: { type: "number" },
        slider: { type: "integer", minimum: 1, maximum: 4, ...ui("slider") },
        check: { type: "boolean" },
        toggle: { type: "boolean", ...ui("toggle") },
        switch: { type: "boolean", ...ui("switch") },
        radio: { enum: ["a", "b"] },
        const: { const: "v1" },
        select: { enum: ["one", "two"], ...ui("select") },
        list: { type: "array", items: { type: "integer" } },
        cards: { type: "array", items: object({ value: text }) },
        tags: { type: "array", items: text, ...ui("tags") },
        table: { type: "array", items: object({ value: text }), ...ui("table") },
        group: { ...object({ extra: text }), ...ui("collapsed", { advanced: true }) },
        map: { type: "object", additionalProperties: text, propertyNames: { pattern: "^p" }, ...ui("map") },
        variant: variantSchema,
        secret: { $ref: "urn:skm:config:secret-ref:v1" },
        json: { ...object({ key: text }), ...ui("json") },
      }, ["name"]),
    };
    const value = {
      name: "A", path: "~/file", textarea: "one\ntwo", markdown: "**strong**", code: "<script>", number: 7.5, slider: 3,
      check: false, toggle: true, switch: false, radio: "a", const: "v1", select: "two", list: [1], cards: [{ value: "c" }],
      tags: ["tag"], table: [{ value: "table row" }], group: { extra: "advanced" }, map: { "a/b~": "entry" },
      variant: { kind: "manual", shared: "shared", reason: "test" }, secret: "should-not-appear", json: { key: "one\u202etwo" },
    };
    await expect(golden({ schema, value, serverError: serverError([
      { pointer: "/map/a~1b~0", message: "Исправьте запись" },
      { pointer: "/variant/reason", message: "Укажите причину" },
    ]) })).toMatchFileSnapshot("./__golden__/profile.html");
  });

  it("renders a real planning review branch via a pointer URN", async () => {
    const urn = "urn:skm:planning:specification:v1";
    const schema = { $ref: `${urn}#/$defs/review` };
    await expect(golden({ schema, registry: { [urn]: load("planning/specification") },
      value: { mode: "self", reason: "Review rationale" } })).toMatchFileSnapshot("./__golden__/planning-review.html");
  });

  it("renders bounded recursive schema fixtures and unsupported keywords", async () => {
    const registry = Object.fromEntries(["tree", "node-a", "node-b", "defs"].map((name) => [
      `urn:skm:shop:${name}:v1`, load(name, "tests/fixtures/schemas/valid/shop"),
    ]));
    const schema = object({
      tree: { $ref: "urn:skm:shop:tree:v1" },
      pair: { $ref: "urn:skm:shop:node-a:v1" },
      sku: { $ref: "urn:skm:shop:defs:v1#/$defs/sku" },
      fallback: { properties: { unsafe: text }, if: {}, then: {}, else: {}, allOf: [], not: {}, patternProperties: {}, anyOf: [] },
      untagged: { oneOf: [text] },
      null: { type: "null" },
      unresolved: { $ref: "urn:unknown" },
    });
    await expect(golden({ schema, registry, value: {
      tree: { name: "parent", children: [{ name: "child", children: [] }] },
      pair: { kind: "a", next: { kind: "b", next: { kind: "a" } } }, sku: "ABC-1234",
      fallback: { unsafe: "<img>\u2066" }, untagged: "text", null: null, unresolved: [1],
    } })).toMatchFileSnapshot("./__golden__/fallback.html");
  });
});
