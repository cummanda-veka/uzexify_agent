"use client";
import { ArrowUp } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { copy, type Locale } from "@/lib/i18n";

export function ChatInput({
  locale,
  busy,
  onSend,
}: {
  locale: Locale;
  busy: boolean;
  onSend: (question: string) => void;
}) {
  const [value, setValue] = useState("");
  const t = copy[locale];
  function submit() {
    const question = value.trim();
    if (!question || busy) return;
    onSend(question);
    setValue("");
  }
  return (
    <div className="composer">
      <div className="composer-inner">
        <Textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (
              e.key === "Enter" &&
              !e.shiftKey &&
              !e.nativeEvent.isComposing
            ) {
              e.preventDefault();
              submit();
            }
          }}
          disabled={busy}
          maxLength={1000}
          placeholder={t.placeholder}
          aria-label={t.placeholder}
          className="question-input"
        />
        <Button
          aria-label={t.send}
          title={t.send}
          disabled={busy || !value.trim()}
          onClick={submit}
          className="send-button"
        >
          <ArrowUp size={19} />
        </Button>
      </div>
      <div className="composer-foot">
        <span>{t.hint}</span>
        <span>{value.length}/1000</span>
      </div>
    </div>
  );
}
