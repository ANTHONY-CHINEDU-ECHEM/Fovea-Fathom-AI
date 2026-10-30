import type { EmergencyAlert } from "../types";

export function EmergencyBanner({ alerts }: { alerts: EmergencyAlert[] }) {
  if (alerts.length === 0) return null;
  return (
    <section className="emergency" role="alert" aria-live="assertive">
      {alerts.map((alert) => (
        <article key={alert.id} className="emergency__item">
          <header>
            <span className="emergency__badge">{alert.urgency.replace(/_/g, " ")}</span>
            <h2>{alert.name}</h2>
          </header>
          <p>{alert.action}</p>
          <p className="emergency__guidance">{alert.guidance}</p>
        </article>
      ))}
    </section>
  );
}
