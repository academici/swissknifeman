import { useState } from "react";
import type { DesignPlan } from "../../api/generated/planning";
import { isUuid, useDesignResearchResult, usePlanResearchProfile } from "../../api/hooks/planning";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { isRecord } from "../../components/schema-form/values";
import { escapeText } from "../../lib/safeText";

type Reference = NonNullable<DesignPlan["research_references"]>[number];
const digest = /^sha256:[0-9a-f]{64}$/;
const quote = (value: string) => "'" + value.replaceAll("'", "'\"'\"'") + "'";

export function DesignResearch({ projectId, planId, references, onChange }: {
  projectId: string; planId: string; references: readonly Reference[]; onChange(refs: Reference[]): void;
}) {
  const [question, setQuestion] = useState("");
  const [deep, setDeep] = useState(false);
  const [command, setCommand] = useState("");
  const [query, setQuery] = useState("");
  const [lookup, setLookup] = useState("");
  const profile = usePlanResearchProfile(projectId);
  const result = useDesignResearchResult(projectId, lookup);
  const config = new Map(profile.data?.keys.map(entry => [entry.key, entry.value]));
  const sources = config.get("context.research.profile.sources");
  const allowDeep = config.get("context.research.allow_deep") === true &&
    config.get("context.research.profile.allow_deep") !== false;
  const limit = (field: string) => config.get(`context.research.profile.${field}`) ?? config.get(`context.research.${field}`);
  const queryLimit = limit("query_max_chars");
  const excerptLimit = limit("excerpt_max_chars");
  const documents = limit("max_documents");
  const disabled = Array.isArray(sources) && sources.length === 0;
  const raw = result.data?.result;
  const evidence = raw?.status === "ok" && raw.query_id === lookup && Array.isArray(raw.documents)
    ? raw.documents.filter(isRecord).flatMap(doc => {
      if (typeof doc.document_id !== "string" || !isUuid(doc.document_id) ||
          typeof doc.content_digest !== "string" || !digest.test(doc.content_digest) ||
          typeof doc.origin !== "string" || doc.origin.startsWith("answer:") || !doc.excerpt) return [];
      return [{ reference: `research-query:${lookup}/${doc.document_id}`, content_digest: doc.content_digest }];
    })
    : [];
  const attached = new Set(references.map(entry => entry.reference));
  const additions = evidence.filter(entry => !attached.has(entry.reference));
  return <fieldset>
    <legend>Исследование RAG</legend>
    {profile.error && <ErrorPanel error={profile.error} onRetry={() => void profile.refetch()} />}
    {profile.data && <dl>
      <dt>Источники проекта</dt><dd>{disabled ? "Отключены" : Array.isArray(sources) ?
        sources.map(source => escapeText(String(source))).join(", ") : "По настройкам хоста"}</dd>
      {typeof documents === "number" && <><dt>Документов на источник</dt><dd>{documents}</dd></>}
      {typeof queryLimit === "number" && <><dt>Символов в запросе</dt><dd>{queryLimit}</dd></>}
      {typeof excerptLimit === "number" && <><dt>Символов в выдержке</dt><dd>{excerptLimit}</dd></>}
    </dl>}
    <label>Вопрос для исследования <input value={question} maxLength={typeof queryLimit === "number" ? queryLimit : 4000}
      onChange={event => { setQuestion(event.target.value); setCommand(""); }} /></label>
    {allowDeep && <label><input type="checkbox" checked={deep}
      onChange={event => { setDeep(event.target.checked); setCommand(""); }} />Углублённое исследование</label>}
    <Button disabled={disabled || !question.trim()} onClick={() => setCommand([
      "skm plan research --json --project", quote(projectId),
      ...(allowDeep && deep ? ["--deep"] : []), "--", quote(planId), quote(question.trim()),
    ].join(" "))}>Подготовить запуск RAG на хосте</Button>
    {command && <p>Выполните команду на зарегистрированном хосте. Используйте ID из <code>design_query_ids</code>.
      <br /><code>{escapeText(command)}</code></p>}
    <label>ID результата исследования <input value={query} onChange={event => {
      setQuery(event.target.value.trim().toLowerCase()); setLookup("");
    }} /></label>
    <Button disabled={!isUuid(query) || result.isFetching}
      onClick={() => { if (lookup === query) void result.refetch(); else setLookup(query); }}>Загрузить результат RAG</Button>
    {result.error && <ErrorPanel error={result.error} />}
    {result.data && <p role="status">Документов с подтверждённым содержимым: {evidence.length}</p>}
    {additions.length > 0 && <Button disabled={references.length + additions.length > 100}
      onClick={() => onChange([...references, ...additions])}>Прикрепить документы</Button>}
    {references.length > 0 && <p>{references.length} документов прикреплено
      {" "}<Button onClick={() => onChange([])}>Очистить ссылки на документы</Button></p>}
  </fieldset>;
}
