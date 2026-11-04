import type { AskResponse } from "@/lib/api";
import { copy, type Locale } from "@/lib/i18n";
import { EvidencePanel } from "./EvidencePanel";

export function AnswerCard({
  answer,
  locale,
  open,
  onToggle,
}: {
  answer: AskResponse;
  locale: Locale;
  open: boolean;
  onToggle: () => void;
}) {
  const t = copy[locale];
  return (
    <article className="answer" data-kind={answer.kind}>
      {answer.kind !== "answer" && (
        <span className="answer-kind">{t[answer.kind]}</span>
      )}
      <div className="answer-text">{answer.text}</div>
      {answer.model && (
        <div className="answer-meta">{answer.model.split("/").pop()}</div>
      )}
      <EvidencePanel
        answer={answer}
        locale={locale}
        open={open}
        onToggle={onToggle}
      />
    </article>
  );
}
