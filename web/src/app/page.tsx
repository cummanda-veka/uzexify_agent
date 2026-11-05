"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { StickToBottom, type StickToBottomContext } from "use-stick-to-bottom";
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

export default function Home() {
  const [locale, setLocale] = useState<Locale>("ru");
  const [messages, setMessages] = useState<Message[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const session = useRef("");
  const controller = useRef<AbortController | null>(null);
  // Thinking level, by index into EFFORTS (labels are localised; the index survives a language switch).
  const effort = useRef<Effort>("low");
  const stick = useRef<StickToBottomContext>(null);
  const dockRef = useRef<HTMLDivElement>(null);
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

  // Layout model (iOS-safe): the document never scrolls. `.app` is an app shell pinned to the
  // *visual* viewport — its height and top follow visualViewport, so when the on-screen keyboard
  // opens the shell shrinks, the composer sits right on the keyboard and Safari has nothing to pan.
  // The thread is the only scroll container, managed by use-stick-to-bottom (follows a running
  // answer while the reader is at the bottom, lets go as soon as they scroll up).
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return undefined;
    const root = document.documentElement;
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (vv.scale > 1.01) return; // pinch-zoom, not a keyboard
        root.style.setProperty("--vv-h", `${Math.round(vv.height)}px`);
        root.style.setProperty("--vv-top", `${Math.round(vv.offsetTop)}px`);
        root.toggleAttribute("data-kb", window.innerHeight - vv.height > 120);
        // Safari may leave the layout viewport scrolled after the keyboard closes.
        if (window.scrollY !== 0 && vv.offsetTop === 0) window.scrollTo(0, 0);
      });
    };
    update();
    vv.addEventListener("resize", update);
    vv.addEventListener("scroll", update);
    return () => {
      cancelAnimationFrame(frame);
      vv.removeEventListener("resize", update);
      vv.removeEventListener("scroll", update);
    };
  }, []);

  // The floating composer's height (grows with multi-line text) becomes the thread's bottom room.
  // biome-ignore lint/correctness/useExhaustiveDependencies: the dock mounts when `empty` flips
  useEffect(() => {
    const dock = dockRef.current;
    if (!dock) return undefined;
    const root = document.documentElement;
    const observer = new ResizeObserver(() =>
      root.style.setProperty("--dock-h", `${Math.round(dock.offsetHeight)}px`),
    );
    observer.observe(dock);
    return () => observer.disconnect();
  }, [empty]);

  // A send always brings the new question into view, even if the reader had scrolled up.
  // biome-ignore lint/correctness/useExhaustiveDependencies: runs when a message is added
  useEffect(() => {
    if (!empty) void stick.current?.scrollToBottom("smooth");
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

  // Stable handlers for the memoised message list (it skips settled exchanges on re-render).
  const sendRef = useRef<(question: string, retryId?: string) => Promise<void>>(
    async () => {},
  );
  const messagesRef = useRef(messages);
  messagesRef.current = messages;
  const onToggle = useCallback(
    (id: string) => setOpenId((current) => (current === id ? null : id)),
    [],
  );
  const onPick = useCallback(
    (label: string) => void sendRef.current(label),
    [],
  );
  const onRetry = useCallback((id: string) => {
    const message = messagesRef.current.find((m) => m.id === id);
    if (message) void sendRef.current(message.question, id);
  }, []);

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
  sendRef.current = send;

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
          <StickToBottom
            className="thread-frame"
            contextRef={stick}
            initial="instant"
            resize="smooth"
          >
            <StickToBottom.Content
              className="thread"
              scrollClassName="thread-scroll"
            >
              <MessageList
                messages={messages}
                locale={locale}
                busyId={busyId}
                openId={openId}
                onToggle={onToggle}
                onRetry={onRetry}
                onPick={onPick}
              />
            </StickToBottom.Content>
            <GradualBlur
              position="top"
              height="4.5rem"
              strength={1.5}
              zIndex={3}
            />
            <GradualBlur
              position="bottom"
              height="calc(var(--dock-h, 140px) + 2.5rem)"
              strength={1.5}
              zIndex={3}
            />
          </StickToBottom>
          <div className="dock" ref={dockRef}>
            {composer}
          </div>
        </>
      )}
    </main>
  );
}
