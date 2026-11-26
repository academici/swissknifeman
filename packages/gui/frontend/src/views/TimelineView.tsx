import type { Timeline } from "../contracts";
import { ViewLinkTo } from "./common";

export function TimelineView({ data, projectId }: { data: Timeline; projectId?: string }) {
  return (
    <ol className="timeline">
      {data.entries.map((entry, index) => (
        <li key={`${entry.at}-${index}`}>
          <time dateTime={entry.at}>{entry.at.replace("T", " ").replace(/\.\d+Z$|Z$/, " UTC")}</time>{" "}
          <span className="kind">{entry.kind}</span>{" "}
          <ViewLinkTo link={entry.link} projectId={projectId}>
            {entry.title}
          </ViewLinkTo>
          {entry.detail ? <div className="detail">{entry.detail}</div> : null}
        </li>
      ))}
      {data.entries.length === 0 && <li className="muted">Nothing yet.</li>}
    </ol>
  );
}
