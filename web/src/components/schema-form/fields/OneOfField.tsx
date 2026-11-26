import { escapeText } from "../../../lib/safeText";
import type { OneOfNode, SchemaNode } from "../profile";
import { appendPointer, initialValue, isRecord, jsonEqual, own, selectedVariant, setAtPointer } from "../values";
import { FieldFrame, type FieldProps } from "./FieldFrame";
import { ObjectContents } from "./ObjectField";
import { ReadOnlyField } from "./ReadOnlyField";

export function OneOfField(field: FieldProps<OneOfNode>) {
  const { node, value, pointer, readOnly } = field;
  const selected = selectedVariant(node, value);
  const branch = node.variants[selected]?.node;
  const tagPointer = appendPointer(pointer, node.discriminator);
  const tag = own(value, node.discriminator);
  const options = node.variants.flatMap(({ tags, node: branch }, variantIndex) => tags.map((tag) => {
    const tagLabel = typeof tag === "string" ? tag : JSON.stringify(tag) ?? "";
    const label = branch.title ? (tags.length === 1 ? branch.title : `${branch.title} (${tagLabel})`) : tagLabel;
    return { tag, label, branch, variantIndex };
  }));
  const selectedOption = options.findIndex((option) => jsonEqual(option.tag, tag));
  const selector: FieldProps = {
    ...field,
    node: { ...node, kind: "leaf/enum", widget: "select", options: options.map((option) => option.tag),
      title: undefined, description: undefined, ui: { ...node.ui, helpUrl: undefined } },
    value: tag, pointer: tagPointer, label: node.discriminator, required: true, issues: field.issuesFor(tagPointer),
  };

  return (
    <FieldFrame field={field} group>
      {() => (
        <>
          <FieldFrame field={selector}>
            {(control) => (
              <select {...control} value={selectedOption < 0 ? "" : selectedOption} disabled={readOnly}
                onChange={(event) => {
                  const option = options[Number(event.currentTarget.value)];
                  if (!option) return;
                  field.change(option.variantIndex === selected
                    ? setAtPointer(value, appendPointer("", node.discriminator), option.tag)
                    : switchVariant(value, node.discriminator, option.branch, option.tag));
                }}>
                {selectedOption < 0 && <option value="" disabled>Выберите вариант</option>}
                {options.map(({ label }, index) => (
                  <option key={index} value={index}>{escapeText(label)}</option>
                ))}
              </select>
            )}
          </FieldFrame>
          {branch?.kind === "object" && (
            <ObjectContents key={selected} {...field} node={branch} omit={node.discriminator} />
          )}
          {branch?.kind === "unsupported" && (
            <ReadOnlyField {...field} node={branch} issues={[]} required={false} />
          )}
        </>
      )}
    </FieldFrame>
  );
}

function switchVariant(value: unknown, discriminator: string, node: SchemaNode, tag: unknown): unknown {
  const defaults = initialValue(node);
  const properties = node.schema.properties;
  const common = isRecord(properties) && isRecord(value) ? Object.fromEntries(
    Object.entries(value).filter(([key]) => key !== discriminator && Object.hasOwn(properties, key)),
  ) : {};
  return { ...(isRecord(defaults) ? defaults : {}), ...common, [discriminator]: tag };
}
