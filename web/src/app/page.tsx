"use client";
import { useEffect, useRef, useState } from "react";
import {
  DecryptedText,
  GradientASCII,
  GradualBlur,
  HalftoneMark,
  PromptBar,
  RubberSegment,
} from "@/components/bits";
import { ExampleChips } from "@/components/chat/ExampleChips";
import { type Message, MessageList } from "@/components/chat/MessageList";
import { askStream, type Effort } from "@/lib/api";
import { copy, examples, type Locale } from "@/lib/i18n";

const MONO = '"Geist Mono", ui-monospace, SFMono-Regular, Menlo, monospace';

// Example questions shown in the empty prompt; Uzbek Cyrillic examples get a Cyrillic lead-in.
const HINTS = Object.fromEntries(
  (Object.keys(examples) as Locale[]).map((locale) => [
    locale,
    examples[locale].map((q) =>
      locale === "uz" && /[а-яўқғҳ]/i.test(q)
        ? `Масалан: ${q}`
        : `${copy[locale].examplePrefix}${q}`,
    ),
  ]),
) as Record<Locale, string[]>;

const EFFORTS: Effort[] = ["low", "medium", "high"];

const scrollToEnd = (smooth: boolean) =>
  window.scrollTo({
    top: document.documentElement.scrollHeight,
    behavior: smooth ? "smooth" : "auto",
  });

export default function Home() {
  const [locale, setLocale] = useState<Locale>("ru");
  const [messages, setMessages] = useState<Message[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const session = useRef("");
  const controller = useRef<AbortController | null>(null);
  // Thinking level, by index into EFFORTS (labels are localised; the index survives a language switch).
  const effort = useRef<Effort>("low");
  const dockRef = useRef<HTMLDivElement>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  const busy = busyId !== null;
  const empty = messages.length === 0;
  const t = copy[locale];
  const hints = HINTS[locale];
  const effortLabels: readonly string[] = t.efforts;

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

  // Scrolling. The thread scrolls with the window; the top bar and the input dock are fixed.
  // - Mobile keyboards shrink only the visual viewport: their height goes into --kb so the dock rides
  //   above them.
  // - The dock's height (it grows with the text and wraps) goes into --dock-h, which the thread uses
  //   as its bottom padding, so the last answer is never hidden under it.
  // - The thread follows a running answer only while the reader is at the bottom; a send always
  //   scrolls down, and re-scrolls while the viewport settles (keyboard closing).
  const pinned = useRef(true);
  const sentAt = useRef(0);

  useEffect(() => {
    const root = document.documentElement;
    // Only the reader's own input may unpin: smooth scrolls and growing content also fire `scroll`.
    let userAt = 0;
    const markUser = () => {
      userAt = performance.now();
    };
    const onScroll = () => {
      const gap = root.scrollHeight - (window.scrollY + window.innerHeight);
      if (gap < 96) pinned.current = true;
      else if (performance.now() - userAt < 800) pinned.current = false;
    };
    const vv = window.visualViewport;
    let lastKb = 0;
    const onViewport = () => {
      if (!vv) return;
      const kb = Math.round(
        Math.max(0, window.innerHeight - vv.height - vv.offsetTop),
      );
      if (kb === lastKb) return;
      lastKb = kb;
      root.style.setProperty("--kb", `${kb}px`);
      root.toggleAttribute("data-kb", kb > 80);
      // Keyboard opened or closed: keep the end in view if the reader was there.
      if (pinned.current && root.dataset.screen === "thread")
        scrollToEnd(false);
    };
    const userEvents = ["wheel", "touchmove", "keydown"] as const;
    onViewport();
    window.addEventListener("scroll", onScroll, { passive: true });
    for (const e of userEvents)
      window.addEventListener(e, markUser, { passive: true });
    vv?.addEventListener("resize", onViewport);
    vv?.addEventListener("scroll", onViewport);
    return () => {
      window.removeEventListener("scroll", onScroll);
      for (const e of userEvents) window.removeEventListener(e, markUser);
      vv?.removeEventListener("resize", onViewport);
      vv?.removeEventListener("scroll", onViewport);
    };
  }, []);

  // The welcome screen fits the viewport and never scrolls (html[data-screen=welcome] locks it).
  useEffect(() => {
    document.documentElement.dataset.screen = empty ? "welcome" : "thread";
  }, [empty]);

  // The dock's height feeds the thread's bottom padding. While an answer is being produced, growth
  // of the thread keeps the bottom in view (if the reader is there). Once it is done the reader owns
  // the scroll: expanding evidence or a collapsing trace must not pull the page down.
  const busyRef = useRef(false);
  busyRef.current = busyId !== null;
  // biome-ignore lint/correctness/useExhaustiveDependencies: the dock and thread mount when `empty` flips
  useEffect(() => {
    const dock = dockRef.current;
    const thread = threadRef.current;
    if (!dock || !thread) return undefined;
    const root = document.documentElement;
    let lastHeight = thread.offsetHeight;
    const observer = new ResizeObserver(() => {
      root.style.setProperty("--dock-h", `${Math.round(dock.offsetHeight)}px`);
      const height = thread.offsetHeight;
      const grew = height > lastHeight;
      lastHeight = height;
      if (grew && busyRef.current && pinned.current) scrollToEnd(false);
    });
    observer.observe(dock);
    observer.observe(thread);
    return () => observer.disconnect();
  }, [empty]);

  // A send always brings the new question into view, even if the reader had scrolled up.
  // biome-ignore lint/correctness/useExhaustiveDependencies: runs when a message is added
  useEffect(() => {
    if (empty) return;
    pinned.current = true;
    scrollToEnd(true);
  }, [messages.length, empty]);

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
    sentAt.current = performance.now();
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
          onAnswer: (answer) => patch(id, { answer }),
          onError: (error) =>
            patch(id, {
              error: locale === "ru" ? error.message_ru : error.message_uz,
            }),
        },
        controller.current.signal,
        effort.current,
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
      placeholders={hints}
      busyPlaceholder={`${t.working}…`}
      busy={busy}
      onSend={(text) => void send(text)}
      onStop={() => controller.current?.abort()}
      labels={{
        prompt: t.prompt,
        send: t.send,
        stop: t.stop,
        effort: t.effort,
        faster: t.faster,
        smarter: t.smarter,
      }}
      efforts={effortLabels}
      defaultEffort={effortLabels[EFFORTS.indexOf(effort.current)]}
      onEffortChange={(label) => {
        effort.current = EFFORTS[effortLabels.indexOf(label)] ?? "low";
      }}
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
        <RubberSegment
          className="language"
          aria-label="Язык / Til"
          items={[
            { value: "ru", label: "RU" },
            { value: "uz", label: "O‘Z" },
          ]}
          value={locale}
          onChange={(value) => changeLocale(value as Locale)}
          size="sm"
          trackColor="rgba(16, 18, 26, 0.6)"
          thumbColor="rgba(127, 178, 255, 0.16)"
          textColor="#7d869b"
          activeTextColor="#eef1f8"
          radius={9}
        />
      </header>

      {empty ? (
        <section className="welcome">
          <div className="mark">
            <HalftoneMark label="UZEXify" />
          </div>
          <h1>
            <DecryptedText
              key={locale}
              text={t.title}
              animateOn="view"
              sequential
              revealDirection="start"
              speed={35}
              characters="=+xX0S8#@"
              encryptedClassName="encrypted"
            />
          </h1>
          <p>{t.intro}</p>
          {composer}
          <ExampleChips locale={locale} onSelect={(q) => void send(q)} />
        </section>
      ) : (
        <>
          <div className="thread" ref={threadRef}>
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
              pick={(label) => void send(label)}
            />
          </div>
          <GradualBlur
            target="page"
            position="top"
            height="5rem"
            strength={1.5}
            zIndex={3}
          />
          <GradualBlur
            target="page"
            position="bottom"
            height="9rem"
            strength={1.5}
            zIndex={3}
          />
          <div className="dock" ref={dockRef}>
            {composer}
          </div>
        </>
      )}
    </main>
  );
}
