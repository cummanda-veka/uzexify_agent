import { memo } from "react";
import type { AskResponse, Step } from "@/lib/api";
import { copy, type Locale } from "@/lib/i18n";
import { AnswerCard } from "./AnswerCard";
import { StepList } from "./StepList";

export type Message = {
  id: string;
  question: string;
  steps: Step[];
  answer?: AskResponse;
  cancelled?: boolean;
  error?: string;
};

type Handlers = {
  /** All handlers must be stable (useCallback) so settled exchanges skip re-rendering. */
  onToggle: (id: string) => void;
  onRetry: (id: string) => void;
  onPick: (label: string) => void;
};

export function MessageList({
  messages,
  locale,
  busyId,
  openId,
  ...handlers
}: {
  messages: Message[];
  locale: Locale;
  busyId: string | null;
  openId: string | null;
} & Handlers) {
  return (
    <div className="messages">
      {messages.map((message, index) => (
        <Exchange
          key={message.id}
          message={message}
          locale={locale}
          working={busyId === message.id}
          open={openId === message.id}
          canPick={index === messages.length - 1 && !busyId}
          {...handlers}
        />
      ))}
    </div>
  );
}

/** One question with its trace and answer. Memoised: a running answer patches only its own
 * message object, so earlier exchanges (tables, charts, evidence) are not re-rendered. */
const Exchange = memo(function Exchange({
  message,
  locale,
  working,
  open,
  canPick,
  onToggle,
  onRetry,
  onPick,
}: {
  message: Message;
  locale: Locale;
  working: boolean;
  open: boolean;
  canPick: boolean;
} & Handlers) {
  return (
    <section className="exchange">
      <p className="question">{message.question}</p>
      {(working || message.steps.length > 0) && (
        <StepList
          steps={message.steps}
          locale={locale}
          working={working}
          cancelled={message.cancelled}
          elapsed={
            message.answer ? message.answer.duration_ms / 1000 : undefined
          }
        />
      )}
      {message.answer && (
        <AnswerCard
          id={message.id}
          answer={message.answer}
          locale={locale}
          open={open}
          onToggle={onToggle}
          onPick={canPick ? onPick : undefined}
        />
      )}
      {(message.error || message.cancelled) && (
        <div
          className={message.error ? "error-message" : "stopped-message"}
          role={message.error ? "alert" : "status"}
        >
          <span>{message.error ?? copy[locale].stopped}</span>
          <button type="button" onClick={() => onRetry(message.id)}>
            {copy[locale].retry}
          </button>
        </div>
      )}
    </section>
  );
});
