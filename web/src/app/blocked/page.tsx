import type { Metadata } from "next";
import { HalftoneMark } from "@/components/bits";
import "./blocked.css";

export const metadata: Metadata = {
  title: "UZEXify — доступ из Узбекистана",
  robots: { index: false },
};

// Shown by the Caddy country gate (backend /internal/geo) to visitors outside Uzbekistan.
export default function Blocked() {
  return (
    <main className="blocked">
      <div className="blocked-mark">
        <HalftoneMark label="UZEXify" />
      </div>
      <section lang="ru">
        <h1>Сайт работает только из Узбекистана</h1>
        <p>Откройте его без VPN с узбекского интернета.</p>
      </section>
      <hr />
      <section lang="uz">
        <h1>Sayt faqat O‘zbekistondan ishlaydi</h1>
        <p>Uni VPN’siz, O‘zbekiston internetidan oching.</p>
      </section>
    </main>
  );
}
