import type { Source } from "../types";

interface Props {
  sources: Source[];
  cited: number[];
  highlighted: number | null;
}

export function EvidenceTray({ sources, cited, highlighted }: Props) {
  if (sources.length === 0) return null;
  return (
    <aside className="evidence" aria-label="Numbered sources">
      <h2>Sources</h2>
      <ol>
        {sources.map((s) => (
          <li
            key={s.number}
            id={`source-${s.number}`}
            className={[
              "source",
              cited.includes(s.number) ? "source--cited" : "",
              highlighted === s.number ? "source--highlight" : "",
              s.superseded_by ? "source--superseded" : "",
            ].join(" ")}
          >
            <header>
              <span className="source__number">{s.number}</span>
              <a href={s.url} target="_blank" rel="noreferrer noopener">
                {s.title}
              </a>
            </header>
            <p className="source__meta">
              {s.source_label} · {s.year ?? "undated"} · {s.jurisdiction} · grade {s.grade} ({s.grade_label})
            </p>
            {s.superseded_by && <p className="source__superseded">Superseded by {s.superseded_by}</p>}
            <p className="source__excerpt">{s.excerpt}</p>
            <p className="source__why">{s.reasons.join(" · ")}</p>
          </li>
        ))}
      </ol>
    </aside>
  );
}
