import { ArrowUpRight } from "lucide-react";
import { copy, examples, type Locale } from "@/lib/i18n";
export function ExampleChips({
  locale,
  onSelect,
}: {
  locale: Locale;
  onSelect: (question: string) => void;
}) {
  return (
    <section className="examples">
      <div className="section-label">
        <span>{copy[locale].examples}</span>
        <span>01 — 06</span>
      </div>
      <div className="example-grid">
        {examples.map((question, index) => (
          <button
            type="button"
            className="example"
            key={question}
            onClick={() => onSelect(question)}
          >
            <span className="example-index">0{index + 1}</span>
            <span>{question}</span>
            <ArrowUpRight size={16} aria-hidden="true" />
          </button>
        ))}
      </div>
    </section>
  );
}
