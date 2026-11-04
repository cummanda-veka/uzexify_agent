import { ThoughtLine } from "@/components/bits";
import type { Step } from "@/lib/api";
import { copy, type Locale } from "@/lib/i18n";

/** Live (working) or settled trace of agent tool steps. */
export function StepList({
  steps,
  locale,
  working,
  elapsed,
}: {
  steps: Step[];
  locale: Locale;
  working: boolean;
  elapsed?: number;
}) {
  const t = copy[locale];
  return (
    <ThoughtLine
      className="steps"
      working={working}
      elapsed={working ? undefined : elapsed}
      label={t.working}
      doneLabel={t.done}
      steps={steps.map((s) => (locale === "ru" ? s.label_ru : s.label_uz))}
      glyph="sparkle"
      color="#b9c0d0"
      glyphColor="#7fb2ff"
      fontSize={14}
      collapseOnSettle
    />
  );
}
