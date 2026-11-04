import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const sans = Geist({ subsets: ["latin", "cyrillic"], variable: "--font-sans" });
const mono = Geist_Mono({
  subsets: ["latin", "cyrillic"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "UZEXify — сделки UZEX",
  description:
    "Ответы на вопросы о биржевых сделках UZEX на русском и узбекском, с SQL-основанием.",
};

export const viewport: Viewport = { themeColor: "#07080d" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ru" className={`${sans.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
