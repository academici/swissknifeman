import { Menu as BaseMenu } from "@base-ui/react/menu";
import { escapeText } from "../../lib/safeText";

interface MenuItem {
  id: string;
  label: string;
  disabled?: boolean;
  onSelect(): void;
}

export function Menu({ label, items }: { label: string; items: readonly MenuItem[] }) {
  const name = escapeText(label);
  return (
    <BaseMenu.Root>
      <BaseMenu.Trigger>{name}</BaseMenu.Trigger>
      <BaseMenu.Portal>
        <BaseMenu.Positioner className="overlay-positioner" sideOffset={4} align="start">
          <BaseMenu.Popup className="menu-popup" aria-label={name}>
            {items.map((item) => (
              <BaseMenu.Item
                key={item.id}
                className="menu-item"
                render={<button type="button" />}
                nativeButton
                disabled={item.disabled}
                onClick={item.onSelect}
              >
                {escapeText(item.label)}
              </BaseMenu.Item>
            ))}
          </BaseMenu.Popup>
        </BaseMenu.Positioner>
      </BaseMenu.Portal>
    </BaseMenu.Root>
  );
}
