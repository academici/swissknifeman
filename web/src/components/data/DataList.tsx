import type { PropsWithChildren } from "react";

export function DataList({ children }: PropsWithChildren) {
  return <dl className="data-list">{children}</dl>;
}
