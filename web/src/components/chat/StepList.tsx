import { CallChip, LatticeLoader, ThoughtLine } from "@/components/bits";
import type { Step } from "@/lib/api";
import { copy, type Locale } from "@/lib/i18n";

type Call = { id: string; tool: string; label: string; result?: Step };

/** Pairs each tool_call with its tool_result by call_id (parallel calls of one tool interleave). */
function toCalls(steps: Step[], locale: Locale): Call[] {
  const calls = new Map<string, Call>();
  for (const step of steps) {
    if (step.type === "tool_call")
      calls.set(step.call_id, {
        id: step.call_id,
        tool: step.tool,
        label: locale === "ru" ? step.label_ru : step.label_uz,
      });
    else {
      const call = calls.get(step.call_id);
      if (call) call.result = step;
    }
  }
  return [...calls.values()];
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
  const chips = toCalls(steps, locale).map((call) => {
    const [name, argument = ""] = call.label.split(/:\s*/, 2);
    const resultLabel = call.result
      ? locale === "ru"
        ? call.result.label_ru
        : call.result.label_uz
      : "";
    const status = call.result
      ? call.result.ok
        ? "done"
        : "error"
      : working
        ? "running"
        : "error";
    return (
      <CallChip
        key={call.id}
        className="step-chip"
        icon={
          call.tool === "run_sql"
            ? "terminal"
            : call.tool === "make_chart"
              ? "edit"
              : "search"
        }
        name={name}
        argument={argument || resultLabel}
        status={status}
        expectedMs={call.tool === "run_sql" ? 3000 : 1500}
        size={30}
        radius={9}
        surfaceColor="rgba(127, 178, 255, 0.05)"
        color="#cfd6e6"
        progressColor="#7fb2ff"
        progressOpacity={0.16}
        doneColor="#5fd39a"
        errorColor="#ff8a7a"
        washOpacity={0.12}
        showTimer={call.tool === "run_sql"}
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
      glyph={
        <LatticeLoader
          className="steps-lattice"
          status={working ? "working" : cancelled ? "error" : "done"}
          label=""
          doneLabel=""
          errorLabel=""
          showTimer={false}
          cellSize={4}
          gap={2}
          color="#7fb2ff"
          doneColor="#5fd39a"
          errorColor="#ff8a7a"
          glow
          glowColor="rgba(127, 178, 255, 0.55)"
        />
      }
      glyphStatic
      color="#b9c0d0"
      fontSize={14}
      collapseOnSettle
    />
  );
}
