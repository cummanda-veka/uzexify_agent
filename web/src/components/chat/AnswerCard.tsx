import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { AnimatedList } from "@/components/bits";
import type { AskResponse } from "@/lib/api";
import { copy, type Locale } from "@/lib/i18n";
import { AnswerChart } from "./AnswerChart";
import { EvidencePanel } from "./EvidencePanel";

// Module-level so ReactMarkdown sees the same component types on every render; inline objects
// would make React remount every table (visible as a blink).
const REMARK_PLUGINS = [remarkGfm];
const MD_COMPONENTS: Components = {
  table: ({ node: _node, ...props }) => (
    <div className="md-table">
      <table {...props} />
    </div>
  ),
};

export function AnswerCard({
  id,
  answer,
  locale,
  open,
  onToggle,
  onPick,
}: {
  id: string;
  answer: AskResponse;
  locale: Locale;
  open: boolean;
  onToggle: (id: string) => void;
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
          remarkPlugins={REMARK_PLUGINS}
          components={MD_COMPONENTS}
        >
          {answer.text}
        </ReactMarkdown>
      </div>
      {answer.charts?.map((chart) => (
        <AnswerChart
          key={chart.id}
          spec={chart}
          evidence={answer.evidence}
          language={answer.language}
        />
      ))}
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
        onToggle={() => onToggle(id)}
      />
    </article>
  );
}
