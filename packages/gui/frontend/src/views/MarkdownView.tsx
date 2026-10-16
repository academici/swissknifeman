import ReactMarkdown from "react-markdown";
import type { Markdown } from "../contracts";

/** Only relative links and http(s) URLs survive; everything else (javascript:, data:, file:) becomes empty. */
export function safeUrl(url: string): string {
  const value = url.trim();
  if (/^https?:\/\//i.test(value)) return value;
  if (/^[a-z][a-z0-9+.-]*:/i.test(value) || value.startsWith("//")) return "";
  return value;
}

/** Markdown from a contribution: raw HTML is skipped, never rendered (XSS). */
export function MarkdownView({ data }: { data: Pick<Markdown, "text"> }) {
  return (
    <div className="markdown">
      <ReactMarkdown skipHtml urlTransform={safeUrl}>
        {data.text}
      </ReactMarkdown>
    </div>
  );
}
