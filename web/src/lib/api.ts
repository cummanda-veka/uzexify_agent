export type Step = {
  type: "tool_call" | "tool_result";
  call_id: string;
  tool: string;
  /** Present on tool_result: false when the tool raised and the agent retries. */
  ok?: boolean;
  label_ru: string;
  label_uz: string;
};
export type Evidence = {
  sql_id: string;
  purpose: string;
  sql: string;
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  duration_ms: number;
};
export type ChartSeries = { column: string; unit: string; label: string };
export type ChartSpec = {
  id: string;
  sql_id: string;
  type: "bar" | "hbar" | "line" | "grouped_bar" | "panels";
  x: string;
  series: ChartSeries[];
  title: string;
};
export type Entity = {
  kind: "company" | "broker" | "product";
  query: string;
  matches: { id: string; label: string; score: number }[];
};
export type AskResponse = {
  id: string;
  session_id: string;
  question: string;
  language: "ru" | "uz";
  kind: "answer" | "no_data" | "clarify" | "error";
  text: string;
  evidence: Evidence[];
  entities: Entity[];
  charts?: ChartSpec[];
  model: string;
  duration_ms: number;
  trace_id: string | null;
};
export type StreamError = {
  code: "timeout" | "unavailable" | "internal";
  message_ru: string;
  message_uz: string;
};

type Handlers = {
  onStep: (step: Step) => void;
  onAnswer: (answer: AskResponse) => void;
  onError: (error: StreamError) => void;
};

/** Server-rendered infographic (same template as Telegram); the server re-validates chart + rows. */
export async function chartPng(
  chart: ChartSpec,
  evidence: Evidence,
): Promise<Blob> {
  const response = await fetch(
    `${process.env.NEXT_PUBLIC_API_BASE ?? ""}/api/chart.png`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chart, evidence }),
    },
  );
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.blob();
}

export type Effort = "low" | "medium" | "high";

export async function askStream(
  question: string,
  sessionId: string,
  handlers: Handlers,
  signal: AbortSignal,
  effort?: Effort,
) {
  const response = await fetch(
    `${process.env.NEXT_PUBLIC_API_BASE ?? ""}/api/ask/stream`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Client": "web" },
      body: JSON.stringify({ question, session_id: sessionId, effort }),
      signal,
    },
  );
  if (!response.ok || !response.body)
    throw new Error(`HTTP ${response.status}`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let event = "message";
  let data: string[] = [];
  let finished = false;
  const line = (value: string) => {
    if (value === "") {
      if (data.length) {
        const payload = JSON.parse(data.join("\n"));
        if (event === "step") handlers.onStep(payload as Step);
        if (event === "answer") {
          finished = true;
          handlers.onAnswer(payload as AskResponse);
        }
        if (event === "error") {
          finished = true;
          handlers.onError(payload as StreamError);
        }
      }
      event = "message";
      data = [];
      return;
    }
    if (value.startsWith(":")) return;
    const colon = value.indexOf(":");
    const field = colon < 0 ? value : value.slice(0, colon);
    let contents = colon < 0 ? "" : value.slice(colon + 1);
    if (contents.startsWith(" ")) contents = contents.slice(1);
    if (field === "event") event = contents;
    if (field === "data") data.push(contents);
  };
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const trailingCR = !done && buffer.endsWith("\r");
    if (trailingCR) buffer = buffer.slice(0, -1);
    const lines = buffer.split(/\r\n|\r|\n/);
    buffer = (lines.pop() ?? "") + (trailingCR ? "\r" : "");
    for (const item of lines) line(item);
    if (done) {
      if (buffer) line(buffer);
      line("");
      break;
    }
  }
  if (!finished) throw new Error("Stream ended without an answer");
}
