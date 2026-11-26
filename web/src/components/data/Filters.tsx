import type { PropsWithChildren } from "react";

export function Filters({ children, onReset }: PropsWithChildren<{ onReset(): void }>) {
  return (
    <fieldset className="filters">
      <legend>Фильтры</legend>
      {children}
      <button type="button" onClick={onReset}>Сбросить фильтры</button>
    </fieldset>
  );
}
