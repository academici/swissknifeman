import { useState } from "react";
import type { SettingsLevel, SettingsScope } from "../../api/hooks/settings";
import { SafeLink } from "../../components/content/SafeLink";
import { Badge } from "../../components/primitives/Badge";
import { Button } from "../../components/primitives/Button";
import {
  fartherLock, fieldSchema, safeSettingValue, scopeHref,
  type BaseRow, type DraftOp, type KeyReport, type KeySpec,
} from "../../components/schema-form/draft";
import { HistoryDrawer } from "../../components/schema-form/HistoryDrawer";
import type { SchemaRegistry } from "../../components/schema-form/profile";
import { layerLabel, ProvenanceBadge, SettingValue } from "../../components/schema-form/ProvenanceBadge";
import { SchemaForm } from "../../components/schema-form/SchemaForm";
import { escapeText } from "../../lib/safeText";

export function KeyRow({ spec, target, known, base, operation, effective, targetReport, registry, writable, lockable,
  canSave, onEdit, onSave, onLock }: {
  spec: KeySpec;
  target: SettingsScope;
  known: ReadonlyMap<SettingsLevel, SettingsScope>;
  base: BaseRow | null;
  operation: DraftOp | undefined;
  effective: KeyReport | undefined;
  targetReport: KeyReport | undefined;
  registry: SchemaRegistry;
  writable: boolean;
  lockable: boolean;
  canSave: boolean;
  onEdit(operation?: DraftOp): void;
  onSave(): void;
  onLock(): void;
}) {
  const [history, setHistory] = useState(false);
  const title = spec.ui.title ?? spec.key;
  const lock = fartherLock(target, targetReport);
  const allowed = spec.levels.includes(target.level);
  const readOnly = !writable || base?.locked === true;
  const fallback = targetReport?.present ? targetReport.value : spec.default;
  const value = operation && "value" in operation ? operation.value :
    !operation && base && base.op !== "unset" ? base.value : fallback;
  const append = spec.merge === "replace" && spec.value_schema.type === "array" && spec.sensitivity !== "secret";
  const activeOp = operation?.op ?? base?.op;
  const nextDestinations = spec.levels.map((level) => known.get(level)).filter((dest) => dest !== undefined);
  const hasUnknownLevel = spec.levels.some((level) => !known.has(level));

  return (
    <article aria-label={escapeText(title)}>
      <h4>{escapeText(title)} {spec.chain === "host" && <Badge>(H)</Badge>}</h4>
      {title !== spec.key && <code>{escapeText(spec.key)}</code>}
      {!allowed && <p>Допустимые уровни {spec.levels.join(", ")}.{" "}
        {nextDestinations.map((dest) => <span key={dest.level}>
          <SafeLink href={scopeHref(dest)}>Перейти на {dest.level}</SafeLink>{" "}
        </span>)}
        {hasUnknownLevel && <SafeLink href={`${scopeHref(target)}#settings-level`}>Выбрать область</SafeLink>}
      </p>}
      {lock && <p>🔒 Заблокировано на {escapeText(layerLabel(lock))}</p>}
      {base?.locked && <p>🔒 Заблокировано на этом уровне</p>}
      <p>На уровне {operation
        ? <Badge>{operation.op === "remove" ? "Будет наследоваться" : `Черновик · ${operation.op}`}</Badge>
        : <Badge>{base?.op ?? "Наследуется"}</Badge>}
      </p>
      <SchemaForm schema={fieldSchema(spec)} registry={registry} value={value} label={title} readOnly={readOnly}
        onChange={(next) => onEdit({ op: activeOp === "append" ? "append" : "set", value: next })} />
      <p>Эффективное значение{" "}
        <SettingValue value={safeSettingValue(spec, registry, effective?.present ? effective.value :
          effective ? undefined : spec.default)} />
      </p>
      {spec.narrow?.unlimited !== undefined && <p>
        Без ограничения <SettingValue value={spec.narrow.unlimited} />
      </p>}
      {effective && <ProvenanceBadge report={effective} spec={spec} registry={registry} />}
      <div>
        <Button aria-label={escapeText(`История · ${title}`)} onClick={() => setHistory(true)}>История</Button>{" "}
        {!readOnly && spec.merge !== "narrow" && spec.merge !== "union" && <Button
          disabled={activeOp === "unset"} onClick={() => onEdit({ op: "unset" })}>Сбросить к умолчанию</Button>}{" "}
        {!readOnly && base && <Button disabled={operation?.op === "remove"}
          onClick={() => onEdit({ op: "remove" })}>Убрать запись</Button>}{" "}
        {!readOnly && append && activeOp !== "append" && <Button onClick={() => onEdit({ op: "append", value: [] })}>
          Добавить к наследуемому списку
        </Button>}{" "}
        {!readOnly && append && activeOp === "append" && <Button onClick={() => onEdit({ op: "set", value })}>
          Задать список целиком
        </Button>}{" "}
        {lockable && base && !operation && <Button onClick={onLock}>{base.locked ? "Разблокировать" : "Заблокировать"}</Button>}{" "}
        {operation && <Button onClick={() => onEdit()}>Отменить правку</Button>}{" "}
        {canSave && !readOnly && <Button onClick={onSave}>Сохранить только этот ключ</Button>}
      </div>
      {history && <HistoryDrawer spec={spec} scope={target} registry={registry} onClose={() => setHistory(false)} />}
    </article>
  );
}
