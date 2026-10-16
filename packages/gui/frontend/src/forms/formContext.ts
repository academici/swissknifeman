import type { Draft } from "./draft";
import type { ConfigView, LayerName } from "./types";

/** What every field of a form needs: the loaded view, the layer being edited and the draft with its setter. */
export interface FormContext {
  view: ConfigView;
  layer: LayerName;
  draft: Draft | null;
  onDraft: (draft: Draft) => void;
}
