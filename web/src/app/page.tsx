"use client";
import { useEffect, useRef, useState } from "react";
import { GradientASCII, HalftoneMark, PromptBar } from "@/components/bits";
import { ExampleChips } from "@/components/chat/ExampleChips";
import { type Message, MessageList } from "@/components/chat/MessageList";
import { askStream } from "@/lib/api";
import { copy, type Locale } from "@/lib/i18n";

const MONO = '"Geist Mono", ui-monospace, SFMono-Regular, Menlo, monospace';

export default function Home() {
  const [locale, setLocale] = useState<Locale>("ru");
  const [messages, setMessages] = useState<Message[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const session = useRef("");
  const controller = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const busy = busyId !== null;
  const empty = messages.length === 0;
  const t = copy[locale];

  useEffect(() => {
    const saved = localStorage.getItem("uzexify-language");
    if (saved === "ru" || saved === "uz") setLocale(saved);
    session.current =
      localStorage.getItem("uzexify-session") || crypto.randomUUID();
    localStorage.setItem("uzexify-session", session.current);
    return () => controller.current?.abort();
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const lastStepCount = messages.at(-1)?.steps.length ?? 0;
  const lastAnswered = Boolean(messages.at(-1)?.answer);
  useEffect(() => {
    if (messages.length === 0 && lastStepCount === 0 && !lastAnswered) return;
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, lastStepCount, lastAnswered]);

  function changeLocale(next: Locale) {
    setLocale(next);
    localStorage.setItem("uzexify-language", next);
  }

  function patch(id: string, update: Partial<Message>) {
    setMessages((current) =>
      current.map((m) => (m.id === id ? { ...m, ...update } : m)),
    );
  }

  function newChat() {
    controller.current?.abort();
    session.current = crypto.randomUUID();
    localStorage.setItem("uzexify-session", session.current);
    setMessages([]);
    setOpenId(null);
  }

  async function send(question: string, retryId?: string) {
    if (busy || !question.trim()) return;
    const id = retryId ?? crypto.randomUUID();
    setMessages((current) =>
      retryId
        ? current.map((m) => (m.id === id ? { id, question, steps: [] } : m))
        : [...current, { id, question, steps: [] }],
    );
    setBusyId(id);
    controller.current = new AbortController();
    try {
      await askStream(
        question,
        session.current,
        {
          onStep: (step) =>
            setMessages((current) =>
              current.map((m) =>
                m.id === id ? { ...m, steps: [...m.steps, step] } : m,
              ),
            ),
          onAnswer: (answer) => {
            patch(id, { answer });
            setOpenId(id);
          },
          onError: (error) =>
            patch(id, {
              error: locale === "ru" ? error.message_ru : error.message_uz,
            }),
        },
        controller.current.signal,
      );
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError")
        patch(id, { cancelled: true });
      else patch(id, { error: t.network });
    } finally {
      setBusyId(null);
    }
  }

  const composer = (
    <PromptBar
      className="composer"
      placeholder={t.placeholder}
      busy={busy}
      onSend={(text) => void send(text)}
      onStop={() => controller.current?.abort()}
      labels={{ prompt: t.prompt, send: t.send, stop: t.stop }}
      background="rgba(22, 24, 33, 0.82)"
      color="#eef1f8"
      sparkColor="#7fb2ff"
      width={720}
      radius={18}
      maxRows={6}
    />
  );

  return (
    <main className={empty ? "app is-empty" : "app"}>
      <div className="backdrop" aria-hidden="true">
        <GradientASCII
          cellSize={16}
          speed={0.6}
          clickEffect="none"
          fontFamily={MONO}
        />
      </div>

      <header className="topbar">
        <button
          type="button"
          className="wordmark"
          onClick={newChat}
          disabled={empty}
          title={empty ? undefined : t.newChat}
        >
          uzexify
        </button>
        <fieldset className="language" aria-label="Language">
          {(["ru", "uz"] as const).map((code) => (
            <button
              key={code}
              type="button"
              aria-pressed={locale === code}
              onClick={() => changeLocale(code)}
            >
              {code === "ru" ? "RU" : "O‘Z"}
            </button>
          ))}
        </fieldset>
      </header>

      {empty ? (
        <section className="welcome">
          <div className="mark">
            <HalftoneMark label="UZEXify" />
          </div>
          <h1>{t.title}</h1>
          <p>{t.intro}</p>
          {composer}
          <ExampleChips locale={locale} onSelect={(q) => void send(q)} />
        </section>
      ) : (
        <>
          <div className="thread">
            <MessageList
              messages={messages}
              locale={locale}
              busyId={busyId}
              openId={openId}
              setOpenId={setOpenId}
              retry={(id) => {
                const message = messages.find((m) => m.id === id);
                if (message) void send(message.question, id);
              }}
            />
            <div ref={endRef} />
          </div>
          <div className="dock">{composer}</div>
        </>
      )}
    </main>
  );
}
