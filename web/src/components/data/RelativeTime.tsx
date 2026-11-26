const formatter = new Intl.RelativeTimeFormat("ru", { numeric: "auto" });
const units = [["day", 86_400], ["hour", 3_600], ["minute", 60], ["second", 1]] as const;

export function RelativeTime({ value, now = Date.now() }: { value: string; now?: number }) {
  const parsed = new Date(value);
  const seconds = (parsed.getTime() - now) / 1_000;
  if (!Number.isFinite(seconds)) return <span>Время неизвестно</span>;
  for (const [unit, size] of units) {
    if (unit === "second" || Math.abs(seconds) >= size) {
      return <time dateTime={parsed.toISOString()} title={parsed.toLocaleString("ru")}>{formatter.format(Math.round(seconds / size), unit)}</time>;
    }
  }
}
