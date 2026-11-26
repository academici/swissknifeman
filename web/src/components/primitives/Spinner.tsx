export function Spinner({ label = "Загрузка…" }: { label?: string }) {
  return <p role="status" className="spinner"><span aria-hidden="true" />{label}</p>;
}
