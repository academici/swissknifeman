// Inert declarative workflow specification (data asset; never auto-executed by SKM).
export const workflow = {
  id: "dev-loop",
  version: "1.0.0",
  stages: ["plan", "implement", "verify", "review"],
  requireCleanVerification: true,
};
