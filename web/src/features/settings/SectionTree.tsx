import { Tree } from "../../components/viz/Tree";
import type { KeySpec } from "../../components/schema-form/draft";
import { escapeText } from "../../lib/safeText";

export interface SettingsSection {
  id: string;
  title: string;
  keys: readonly KeySpec[];
}

export function filterSections(sections: readonly SettingsSection[], search: string) {
  const term = search.trim().toLocaleLowerCase();
  return sections.map((section) => ({
    ...section,
    keys: section.keys.filter((spec) =>
      [section.title, spec.key, spec.ui.title ?? ""].some((text) => text.toLocaleLowerCase().includes(term))),
  })).filter((section) => section.keys.length > 0);
}

export function SectionTree({ sections, active, search, isLocked, onSearch, onSelect }: {
  sections: readonly SettingsSection[];
  active: string | undefined;
  search: string;
  isLocked(key: string): boolean;
  onSearch(search: string): void;
  onSelect(section: string): void;
}) {
  const nodes = sections.map((section) => ({
    id: section.id,
    label: `${section.title}${section.keys.some((spec) => spec.chain === "host") ? " (H)" : ""}` +
      (section.keys.some(({ key }) => isLocked(key)) ? " 🔒" : ""),
  }));
  const activeTitle = sections.find(({ id }) => id === active)?.title;
  return (
    <nav aria-label="Разделы настроек">
      <label>Поиск настроек <input type="search" value={search} onChange={(event) => onSearch(event.currentTarget.value)} /></label>
      <div aria-label={activeTitle ? escapeText(`Открыт раздел ${activeTitle}`) : undefined}>
        <Tree nodes={nodes} onSelect={(node) => onSelect(node.id)} />
      </div>
    </nav>
  );
}
