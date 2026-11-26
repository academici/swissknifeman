import { escapeText } from "../../lib/safeText";
import { RelativeTime } from "./RelativeTime";

export function Timeline({ events, type }: {
  events: readonly { id: string; time: string; type: string; detail: string; task?: string }[];
  type?: string;
}) {
  return (
    <ol className="timeline">
      {events.filter((event) => type === undefined || event.type === type).map((event) => (
        <li key={event.id}>
          <RelativeTime value={event.time} /> · {escapeText(event.type)}
          {event.task && <> · {escapeText(event.task)}</>}
          <p>{escapeText(event.detail)}</p>
        </li>
      ))}
    </ol>
  );
}
