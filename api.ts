import type { EmergencyAlert, FinalEvent, PatientContext, Provider, Source, ToolCard } from "./types";

const API_KEY = import.meta.env.VITE_API_KEY as string | undefined;

function headers(): HeadersInit {
  return { "Content-Type": "application/json", ...(API_KEY ? { "X-API-Key": API_KEY } : {}) };
}

export interface StreamHandlers {
  onMeta?: (data: Record<string, unknown>) => void;
  onEmergency?: (alerts: EmergencyAlert[]) => void;
  onTools?: (cards: ToolCard[]) => void;
  onSources?: (sources: Source[]) => void;
  onToken?: (text: string) => void;
  onFinal?: (final: FinalEvent) => void;
  onError?: (message: string) => void;
}

/** Ask a question and dispatch server sent events in the order the pipeline emits them. */
export async function askStream(
  question: string,
  context: PatientContext,
  provider: Provider | undefined,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch("/v1/ask/stream", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ question, context, provider }),
    signal,
  });
  if (!response.ok || !response.body) {
    handlers.onError?.(`Request failed with status ${response.status}`);
    return;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      dispatch(block, handlers);
      boundary = buffer.indexOf("\n\n");
    }
  }
}

function dispatch(block: string, h: StreamHandlers): void {
  let type = "message";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event: ")) type = line.slice(7).trim();
    else if (line.startsWith("data: ")) data += line.slice(6);
  }
  if (!data) return;
  const payload = JSON.parse(data);
  switch (type) {
    case "meta":
      h.onMeta?.(payload);
      break;
    case "emergency":
      h.onEmergency?.(payload.alerts);
      break;
    case "tools":
      h.onTools?.(payload.cards);
      break;
    case "sources":
      h.onSources?.(payload.sources);
      break;
    case "token":
      h.onToken?.(payload.text);
      break;
    case "final":
      h.onFinal?.(payload);
      break;
  }
}

export async function sendFeedback(requestId: string, rating: 1 | -1, reasons: string[], comment: string): Promise<void> {
  await fetch("/v1/feedback", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ request_id: requestId, rating, reasons, comment: comment || null }),
  });
}

export async function runTool(path: string, body: unknown): Promise<ToolCard | { cards: ToolCard[] } | { detail: string }> {
  const response = await fetch(`/v1/tools/${path}`, { method: "POST", headers: headers(), body: JSON.stringify(body) });
  return response.json();
}
