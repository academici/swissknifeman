import { Tooltip as BaseTooltip } from "@base-ui/react/tooltip";
import type { ReactElement } from "react";
import { escapeText } from "../../lib/safeText";

export function Tooltip({ label, children }: { label: string; children: ReactElement }) {
  const name = escapeText(label);
  return (
    <BaseTooltip.Root>
      <BaseTooltip.Trigger render={children} aria-label={name} />
      <BaseTooltip.Portal>
        <BaseTooltip.Positioner className="overlay-positioner" sideOffset={4}>
          <BaseTooltip.Popup className="tooltip-popup" aria-hidden="true">{name}</BaseTooltip.Popup>
        </BaseTooltip.Positioner>
      </BaseTooltip.Portal>
    </BaseTooltip.Root>
  );
}
