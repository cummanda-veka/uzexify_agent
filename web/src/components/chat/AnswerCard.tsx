import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AnimatedList } from "@/components/bits";
import type { AskResponse } from "@/lib/api";
import { copy, type Locale } from "@/lib/i18n";
import { EvidencePanel } from "./EvidencePanel";

export function AnswerCard({
  answer,
  locale,
  open,
  onToggle,
  onPick,
}: {
  answer: AskResponse;
  locale: Locale;
  open: boolean;
  onToggle: () => void;
  /** Sends a clarify candidate back as the follow-up question; absent when picking is not possible. */
  onPick?: (label: string) => void;
}) {
  const t = copy[locale];
  const found =
    answer.kind === "clarify"
      ? answer.entities
          .filter((e) => e.kind !== "product")
          .flatMap((e) => e.matches)
      : [];
  // Offer the candidates the agent actually named; fall back to the search hits if it named none.
  const named = found.filter((m) => answer.text.includes(m.label));
  const candidates = (named.length > 0 ? named : found).slice(0, 5);
  return (
    <article className="answer" data-kind={answer.kind}>
      {answer.kind !== "answer" && (
        <span className="answer-kind">{t[answer.kind]}</span>
      )}
      <div className="answer-text markdown">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            table: ({ node: _node, ...props }) => (
              <div className="md-table">
                <table {...props} />
              </div>
            ),
          }}
        >
          {answer.text}
        </ReactMarkdown>
      </div>
      {candidates.length > 0 && onPick && (
        <AnimatedList
          className="candidates"
          items={candidates.map((m) => ({ title: m.label, meta: m.id }))}
          onItemSelect={(item) => onPick(item.title)}
          selectOnHover={false}
          showGradients={false}
          displayScrollbar={false}
          width="100%"
          maxHeight={320}
          radius={14}
        />
      )}
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
