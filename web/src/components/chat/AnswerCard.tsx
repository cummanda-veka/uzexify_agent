import { Badge } from "@/components/ui/badge";
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
    <article className="answer-card">
      <div className="answer-meta">
        <Badge variant="secondary" className={`answer-badge ${answer.kind}`}>
          {t[answer.kind]}
        </Badge>
        <span>
          {(answer.duration_ms / 1000).toFixed(1)} {t.seconds}
        </span>
        {answer.model && <span className="model">{answer.model}</span>}
      </div>
      <div className="answer-text">{answer.text}</div>
      <EvidencePanel
        answer={answer}
        locale={locale}
        open={open}
        onToggle={onToggle}
      />
    </article>
  );
}
