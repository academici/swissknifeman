import { CodeBlock } from "../content/CodeBlock";

export function JsonView({ value }: { value: unknown }) {
  return (
    <details>
      <summary>Подробности</summary>
      <CodeBlock text={JSON.stringify(value, null, 2) ?? ""} />
    </details>
  );
}
