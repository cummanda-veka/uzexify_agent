"use client";
import {
  addTransitionType,
  startTransition,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  ViewTransition,
} from "react";
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
  // Viewport state: shell height/offset and whether the on-screen keyboard is up. The welcome screen
  // does not react to the keyboard beyond its height: parts that no longer fit are dropped by CSS
  // container queries on the welcome screen's own height.
  const [viewport, setViewport] = useState<{
    h: number;
    top: number;
    keyboard: boolean;
  } | null>(null);
  const prevKeyboard = useRef(false);
  useLayoutEffect(() => {
    if (!viewport) return;
    const root = document.documentElement;
    // Keyboard closing on the welcome screen: the composer moves from the keyboard back to its
    // centred place. FLIP it — measure, relayout, then animate from the old position — instead of
    // letting it jump (justify-content itself cannot be transitioned).
    const composer = document.querySelector<HTMLElement>(".welcome .composer");
    const closing = prevKeyboard.current && !viewport.keyboard;
    const before = closing ? composer?.getBoundingClientRect().top : undefined;
    root.style.setProperty("--vv-h", `${viewport.h}px`);
    root.style.setProperty("--vv-top", `${viewport.top}px`);
    root.toggleAttribute("data-kb", viewport.keyboard);
    prevKeyboard.current = viewport.keyboard;
    if (
      composer &&
      before !== undefined &&
      !matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      const delta = before - composer.getBoundingClientRect().top;
      if (Math.abs(delta) > 1)
        composer.animate(
          [
            { transform: `translateY(${delta}px)` },
            { transform: "translateY(0)" },
          ],
          { duration: 360, easing: "cubic-bezier(0.22, 1, 0.36, 1)" },
        );
    }
  }, [viewport]);

  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return undefined;
    // iOS reports the keyboard opening at once but its closing only after the slide-out animation
    // (~250 ms), which kept the composer hanging in mid-air. The keyboard can only be up while an
    // editable element has focus, so without focus the shell snaps to the full height immediately.
    const editing = () => {
      const el = document.activeElement;
      return (
        el instanceof HTMLElement &&
        (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))
      );
    };
    const apply = () => {
      if (vv.scale > 1.01) return; // pinch-zoom, not a keyboard
      const kb = editing() && window.innerHeight - vv.height > 120;
      setViewport({
        h: Math.round(kb ? vv.height : window.innerHeight),
        top: Math.round(kb ? vv.offsetTop : 0),
        keyboard: kb,
      });
      // Safari may leave the layout viewport scrolled after the keyboard closes.
      if (!kb && window.scrollY !== 0) window.scrollTo(0, 0);
    };
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(apply);
    };
    // Blur is synchronous with the tap that dismisses the keyboard; focus moving to another field
    // is checked after the event settles.
    const onFocusOut = () => setTimeout(apply, 0);
    update();
    vv.addEventListener("resize", update);
    vv.addEventListener("scroll", update);
    document.addEventListener("focusout", onFocusOut);
    document.addEventListener("focusin", update);
    return () => {
      cancelAnimationFrame(frame);
      vv.removeEventListener("resize", update);
      vv.removeEventListener("scroll", update);
      document.removeEventListener("focusout", onFocusOut);
      document.removeEventListener("focusin", update);
    };
  }, []);

  // The floating composer's height (grows with multi-line text) becomes the thread's bottom room.
  // Measured in a layout effect so it is in place before a view transition snapshots the new page.
  // biome-ignore lint/correctness/useExhaustiveDependencies: the dock mounts when `empty` flips
  useLayoutEffect(() => {
    const dock = dockRef.current;
    if (!dock) return undefined;
    const root = document.documentElement;
    const measure = () =>
      root.style.setProperty("--dock-h", `${Math.round(dock.offsetHeight)}px`);
    measure();
    const observer = new ResizeObserver(measure);
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
    const add = () =>
      setMessages((current) =>
        retryId
          ? current.map((m) => (m.id === id ? { id, question, steps: [] } : m))
          : [...current, { id, question, steps: [] }],
      );
    // Leaving the welcome screen is a view transition: the composer glides down into the dock.
    if (messagesRef.current.length === 0)
      startTransition(() => {
        addTransitionType("start-chat");
        add();
      });
    else add();
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
        <ViewTransition exit="vt-fade-out">
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
            <ViewTransition name="composer">{composer}</ViewTransition>
            <ExampleChips locale={locale} onSelect={(q) => void send(q)} />
          </section>
        </ViewTransition>
      ) : (
        <>
          <ViewTransition enter="vt-appear">
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
          </ViewTransition>
          <div className="dock" ref={dockRef}>
            <ViewTransition name="composer">{composer}</ViewTransition>
          </div>
        </>
      )}
    </main>
  );
}
