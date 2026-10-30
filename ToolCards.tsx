import { useState } from "react";
import type { ToolCard } from "../types";

interface Option {
  id: string;
  agent: string;
  guidance: string;
  status_label: string;
  eligibility: string;
  unmet: string[];
  missing: string[];
  line: string;
}

const ELIGIBILITY_LABEL: Record<string, string> = {
  meets_criteria: "Meets recorded criteria",
  unknown: "Information missing",
  does_not_meet: "Does not meet criteria",
  not_applicable: "Not applicable",
};

function TherapyTable({ options }: { options: Option[] }) {
  return (
    <table className="options">
      <thead>
        <tr>
          <th>Option</th>
          <th>Guidance</th>
          <th>NICE status</th>
          <th>This eye</th>
        </tr>
      </thead>
      <tbody>
        {options.map((o) => (
          <tr key={o.id} className={`eligibility eligibility--${o.eligibility}`}>
            <td>
              {o.agent}
              <small>{o.line} line</small>
            </td>
            <td>{o.guidance}</td>
            <td>{o.status_label}</td>
            <td>
              {ELIGIBILITY_LABEL[o.eligibility] ?? o.eligibility}
              {[...o.unmet, ...o.missing].length > 0 && <small>{[...o.unmet, ...o.missing].join("; ")}</small>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Card({ card }: { card: ToolCard }) {
  const [open, setOpen] = useState(false);
  const options = (card.details.options as Option[] | undefined) ?? [];
  return (
    <article className="tool">
      <header className="tool__header">
        <h3>
          {card.title}
          {card.eye && <span className={`eye eye--${card.eye}`}>{card.eye} eye</span>}
        </h3>
        <span className="tool__verified" title={card.provenance}>
          Verified tool
        </span>
      </header>
      <p className="tool__summary">{card.summary}</p>
      {card.tool === "therapy_options" && options.length > 0 && <TherapyTable options={options} />}
      {card.findings
        .filter((f) => f.severity !== "info")
        .map((f, i) => (
          <p key={i} className={`finding finding--${f.severity}`}>
            <strong>{f.severity}</strong> {f.message}
            {f.reference && <em> {f.reference}</em>}
          </p>
        ))}
      {card.missing.length > 0 && <p className="tool__missing">Missing: {card.missing.join(", ")}</p>}
      <button type="button" className="link" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? "Hide working" : "Show working"}
      </button>
      {open && (
        <div className="tool__working">
          <ol>
            {card.working.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ol>
          {card.findings
            .filter((f) => f.severity === "info")
            .map((f, i) => (
              <p key={i} className="finding finding--info">
                {f.message}
              </p>
            ))}
          <p className="tool__provenance">Rules: {card.provenance}</p>
        </div>
      )}
    </article>
  );
}

export function ToolCards({ cards }: { cards: ToolCard[] }) {
  if (cards.length === 0) return null;
  return (
    <section className="tools" aria-label="Deterministic tool results">
      {cards.map((card, i) => (
        <Card key={`${card.tool}-${card.eye}-${i}`} card={card} />
      ))}
    </section>
  );
}
