import type { Element, Root } from "hast";
import ReactMarkdown, { type Components } from "react-markdown";
import { sanitizeLink } from "../../lib/safeLink";
import { escapeText } from "../../lib/safeText";
import { CodeBlock } from "./CodeBlock";
import { SafeLink } from "./SafeLink";

function escapeMarkdownText() {
  function visit(parent: Root | Element) {
    for (const node of parent.children) {
      if (node.type === "text" && (node.position || node.value !== "\n")) {
        node.value = escapeText(node.value);
      }
      if (node.type === "element" && node.tagName !== "pre") {
        visit(node);
      }
    }
  }
  return visit;
}

const components: Components = {
  a: ({ href, title, children }) => <SafeLink href={href} title={title}>{children}</SafeLink>,
  pre: ({ node }) => {
    const code = node?.children.find((child) => child.type === "element" && child.tagName === "code");
    if (code?.type !== "element") return null;
    const text = code.children.map((child) => child.type === "text" ? child.value : "").join("");
    return <CodeBlock text={text.replace(/\n$/u, "")} />;
  },
};

export default function MarkdownContent({ text }: { text: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        skipHtml
        disallowedElements={["img"]}
        components={components}
        rehypePlugins={[escapeMarkdownText]}
        urlTransform={(value) => sanitizeLink(value)?.href}
      >
        {text.replaceAll("\u0000", "\\u0000")}
      </ReactMarkdown>
    </div>
  );
}
