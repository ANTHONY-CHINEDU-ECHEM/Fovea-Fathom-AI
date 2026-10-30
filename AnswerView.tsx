import type { FinalEvent, Source } from "../types";

function renderWithCitations(text: string, sources: Source[], onCite: (n: number) => void) {
  const parts = text.split(/(\[\d+\]|\[figure not found in the cited source\])/g);
  return parts.map((part, i) => {
    const cite = part.match(/^\[(\d+)\]$/);
    if (cite) {
      const n = Number(cite[1]);
      const source = sources.find((s) => s.number === n);
      return (
        <button key={i} type="button" className="cite" onClick={() => onCite(n)} title={source?.title}>
          {n}
        </button>
      );
    }
    if (part === "[figure not found in the cited source]") {
      return (
        <mark key={i} className="unverified">
          figure not found in the cited source
        </mark>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

interface Props {
  text: string;
  final: FinalEvent | null;
  sources: Source[];
  streaming: boolean;
  onCite: (n: number) => void;
}

export function AnswerView({ text, final, sources, streaming, onCite }: Props) {
  if (!text && !streaming) return null;
  const body = final?.answer ?? text;
  const g = final?.grounding;
  return (
    <section className="answer" aria-live="polite">
      {final?.status === "abstained" && <p className="answer__status answer__status--abstained">Abstained: evidence insufficient</p>}
      {final?.status === "out_of_scope" && <p className="answer__status">Outside eye care scope</p>}
      <div className="answer__body">
        {body.split(/\n{2,}/).map((para, i) => (
          <p key={i} className={para.startsWith("Clinical judgement:") ? "answer__judgement" : undefined}>
            {renderWithCitations(para, sources, onCite)}
          </p>
        ))}
        {streaming && <span className="caret" aria-hidden="true" />}
      </div>
      {final?.laterality && !final.laterality.consistent && (
        <p className="finding finding--major">
          <strong>Laterality</strong> {final.laterality.issues.join(" ")}
        </p>
      )}
      {g && (
        <dl className="grounding">
          <div>
            <dt>Grounded</dt>
            <dd className={g.grounded ? "ok" : "warn"}>{g.grounded ? "Yes" : "Review"}</dd>
          </div>
          <div>
            <dt>Citation coverage</dt>
            <dd>{Math.round(g.citation_coverage * 100)}%</dd>
          </div>
          <div>
            <dt>Claim support</dt>
            <dd>{Math.round(g.claim_support * 100)}%</dd>
          </div>
          <div>
            <dt>Unverified figures</dt>
            <dd className={g.unsupported_figures.length ? "warn" : "ok"}>{g.unsupported_figures.length}</dd>
          </div>
          <div>
            <dt>Model</dt>
            <dd>
              {final?.provider}
              {final && final.fallbacks.length > 0 && ` (after ${final.fallbacks.join(", ")})`}
            </dd>
          </div>
          <div>
            <dt>Latency</dt>
            <dd>{final ? `${Math.round(final.latency_ms)} ms` : ""}</dd>
          </div>
        </dl>
      )}
    </section>
  );
}
