import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "UZEXify — Data Assistant",
  description: "Ask questions about UZEX exchange transactions.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
