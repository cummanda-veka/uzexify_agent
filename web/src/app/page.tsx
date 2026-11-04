"use client";
import { BarChart3, Database, Languages } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ChatInput } from "@/components/chat/ChatInput";
import { ExampleChips } from "@/components/chat/ExampleChips";
import { type Message, MessageList } from "@/components/chat/MessageList";
import { StepList } from "@/components/chat/StepList";
import { askStream, type Step } from "@/lib/api";
import { copy, type Locale } from "@/lib/i18n";

export default function Home() {
  const [locale, setLocale] = useState<Locale>("ru");
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [steps, setSteps] = useState<Step[]>([]);
  const [seconds, setSeconds] = useState(0);
  const [openId, setOpenId] = useState<string | null>(null);
  const session = useRef("");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    const saved = localStorage.getItem("uzexify-language");
    if (saved === "ru" || saved === "uz") setLocale(saved);
    session.current =
      localStorage.getItem("uzexify-session") || crypto.randomUUID();
    localStorage.setItem("uzexify-session", session.current);
    return () => controller.current?.abort();
  }, []);
  useEffect(() => {
    if (!busy) return;
    const timer = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(timer);
  }, [busy]);
  function changeLocale(next: Locale) {
    setLocale(next);
    localStorage.setItem("uzexify-language", next);
  }
  async function send(question: string, retryId?: string) {
    if (busy) return;
    const id = retryId ?? crypto.randomUUID();
    setMessages((current) =>
      retryId
        ? current.map((m) => (m.id === id ? { id, question } : m))
        : [...current, { id, question }],
    );
    setBusy(true);
    setSteps([]);
    setSeconds(0);
    controller.current = new AbortController();
    try {
      await askStream(
        question,
        session.current,
        {
          onStep: (step) => setSteps((current) => [...current, step]),
          onAnswer: (answer) => {
            setMessages((current) =>
              current.map((m) => (m.id === id ? { ...m, answer } : m)),
            );
            setOpenId(id);
          },
          onError: (error) =>
            setMessages((current) =>
              current.map((m) =>
                m.id === id
                  ? {
                      ...m,
                      error:
                        locale === "ru" ? error.message_ru : error.message_uz,
                    }
                  : m,
              ),
            ),
        },
        controller.current.signal,
      );
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError"))
        setMessages((current) =>
          current.map((m) =>
            m.id === id ? { ...m, error: copy[locale].network } : m,
          ),
        );
    } finally {
      setBusy(false);
    }
  }
  const t = copy[locale];
  return (
    <main>
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">
            <BarChart3 size={19} />
          </span>
          <span>
            uzexify<span className="brand-dot">.</span>
          </span>
          <span className="brand-divider" />
          <span className="brand-sub">DATA ASSISTANT</span>
        </div>
        <div className="language">
          <Languages size={16} />
          <button
            type="button"
            className={locale === "ru" ? "selected" : ""}
            onClick={() => changeLocale("ru")}
            aria-pressed={locale === "ru"}
          >
            RU
          </button>
          <span>/</span>
          <button
            type="button"
            className={locale === "uz" ? "selected" : ""}
            onClick={() => changeLocale("uz")}
            aria-pressed={locale === "uz"}
          >
            UZ
          </button>
        </div>
      </header>
      <div className="workspace">
        <div className="hero">
          <div className="eyebrow">
            <span className="eyebrow-line" />
            {t.eyebrow}
          </div>
          <h1>
            {t.title}
            <span className="title-dot">.</span>
          </h1>
          <p>{t.intro}</p>
          <div className="source-line">
            <Database size={15} />
            <span>UZEX SPOT DATA</span>
            <span className="source-separator">/</span>
            <span>2022 — 2026</span>
          </div>
        </div>
        <div className="chat-area">
          <MessageList
            messages={messages}
            locale={locale}
            openId={openId}
            setOpenId={setOpenId}
            retry={(id) => {
              const message = messages.find((m) => m.id === id);
              if (message) void send(message.question, id);
            }}
          />
          {busy && <StepList steps={steps} seconds={seconds} locale={locale} />}
          <ChatInput
            locale={locale}
            busy={busy}
            onSend={(question) => void send(question)}
          />
          {messages.length === 0 && (
            <ExampleChips
              locale={locale}
              onSelect={(question) => void send(question)}
            />
          )}
        </div>
      </div>
      <footer>
        <span>UZEXIFY / DATA ASSISTANT</span>
        <span>RU · O‘ZBEK</span>
      </footer>
    </main>
  );
}
