"use client";
import { useEffect, useState } from "react";
import { copy, examples, type Locale } from "@/lib/i18n";

const SHOWN = 6;

// One random pick per language per page load. Cached at module level so a remount (the welcome decor
// leaves and returns when the keyboard opens and closes) renders the same chips synchronously:
// a view transition snapshots that first render, and an empty one made the layout jump afterwards.
const picks = new Map<Locale, string[]>();

function pick(locale: Locale): string[] {
  const pool = [...examples[locale]];
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  return pool.slice(0, SHOWN);
}

export function ExampleChips({
  locale,
  onSelect,
}: {
  locale: Locale;
  onSelect: (question: string) => void;
}) {
  // The very first (server-rendered) pass stays empty: a random pick there would break hydration.
  const [picked, setPicked] = useState<string[]>(() => picks.get(locale) ?? []);
  useEffect(() => {
    let chosen = picks.get(locale);
    if (!chosen) {
      chosen = pick(locale);
      picks.set(locale, chosen);
    }
    setPicked(chosen);
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
