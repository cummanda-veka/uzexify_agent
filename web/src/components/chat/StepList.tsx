import { CallChip, ThoughtLine } from "@/components/bits";
import type { Step } from "@/lib/api";
import { copy, type Locale } from "@/lib/i18n";

type Call = { tool: string; label: string; result?: Step };

/** Pairs each tool_call with the tool_result that follows it. */
function toCalls(steps: Step[], locale: Locale): Call[] {
  const calls: Call[] = [];
  for (const step of steps) {
    const label = locale === "ru" ? step.label_ru : step.label_uz;
    if (step.type === "tool_call") calls.push({ tool: step.tool, label });
    else {
      const open = calls.findLast((c) => c.tool === step.tool && !c.result);
      if (open) open.result = step;
    }
  }
  return calls;
}

/** Live (working) or settled trace of agent tool calls. */
export function StepList({
  steps,
  locale,
  working,
  cancelled,
  elapsed,
}: {
  steps: Step[];
  locale: Locale;
  working: boolean;
  cancelled?: boolean;
  elapsed?: number;
}) {
  const t = copy[locale];
  const chips = toCalls(steps, locale).map((call, i) => {
    const [name, argument = ""] = call.label.split(/:\s*/, 2);
    const resultLabel = call.result
      ? locale === "ru"
        ? call.result.label_ru
        : call.result.label_uz
      : "";
    // Results carry a row count; a result without digits is the agent's "error, retrying" step.
    const failed = Boolean(call.result) && !/\d/.test(resultLabel);
    const status = call.result
      ? failed
        ? "error"
        : "done"
      : working
        ? "running"
        : "error";
    return (
      <CallChip
        key={`${call.tool}-${i}`}
        icon={call.tool === "run_sql" ? "terminal" : "search"}
        name={name}
        argument={argument || resultLabel}
        status={status}
        size={28}
        surfaceColor="rgba(22, 24, 33, 0.85)"
        color="#cfd6e6"
        doneColor="#5fd39a"
        errorColor="#ff8a7a"
        showTimer={false}
      />
    );
  });
  return (
    <ThoughtLine
      className="steps"
      working={working}
      elapsed={working ? undefined : elapsed}
      label={t.working}
      doneLabel={cancelled ? t.stopped : t.done}
      steps={chips}
      glyph="sparkle"
      color="#b9c0d0"
      glyphColor="#7fb2ff"
      fontSize={14}
      collapseOnSettle
    />
  );
}
