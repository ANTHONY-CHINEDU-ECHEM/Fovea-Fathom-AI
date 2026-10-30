import { useState } from "react";
import { sendFeedback } from "../api";

const REASONS = [
  ["accurate", "Accurate"],
  ["helpful", "Helpful"],
  ["incorrect", "Incorrect"],
  ["outdated", "Outdated"],
  ["unsafe", "Unsafe"],
  ["wrong_eye", "Wrong eye"],
  ["missing_evidence", "Missing evidence"],
  ["unclear", "Unclear"],
] as const;

export function Feedback({ requestId }: { requestId: string }) {
  const [rating, setRating] = useState<1 | -1 | null>(null);
  const [reasons, setReasons] = useState<string[]>([]);
  const [comment, setComment] = useState("");
  const [sent, setSent] = useState(false);

  if (sent) return <p className="feedback feedback--sent">Thank you. Feedback is reviewed by the clinical safety officer.</p>;
  return (
    <form
      className="feedback"
      onSubmit={async (e) => {
        e.preventDefault();
        if (rating === null) return;
        await sendFeedback(requestId, rating, reasons, comment);
        setSent(true);
      }}
    >
      <span>Was this answer safe and useful?</span>
      <button type="button" aria-pressed={rating === 1} onClick={() => setRating(1)}>
        Yes
      </button>
      <button type="button" aria-pressed={rating === -1} onClick={() => setRating(-1)}>
        No
      </button>
      {rating !== null && (
        <>
          <div className="feedback__reasons">
            {REASONS.map(([value, label]) => (
              <label key={value}>
                <input
                  type="checkbox"
                  checked={reasons.includes(value)}
                  onChange={(e) => setReasons(e.target.checked ? [...reasons, value] : reasons.filter((r) => r !== value))}
                />
                {label}
              </label>
            ))}
          </div>
          <textarea value={comment} maxLength={2000} placeholder="Comment (identifiers are redacted)" onChange={(e) => setComment(e.target.value)} />
          <button type="submit">Send feedback</button>
        </>
      )}
    </form>
  );
}
