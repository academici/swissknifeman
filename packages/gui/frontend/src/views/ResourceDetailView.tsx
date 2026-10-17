import type { ViewAction, ViewData } from "../contracts";
import { MarkdownView } from "./MarkdownView";
import { StatusBadge, formatScalar } from "./common";

type ResourceDetail = Extract<ViewData, { view: "resource-detail" }>;
type Field = ResourceDetail["fields"][number];

function Value({ field }: { field: Field }) {
  const { type, value } = field;
  if (type === "status" && typeof value === "string") return <StatusBadge status={value} />;
  if (type === "progress" && typeof value === "number") {
    const percent = Math.round(Math.max(0, Math.min(100, value)));
    return (
      <span className="progress">
        <progress max={100} value={percent} aria-label={`${field.label}: ${percent}%`} /> {percent}%
      </span>
    );
  }
  if (type === "date" && typeof value === "string") return <time dateTime={value}>{value.replace("T", " ").replace("Z", " UTC")}</time>;
  return <>{formatScalar(value)}</>;
}

/** One resource: labelled fields by type, markdown sections (sanitized), and the commands offered for it. */
export function ResourceDetailView({ data, onAction }: { data: ResourceDetail; onAction?: (action: ViewAction) => void }) {
  return (
    <article className="resource-detail">
      <h2>{data.title}</h2>
      <dl>
        {data.fields.map((field, index) => (
          <div key={`${field.label}-${index}`} className="field">
            <dt>{field.label}</dt>
            <dd>
              <Value field={field} />
            </dd>
          </div>
        ))}
      </dl>
      {(data.sections ?? []).map((section, index) => (
        <section key={`${section.title}-${index}`}>
          <h3>{section.title}</h3>
          <MarkdownView data={{ text: section.markdown }} />
        </section>
      ))}
      {onAction && data.actions && data.actions.length > 0 && (
        <div className="actions">
          {data.actions.map((action, index) => (
            <button key={`${action.command}-${index}`} type="button" onClick={() => onAction(action)}>
              {action.command}
            </button>
          ))}
        </div>
      )}
    </article>
  );
}
