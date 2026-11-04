import type { AskResponse } from "@/lib/api";
import type { Locale } from "@/lib/i18n";
import { AnswerCard } from "./AnswerCard";
export type Message = {
  id: string;
  question: string;
  answer?: AskResponse;
  error?: string;
};
export function MessageList({
  messages,
  locale,
  openId,
  setOpenId,
  retry,
}: {
  messages: Message[];
  locale: Locale;
  openId: string | null;
  setOpenId: (id: string | null) => void;
  retry: (id: string) => void;
}) {
  return (
    <div className="messages">
      {messages.map((message) => (
        <section className="exchange" key={message.id}>
          <div className="question">
            <span>Q</span>
            <p>{message.question}</p>
          </div>
          {message.answer && (
            <AnswerCard
              answer={message.answer}
              locale={locale}
              open={openId === message.id}
              onToggle={() =>
                setOpenId(openId === message.id ? null : message.id)
              }
            />
          )}
          {message.error && (
            <div className="error-message" role="alert">
              {message.error}
              <button type="button" onClick={() => retry(message.id)}>
                {locale === "ru" ? "Повторить" : "Qayta urinish"}
              </button>
            </div>
          )}
        </section>
      ))}
    </div>
  );
}
