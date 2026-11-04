"use client";
import { Download, LoaderCircle } from "lucide-react";
import { useId, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  XAxis,
  YAxis,
} from "recharts";
import {
  type ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import {
  type ChartSeries,
  type ChartSpec,
  chartPng,
  type Evidence,
} from "@/lib/api";

const COLORS = ["#7fb2ff", "#ffcf6b", "#5fd39a", "#ff8a7a"];
// Axis ticks are scale marks, shown compactly in the answer language; exact SQL values are in the
// tooltip and the evidence table.
const COMPACT: Record<"ru" | "uz", Intl.NumberFormat> = {
  ru: new Intl.NumberFormat("ru-RU", {
    notation: "compact",
    maximumFractionDigits: 1,
  }),
  uz: new Intl.NumberFormat("uz-Latn", {
    notation: "compact",
    maximumFractionDigits: 1,
  }),
};
const TICK_LINE = 16;
// Room for a two-line label of TICK_LINE characters under each category.
const CATEGORY_MIN = 124;

/** Category label split into at most two lines so long product names stay readable under bars. */
function wrapLabel(text: string): string[] {
  const lines: string[] = [];
  let line = "";
  for (const word of text.split(/\s+/)) {
    if (line && (line + " " + word).length > TICK_LINE) {
      lines.push(line);
      line = word;
    } else line = line ? `${line} ${word}` : word;
  }
  if (line) lines.push(line);
  return lines.length > 2
    ? [
        lines[0],
        `${lines
          .slice(1)
          .join(" ")
          .slice(0, TICK_LINE - 1)}…`,
      ]
    : lines;
}

function WrappedTick({
  x,
  y,
  payload,
}: {
  x?: number;
  y?: number;
  payload?: { value: string };
}) {
  return (
    <text
      x={x}
      y={(y ?? 0) + 14}
      textAnchor="middle"
      fill="#8a93a8"
      fontSize={12}
    >
      <title>{payload?.value}</title>
      {wrapLabel(payload?.value ?? "").map((line, i) => (
        <tspan key={line} x={x} dy={i === 0 ? 0 : 14}>
          {line}
        </tspan>
      ))}
    </text>
  );
}

const DOWNLOAD = { ru: "Скачать PNG", uz: "PNG yuklab olish" };

/** Downloads the server-rendered infographic (same image as the Telegram bot sends). */
function DownloadButton({
  spec,
  evidence,
  language,
}: {
  spec: ChartSpec;
  evidence: Evidence;
  language: "ru" | "uz";
}) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  async function download() {
    setBusy(true);
    setFailed(false);
    try {
      const url = URL.createObjectURL(await chartPng(spec, evidence));
      const link = document.createElement("a");
      link.href = url;
      link.download = `${spec.title.replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-|-$/g, "") || "chart"}.png`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <button
      type="button"
      className="chart-download"
      onClick={() => void download()}
      disabled={busy}
      data-failed={failed || undefined}
      title={DOWNLOAD[language]}
    >
      {busy ? (
        <LoaderCircle size={14} className="spin" />
      ) : (
        <Download size={14} />
      )}
      <span>{DOWNLOAD[language]}</span>
    </button>
  );
}

/** Row keyed by app-owned names: "x" for the category, "s0".."s3" for series. SQL aliases never
 * become CSS variable names or SVG ids. */
type Row = Record<string, string | number>;
type Keyed = ChartSeries & { key: string; color: string };

/** One chart drawn only from the rows of the SQL evidence it references. */
export function AnswerChart({
  spec,
  evidence,
  language,
}: {
  spec: ChartSpec;
  evidence: Evidence[];
  language: "ru" | "uz";
}) {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "");
  const result = evidence.find((e) => e.sql_id === spec.sql_id);
  if (!result) return null;
  const keyed: Keyed[] = spec.series.map((s, i) => ({
    ...s,
    key: `s${i}`,
    color: COLORS[i % COLORS.length],
  }));
  const xi = result.columns.indexOf(spec.x);
  const rows: Row[] = result.rows.map((r) => {
    const row: Row = { x: String(r[xi]) };
    for (const s of keyed)
      row[s.key] = r[result.columns.indexOf(s.column)] as number;
    return row;
  });
  // Panels: one panel per unit; other types: one panel with all series.
  const groups =
    spec.type === "panels"
      ? Object.values(
          Object.groupBy(keyed, (s) => s.unit) as Record<string, Keyed[]>,
        )
      : [keyed];
  return (
    <figure className="answer-chart">
      <figcaption>
        <span>{spec.title}</span>
        <DownloadButton spec={spec} evidence={result} language={language} />
      </figcaption>
      {groups.map((series) => (
        <Panel
          key={series.map((s) => s.key).join("-")}
          uid={uid}
          type={spec.type}
          series={series}
          rows={rows}
          compact={COMPACT[language]}
        />
      ))}
    </figure>
  );
}

function Panel({
  uid,
  type,
  series,
  rows,
  compact,
}: {
  uid: string;
  type: ChartSpec["type"];
  series: Keyed[];
  rows: Row[];
  compact: Intl.NumberFormat;
}) {
  const config: ChartConfig = Object.fromEntries(
    series.map((s) => [s.key, { label: s.label, color: s.color }]),
  );
  const horizontal = type === "hbar";
  const longest = Math.max(...rows.map((r) => String(r.x).length));
  // Each category keeps its own room; a wide chart scrolls horizontally instead of dropping labels.
  const minWidth =
    type === "line" || horizontal
      ? 0
      : rows.length * Math.max(series.length * 26 + 44, CATEGORY_MIN);
  const tickLines = longest > TICK_LINE ? 2 : 1;
  const height = horizontal
    ? Math.max(160, rows.length * (series.length * 14 + 20) + 40)
    : 260 + (tickLines - 1) * 16;
  const gradient = (s: Keyed) => `${uid}-${s.key}`;
  const defs = (
    <defs>
      {series.map((s) => (
        <linearGradient
          key={s.key}
          id={gradient(s)}
          x1="0"
          y1="0"
          x2={horizontal ? "1" : "0"}
          y2={horizontal ? "0" : "1"}
        >
          <stop
            offset="0%"
            stopColor={s.color}
            stopOpacity={horizontal ? 0.55 : 0.95}
          />
          <stop
            offset="100%"
            stopColor={s.color}
            stopOpacity={horizontal ? 0.95 : 0.25}
          />
        </linearGradient>
      ))}
    </defs>
  );
  const tooltip = (
    <ChartTooltip
      cursor={{ fill: "rgba(255,255,255,0.04)" }}
      content={<ChartTooltipContent indicator="dot" className="min-w-52" />}
    />
  );
  const axisTick = { fill: "#8a93a8", fontSize: 12 };
  const valueAxis = {
    tickFormatter: (v: number) => compact.format(v),
    tick: axisTick,
    axisLine: false,
    tickLine: false,
  };
  // All series in a panel share one unit (validated on the server); show it once.
  const unit = series[0].unit;

  return (
    <div className="chart-panel">
      <div className="chart-unit">{unit}</div>
      <div className="chart-scroll">
        <ChartContainer
          config={config}
          className="chart-box"
          style={{
            height,
            width: minWidth ? `max(100%, ${minWidth}px)` : "100%",
            aspectRatio: "auto",
          }}
        >
          {type === "line" ? (
            <AreaChart data={rows} margin={{ left: 0, right: 8, top: 8 }}>
              {defs}
              <CartesianGrid vertical={false} stroke="#22252f" />
              <XAxis
                dataKey="x"
                tick={axisTick}
                tickLine={false}
                axisLine={false}
                minTickGap={16}
              />
              <YAxis {...valueAxis} width={68} />
              {tooltip}
              {series.map((s) => (
                <Area
                  key={s.key}
                  dataKey={s.key}
                  type="monotone"
                  stroke={s.color}
                  strokeWidth={2.5}
                  fill={`url(#${gradient(s)})`}
                  dot={{ r: 3, strokeWidth: 0, fill: s.color }}
                  activeDot={{ r: 5 }}
                />
              ))}
            </AreaChart>
          ) : (
            <BarChart
              data={rows}
              layout={horizontal ? "vertical" : "horizontal"}
              margin={{ left: 0, right: 12, top: 4 }}
              barCategoryGap={horizontal ? "24%" : "22%"}
              barGap={2}
            >
              {defs}
              <CartesianGrid
                vertical={horizontal}
                horizontal={!horizontal}
                stroke="#22252f"
              />
              {horizontal ? (
                <>
                  <XAxis type="number" {...valueAxis} />
                  <YAxis
                    type="category"
                    dataKey="x"
                    tick={axisTick}
                    tickLine={false}
                    axisLine={false}
                    interval={0}
                    width={Math.min(190, Math.max(80, longest * 7))}
                  />
                </>
              ) : (
                <>
                  <XAxis
                    dataKey="x"
                    tick={<WrappedTick />}
                    tickLine={false}
                    axisLine={false}
                    interval={0}
                    height={22 + tickLines * 14}
                  />
                  <YAxis {...valueAxis} width={68} />
                </>
              )}
              {tooltip}
              {series.map((s) => (
                <Bar
                  key={s.key}
                  dataKey={s.key}
                  fill={`url(#${gradient(s)})`}
                  radius={horizontal ? [0, 6, 6, 0] : [6, 6, 0, 0]}
                  maxBarSize={horizontal ? 16 : 48}
                />
              ))}
            </BarChart>
          )}
        </ChartContainer>
      </div>
      {series.length > 1 && (
        <ul className="chart-legend">
          {series.map((s) => (
            <li key={s.key}>
              <span className="chart-swatch" style={{ background: s.color }} />
              {s.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
