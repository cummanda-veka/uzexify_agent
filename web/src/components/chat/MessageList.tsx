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

export function MessageList({
  messages,
  locale,
  busyId,
  openId,
  setOpenId,
  retry,
  pick,
}: {
  messages: Message[];
  locale: Locale;
  busyId: string | null;
  openId: string | null;
  setOpenId: (id: string | null) => void;
  retry: (id: string) => void;
  pick: (label: string) => void;
}) {
  return (
    <div className="messages">
      {messages.map((message, index) => {
        const working = busyId === message.id;
        const last = index === messages.length - 1;
        return (
          <section className="exchange" key={message.id}>
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
                answer={message.answer}
                locale={locale}
                open={openId === message.id}
                onToggle={() =>
                  setOpenId(openId === message.id ? null : message.id)
                }
                onPick={last && !busyId ? pick : undefined}
              />
            )}
            {(message.error || message.cancelled) && (
              <div
                className={message.error ? "error-message" : "stopped-message"}
                role={message.error ? "alert" : "status"}
              >
                <span>{message.error ?? copy[locale].stopped}</span>
                <button type="button" onClick={() => retry(message.id)}>
                  {copy[locale].retry}
                </button>
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
