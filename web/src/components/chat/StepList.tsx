import type { Step } from "@/lib/api";
import { copy, type Locale } from "@/lib/i18n";
export function StepList({
  steps,
  seconds,
  locale,
}: {
  steps: Step[];
  seconds: number;
  locale: Locale;
}) {
  return (
    <output className="progress" aria-live="polite">
      <div className="progress-heading">
        <span className="pulse" /> {copy[locale].thinking}
        <span className="elapsed">
          {seconds} {copy[locale].seconds}
        </span>
      </div>
      {steps.map((step, index) => (
        <div className="step" key={`${step.tool}-${index}`}>
          {locale === "ru" ? step.label_ru : step.label_uz}
        </div>
      ))}
    </output>
  );
}
