import { Tabs as BaseTabs } from "@base-ui/react/tabs";
import type { ReactNode } from "react";
import { escapeText } from "../../lib/safeText";

interface Tab {
  id: string;
  label: string;
  content: ReactNode;
}

export function Tabs({ label, tabs, active, onSelect }: {
  label: string;
  tabs: readonly Tab[];
  active: string;
  onSelect(id: string): void;
}) {
  return (
    <BaseTabs.Root value={active} onValueChange={(value) => {
      if (typeof value === "string") onSelect(value);
    }}>
      <BaseTabs.List className="tabs" aria-label={escapeText(label)} activateOnFocus loopFocus>
        {tabs.map((tab) => (
          <BaseTabs.Tab key={tab.id} value={tab.id}>{escapeText(tab.label)}</BaseTabs.Tab>
        ))}
      </BaseTabs.List>
      {tabs.map((tab) => (
        <BaseTabs.Panel key={tab.id} value={tab.id}>{tab.content}</BaseTabs.Panel>
      ))}
    </BaseTabs.Root>
  );
}
