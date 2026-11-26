// @vitest-environment node
// Golden markup of the form for the valid examples of config-view/v1 (server render: the same components, no DOM).
// The files in __golden__ are in git; `npm run check` compares them and never rewrites them.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { emptyDraft, setValue, unsetValue } from "./draft";
import { ProvenanceBadge } from "./ProvenanceBadge";
import { SchemaForm } from "./SchemaForm";
import { changed, machineView, projectView, SCHEMA } from "./test-fixtures";
import type { ConfigView, LayerName } from "./types";

function html(view: ConfigView, layer: LayerName, edit?: (draft: NonNullable<ReturnType<typeof emptyDraft>>) => ReturnType<typeof emptyDraft>) {
  const start = emptyDraft(view, layer);
  const draft = start && edit ? edit(start) : null;
  return renderToStaticMarkup(<SchemaForm view={view} layer={layer} draft={draft} onDraft={() => undefined} />).replaceAll("><", ">\n<") + "\n";
}

describe("schema form (golden)", () => {
  it("machine view without a project: every field type, project layer not writable", async () => {
    await expect(html(machineView, "machine")).toMatchFileSnapshot("./__golden__/form-machine.html");
  });

  it("project view: map, secret reference, forbidden layer, overridden env value", async () => {
    await expect(html(projectView, "project")).toMatchFileSnapshot("./__golden__/form-project.html");
  });

  it("a draft: changed fields are marked, an unset key shows empty", async () => {
    const markup = html(projectView, "project", (draft) => unsetValue(setValue(draft, "limits.ratio", 0.25), "limits.max"));
    await expect(markup).toMatchFileSnapshot("./__golden__/form-draft.html");
    expect(markup).toContain("changed");
  });

  it("an unsupported keyword makes the field read-only and does not throw", async () => {
    const view = changed(projectView, (copy) => {
      (copy.schema as { properties: Record<string, Record<string, unknown>> }).properties["title"] = { type: "string", format: "uri" };
    });
    const markup = html(view, "project");
    await expect(markup).toMatchFileSnapshot("./__golden__/form-unsupported.html");
    expect(markup).toContain("unsupported: format");
  });

  it("a field is disabled when its key may not be set in the layer", () => {
    const project = html(projectView, "project");
    expect(project).toMatch(/<input id="field-cache_dir"[^>]*disabled=""/);
    expect(project).toContain("allowed: defaults, machine");
    expect(html(machineView, "machine")).not.toMatch(/<input id="field-cache_dir"[^>]*disabled=""/);
  });

  it("a secret field offers the schemes env and keyring only and shows the reference", () => {
    const markup = html(changed(projectView, (copy) => {
      copy.entries.find((entry) => entry.key === "token")!.layer_values.project = "keyring://demo/token";
    }), "project");
    expect(markup).toContain('<option value="env">env</option>');
    expect(markup).toContain('<option value="keyring" selected="">keyring</option>');
    expect(markup).not.toMatch(/<option value="(plain|vault|file)"/);
    expect(markup).toContain('value="demo/token"');
  });

  it("renders data as text, never as markup", () => {
    const markup = renderToStaticMarkup(<ProvenanceBadge entry={changed(projectView, (copy) => {
      copy.entries[0]!.effective.source = "<img src=x onerror=alert(1)>";
      copy.entries[0]!.effective.file = null;
    }).entries[0]!} />);
    expect(markup).not.toContain("<img");
    expect(markup).toContain("&lt;img");
  });

  it("the schema fixture covers a map, a table and a list", () => {
    expect(Object.keys(SCHEMA.properties)).toEqual(expect.arrayContaining(["limits", "profiles", "sources"]));
  });
});
