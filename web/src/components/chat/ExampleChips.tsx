import { copy, examples, type Locale } from "@/lib/i18n";
export function ExampleChips({
  locale,
  onSelect,
}: {
  locale: Locale;
  onSelect: (question: string) => void;
}) {
  return (
    <section className="examples" aria-label={copy[locale].examples}>
      {examples.map((question) => (
        <button
          type="button"
          className="example"
          key={question}
          onClick={() => onSelect(question)}
        >
          {question}
        </button>
      ))}
    </section>
  );
}
