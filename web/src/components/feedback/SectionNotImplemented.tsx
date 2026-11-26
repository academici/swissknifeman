export function SectionNotImplemented({ title }: { title: string }) {
  return (
    <section className="section">
      <h1>{title}</h1>
      <p>Раздел ещё не реализован.</p>
    </section>
  );
}
