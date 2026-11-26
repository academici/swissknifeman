/** Choices of the enum fields of a plan item. The host does not load the JSON Schema of the planner (D20): this table
 * is checked against the schema export of the planner bridge by `SchemaFormView.test.tsx`, and the planner still
 * refuses a value it does not accept (SCHEMA_INVALID). */
export const PLAN_ENUMS: Record<string, string[]> = {
  "/route/class": ["economy", "implementation", "frontier"],
  "/route/effort": ["low", "medium", "high", "xhigh", "max", "ultra"],
  "/review/mode": ["none", "self", "requested"],
  "/review/reviewer/class": ["economy", "implementation", "frontier"],
  "/review/reviewer/effort": ["low", "medium", "high", "xhigh", "max", "ultra"],
  "/authority/kind": ["routine", "owner_gate", "external_gate"],
  "/rag/need": ["none", "optional", "required"],
  "/rag/status": ["not_needed", "pending", "complete", "failed"],
};
