// Types of the configuration editor: the documents of config-view/v1 and config-mutation/v1.
export type { ConfigModules, ConfigView1 as ConfigView, Entry, Layer } from "../contracts/generated/config-view";
export type { Preview, PreviewRequest, CommitRequest, CommitResult } from "../contracts/generated/config-mutation";

export type Scalar = string | number | boolean;
export type Value = Scalar | Scalar[];
export type LayerName = "machine" | "project";
export const WRITABLE_LAYERS: readonly LayerName[] = ["machine", "project"];
export const VIEW_CONTRACT = "urn:swissknifeman:gui:config-view:v1";
export const MUTATION_CONTRACT = "urn:swissknifeman:gui:config-mutation:v1";
