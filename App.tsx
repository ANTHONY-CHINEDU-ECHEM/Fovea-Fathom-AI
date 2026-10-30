import { useRef, useState } from "react";
import { askStream } from "./api";
import { AnswerView } from "./components/AnswerView";
import { EmergencyBanner } from "./components/EmergencyBanner";
import { EvidenceTray } from "./components/EvidenceTray";
import { Feedback } from "./components/Feedback";
import { PatientContextPanel } from "./components/PatientContextPanel";
import { ToolCards } from "./components/ToolCards";
import type { EmergencyAlert, FinalEvent, PatientContext, Provider, Source, ToolCard } from "./types";

const EXAMPLES = [
  "Is faricimab recommended for diabetic macular oedema, and what thickness criterion applies?",
  "Right eye wet AMD on aflibercept, 6 injections, interval 10 weeks, subretinal fluid today. Next interval?",
  "OHT with IOP 27 mmHg and CCT 530. Should we offer SLT first?",
  "Patient on hydroxychloroquine 400 mg daily for 3 years, weight 62 kg. When should monitoring start?",
  "Two days after an intravitreal injection the eye is painful with reduced vision",
];

const EMPTY_CONTEXT: PatientContext = { conditions: [], medicines: [], allergies: [] };

export default function App() {
  const [question, setQuestion] = useState("");
  const [context, setContext] = useState<PatientContext>(EMPTY_CONTEXT);
  const [provider, setProvider] = useState<Provider | "">("");
  const [alerts, setAlerts] = useState<EmergencyAlert[]>([]);
  const [cards, setCards] = useState<ToolCard[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [text, setText] = useState("");
  const [final, setFinal] = useState<FinalEvent | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [highlighted, setHighlighted] = useState<number | null>(null);
  const abort = useRef<AbortController | null>(null);

  async function submit(q: string) {
    if (q.trim().length < 3) return;
    abort.current?.abort();
    abort.current = new AbortController();
    setAlerts([]);
    setCards([]);
    setSources([]);
    setText("");
    setFinal(null);
    setError(null);
    setStreaming(true);
    try {
      await askStream(
        q,
        context,
        provider || undefined,
        {
          onEmergency: setAlerts,
          onTools: setCards,
          onSources: setSources,
          onToken: (t) => setText((prev) => prev + t),
          onFinal: setFinal,
          onError: setError,
        },
        abort.current.signal,
      );
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError((e as Error).message);
    } finally {
      setStreaming(false);
    }
  }

  function cite(n: number) {
    setHighlighted(n);
    document.getElementById(`source-${n}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  return (
    <div className="shell">
      <header className="masthead">
        <div className="brand">
          <span className="brand__mark" aria-hidden="true" />
          <div>
            <h1>Fovea Fathom AI</h1>
            <p>Evidence grounded decision support for NHS eye treatment</p>
          </div>
        </div>
        <p className="masthead__notice">For registered eye care professionals. Not a medical device. Confirm against NICE, the SmPC and local protocols.</p>
      </header>

      <main className="layout">
        <section className="workspace">
          <form
            className="ask"
            onSubmit={(e) => {
              e.preventDefault();
              void submit(question);
            }}
          >
            <label htmlFor="question" className="visually-hidden">
              Clinical question
            </label>
            <textarea
              id="question"
              value={question}
              rows={3}
              placeholder="Ask a clinical question about eye treatment. State which eye."
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void submit(question);
              }}
            />
            <div className="ask__row">
              <select value={provider} onChange={(e) => setProvider(e.target.value as Provider | "")} aria-label="Model">
                <option value="">Deployment default model</option>
                <option value="anthropic">Claude</option>
                <option value="openai">OpenAI</option>
                <option value="ollama">Local (Ollama)</option>
                <option value="extractive">Extractive only</option>
              </select>
              <button type="submit" disabled={streaming}>
                {streaming ? "Answering" : "Ask"}
              </button>
            </div>
            <div className="examples">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  type="button"
                  className="chip"
                  onClick={() => {
                    setQuestion(ex);
                    void submit(ex);
                  }}
                >
                  {ex}
                </button>
              ))}
            </div>
            <PatientContextPanel value={context} onChange={setContext} />
          </form>

          {error && <p className="finding finding--major">{error}</p>}
          <EmergencyBanner alerts={alerts} />
          <ToolCards cards={cards} />
          <AnswerView text={text} final={final} sources={sources} streaming={streaming} onCite={cite} />
          {final && final.status === "answered" && <Feedback requestId={final.request_id} />}
        </section>
        <EvidenceTray sources={sources} cited={final?.grounding?.cited_sources ?? []} highlighted={highlighted} />
      </main>
    </div>
  );
}
