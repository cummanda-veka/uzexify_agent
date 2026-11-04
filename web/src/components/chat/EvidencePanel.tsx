"use client";
import { ChevronDown, Copy } from "lucide-react";
import { useState } from "react";
import type { AskResponse } from "@/lib/api";
import { copy, type Locale } from "@/lib/i18n";
export function EvidencePanel({
  answer,
  locale,
  open,
  onToggle,
}: {
  answer: AskResponse;
  locale: Locale;
  open: boolean;
  onToggle: () => void;
}) {
  const t = copy[locale];
  const [copied, setCopied] = useState<string | null>(null);
  if (!answer.evidence.length && !answer.entities.length) return null;
  return (
    <section className="evidence">
      <button
        type="button"
        className="evidence-toggle"
        onClick={onToggle}
        aria-expanded={open}
      >
        <span>{t.evidence}</span>
        <ChevronDown size={17} className={open ? "chevron open" : "chevron"} />
      </button>
      {open && (
        <div className="evidence-body">
          {answer.entities.length > 0 && (
            <div className="entities">
              <div className="evidence-label">{t.entities}</div>
              {answer.entities.map((entity, i) => (
                <div key={`${entity.kind}-${entity.query}-${i}`}>
                  <strong>{entity.query}</strong>:{" "}
                  {entity.matches
                    .slice(0, 5)
                    .map((match) =>
                      match.id === match.label
                        ? match.label
                        : `${match.label} (${match.id})`,
                    )
                    .join(" · ") || "—"}
                  {entity.matches.length > 5 &&
                    ` · +${entity.matches.length - 5}`}
                </div>
              ))}
            </div>
          )}
          {answer.evidence.map((item) => (
            <div className="query" key={item.sql_id}>
              <div className="query-header">
                <div>
                  <span className="sql-id">{item.sql_id}</span> {item.purpose}
                </div>
                <button
                  type="button"
                  onClick={() => {
                    void navigator.clipboard
                      .writeText(item.sql)
                      .then(() => setCopied(item.sql_id));
                  }}
                >
                  <Copy size={14} />{" "}
                  {copied === item.sql_id ? t.copied : t.copy}
                </button>
              </div>
              <pre>{item.sql}</pre>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      {item.columns.map((column) => (
                        <th key={column}>{column}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {item.rows.slice(0, 20).map((row) => (
                      <tr key={JSON.stringify(row)}>
                        {row.map((cell, j) => (
                          <td key={item.columns[j]}>
                            {cell == null
                              ? "—"
                              : typeof cell === "object"
                                ? JSON.stringify(cell)
                                : String(cell)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="result-caption">
                {item.row_count} {t.rows}
                {item.rows.length > 20 ? ` · ${t.results}` : ""}
                {item.truncated ? ` · ${t.truncated}` : ""}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
