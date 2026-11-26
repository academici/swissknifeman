import { lazy, Suspense } from "react";
import { Spinner } from "../primitives/Spinner";

const MarkdownContent = lazy(() => import("./MarkdownContent"));

export function Markdown({ text }: { text: string }) {
  return (
    <Suspense fallback={<Spinner />}>
      <MarkdownContent text={text} />
    </Suspense>
  );
}
