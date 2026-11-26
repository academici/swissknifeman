import type { ComponentPropsWithoutRef } from "react";
import { Button } from "./Button";

export function IconButton({ label, children, ...props }: ComponentPropsWithoutRef<"button"> & { label: string }) {
  return <Button {...props} aria-label={label}><span aria-hidden="true">{children}</span></Button>;
}
