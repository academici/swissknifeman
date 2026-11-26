import { Popover as BasePopover } from "@base-ui/react/popover";
import type { PropsWithChildren } from "react";
import { escapeText } from "../../lib/safeText";

export function Popover({ label, children }: PropsWithChildren<{ label: string }>) {
  const name = escapeText(label);
  return (
    <BasePopover.Root>
      <BasePopover.Trigger>{name}</BasePopover.Trigger>
      <BasePopover.Portal>
        <BasePopover.Positioner className="overlay-positioner" sideOffset={4} align="start">
          <BasePopover.Popup className="popover-popup" aria-label={name}>
            {children}
          </BasePopover.Popup>
        </BasePopover.Positioner>
      </BasePopover.Portal>
    </BasePopover.Root>
  );
}
