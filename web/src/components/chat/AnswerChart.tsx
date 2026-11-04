"use client";
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
import type { ChartSeries, ChartSpec, Evidence } from "@/lib/api";

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

type Row = Record<string, string | number>;

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
  const result = evidence.find((e) => e.sql_id === spec.sql_id);
  if (!result) return null;
  const rows: Row[] = result.rows.map((r) =>
    Object.fromEntries(
      result.columns.map((c, i) => [c, r[i] as string | number]),
    ),
  );
  const groups =
    spec.type === "panels"
      ? Object.values(
          Object.groupBy(spec.series, (s) => s.unit) as Record<
            string,
            ChartSeries[]
          >,
        )
      : [spec.series];
  return (
    <figure className="answer-chart">
      <figcaption>{spec.title}</figcaption>
      {groups.map((series) => (
        <Panel
          key={series.map((s) => s.column).join("|")}
          spec={spec}
          series={series}
          rows={rows}
          showUnit={spec.type === "panels"}
          compact={COMPACT[language]}
        />
      ))}
    </figure>
  );
}

function Panel({
  spec,
  series,
  rows,
  showUnit,
  compact,
}: {
  spec: ChartSpec;
  series: ChartSeries[];
  rows: Row[];
  showUnit: boolean;
  compact: Intl.NumberFormat;
}) {
  const config: ChartConfig = Object.fromEntries(
    series.map((s, i) => [
      s.column,
      { label: `${s.label}, ${s.unit}`, color: COLORS[i % COLORS.length] },
    ]),
  );
  const horizontal = spec.type === "hbar";
  const height = horizontal ? Math.max(180, rows.length * 34 + 40) : 260;
  const tooltip = (
    <ChartTooltip
      cursor={{ fill: "rgba(255,255,255,0.04)" }}
      content={<ChartTooltipContent indicator="dot" />}
    />
  );
  const defs = (
    <defs>
      {series.map((s) => (
        <linearGradient
          key={s.column}
          id={`g-${spec.id}-${s.column}`}
          x1="0"
          y1="0"
          x2={horizontal ? "1" : "0"}
          y2={horizontal ? "0" : "1"}
        >
          <stop
            offset="0%"
            stopColor={`var(--color-${s.column})`}
            stopOpacity={0.95}
          />
          <stop
            offset="100%"
            stopColor={`var(--color-${s.column})`}
            stopOpacity={horizontal ? 0.55 : 0.25}
          />
        </linearGradient>
      ))}
    </defs>
  );
  const axisTick = { fill: "#8a93a8", fontSize: 12 };
  const valueAxis = {
    tickFormatter: (v: number) => compact.format(v),
    tick: axisTick,
    axisLine: false,
    tickLine: false,
    width: 68,
  };

  return (
    <div className="chart-panel">
      {showUnit && <div className="chart-unit">{series[0].unit}</div>}
      <ChartContainer
        config={config}
        className="chart-box"
        style={{ height, aspectRatio: "auto" }}
      >
        {spec.type === "line" ? (
          <AreaChart data={rows} margin={{ left: 0, right: 8, top: 8 }}>
            {defs}
            <CartesianGrid vertical={false} stroke="#22252f" />
            <XAxis
              dataKey={spec.x}
              tick={axisTick}
              tickLine={false}
              axisLine={false}
              minTickGap={16}
            />
            <YAxis {...valueAxis} />
            {tooltip}
            {series.map((s) => (
              <Area
                key={s.column}
                dataKey={s.column}
                type="monotone"
                stroke={`var(--color-${s.column})`}
                strokeWidth={2.5}
                fill={`url(#g-${spec.id}-${s.column})`}
                dot={{ r: 3, strokeWidth: 0, fill: `var(--color-${s.column})` }}
                activeDot={{ r: 5 }}
              />
            ))}
          </AreaChart>
        ) : (
          <BarChart
            data={rows}
            layout={horizontal ? "vertical" : "horizontal"}
            margin={{ left: 0, right: 8, top: 8 }}
            barCategoryGap="22%"
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
                  dataKey={spec.x}
                  tick={axisTick}
                  tickLine={false}
                  axisLine={false}
                  width={150}
                />
              </>
            ) : (
              <>
                <XAxis
                  dataKey={spec.x}
                  tick={axisTick}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={8}
                />
                <YAxis {...valueAxis} />
              </>
            )}
            {tooltip}
            {/* Legend rendered below from the series config: Recharts' legend reads the gradient fill, not a colour. */}
            {series.map((s) => (
              <Bar
                key={s.column}
                dataKey={s.column}
                fill={`url(#g-${spec.id}-${s.column})`}
                radius={horizontal ? [0, 6, 6, 0] : [6, 6, 0, 0]}
                maxBarSize={48}
              />
            ))}
          </BarChart>
        )}
      </ChartContainer>
      {series.length > 1 && (
        <ul className="chart-legend">
          {series.map((s, i) => (
            <li key={s.column}>
              <span
                className="chart-swatch"
                style={{ background: COLORS[i % COLORS.length] }}
              />
              {s.label}, {s.unit}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
