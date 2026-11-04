"use client";
import { useEffect, useState } from "react";
import { copy, examples, type Locale } from "@/lib/i18n";

const SHOWN = 6;

export function ExampleChips({
  locale,
  onSelect,
}: {
  locale: Locale;
  onSelect: (question: string) => void;
}) {
  // Shuffle after mount: a server-rendered random pick would not match the client and break hydration.
  const [picked, setPicked] = useState<string[]>([]);
  useEffect(() => {
    const pool = [...examples[locale]];
    for (let i = pool.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [pool[i], pool[j]] = [pool[j], pool[i]];
    }
    setPicked(pool.slice(0, SHOWN));
  }, [locale]);
  return (
    <section className="examples" aria-label={copy[locale].examples}>
      {picked.map((question) => (
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
