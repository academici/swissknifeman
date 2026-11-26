// Fixtures of the form tests: the valid examples of config-view/v1 with a module schema that covers every field type.
import machineExample from "../../../schemas/config-view/v1/examples/valid/view-machine.json";
import projectExample from "../../../schemas/config-view/v1/examples/valid/view-project.json";
import type { ConfigView } from "./types";

export const SCHEMA = {
  $schema: "https://json-schema.org/draft/2020-12/schema",
  $id: "urn:swissknifeman:config-demo:config:v1",
  type: "object",
  additionalProperties: false,
  properties: {
    title: { type: "string", default: "demo", description: "Free text." },
    verbose: { type: "boolean", default: false, description: "Print details." },
    mode: { type: "string", enum: ["fast", "safe"], default: "safe", description: "Run mode." },
    limits: {
      type: "object",
      additionalProperties: false,
      properties: {
        max: { type: "integer", minimum: 1, maximum: 100, default: 4, description: "Largest count." },
        ratio: { type: "number", minimum: 0, maximum: 1, default: 0.5 },
      },
    },
    sources: { type: "array", items: { type: "string", minLength: 1 }, default: ["local"] },
    profiles: {
      type: "object",
      description: "Profiles by name.",
      additionalProperties: false,
      patternProperties: {
        "^[a-z][a-z0-9-]*$": {
          type: "object",
          additionalProperties: false,
          properties: {
            level: { type: "integer", minimum: 0, maximum: 9, default: 1 },
            label: { type: "string" },
          },
        },
      },
    },
    token: { type: "string", "x-skm-secret": true, description: "Reference to the API token." },
    cache_dir: { type: "string", default: "", "x-skm-layers": ["defaults", "machine"], description: "Machine-local cache directory." },
  },
};

export const machineView = { ...machineExample, schema: SCHEMA } as unknown as ConfigView;
export const projectView = { ...projectExample, schema: SCHEMA } as unknown as ConfigView;

export const PROJECT_ID = "proj-1a2b3c4d";
export const PROJECTS = {
  $schema: "urn:swissknifeman:gui:project:v1",
  kind: "project_list",
  projects: [{ id: PROJECT_ID, name: "proj", root: "/home/user/proj", source: "open", trusted: true, added_at: "2026-10-16T10:00:00Z" }],
};

/** A copy of `view` with the changes applied (a deep copy). */
export function changed(view: ConfigView, change: (copy: ConfigView) => void): ConfigView {
  const copy = JSON.parse(JSON.stringify(view)) as ConfigView;
  change(copy);
  return copy;
}
