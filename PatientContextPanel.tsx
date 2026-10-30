import type { EyeContext, PatientContext, Side } from "../types";

interface Props {
  value: PatientContext;
  onChange: (next: PatientContext) => void;
}

const LIST_FIELDS: Array<keyof Pick<PatientContext, "conditions" | "medicines" | "allergies">> = ["conditions", "medicines", "allergies"];

function numberOrUndefined(raw: string): number | undefined {
  const n = Number(raw);
  return raw.trim() === "" || Number.isNaN(n) ? undefined : n;
}

function EyeFields({ side, eye, onChange }: { side: Side; eye: EyeContext; onChange: (e: EyeContext) => void }) {
  const set = (patch: Partial<EyeContext>) => onChange({ ...eye, ...patch });
  return (
    <fieldset className={`eyebox eyebox--${side}`}>
      <legend>{side === "right" ? "Right eye" : "Left eye"}</legend>
      <label>
        Diagnosis
        <input value={eye.diagnosis ?? ""} placeholder="e.g. wet AMD" onChange={(e) => set({ diagnosis: e.target.value || undefined })} />
      </label>
      <label>
        Best corrected acuity
        <input value={eye.bcva ?? ""} placeholder="6/18, 70 letters, logMAR 0.48" onChange={(e) => set({ bcva: e.target.value || undefined })} />
      </label>
      <label>
        Lens
        <select value={eye.lens_status ?? "unknown"} onChange={(e) => set({ lens_status: e.target.value as EyeContext["lens_status"] })}>
          <option value="unknown">Unknown</option>
          <option value="phakic">Phakic</option>
          <option value="pseudophakic">Pseudophakic</option>
          <option value="aphakic">Aphakic</option>
        </select>
      </label>
      <label>
        IOP (mmHg)
        <input inputMode="decimal" value={eye.iop_mmhg ?? ""} onChange={(e) => set({ iop_mmhg: numberOrUndefined(e.target.value) })} />
      </label>
      <label>
        Central subfield thickness (µm)
        <input
          inputMode="numeric"
          value={eye.central_subfield_thickness_um ?? ""}
          onChange={(e) => set({ central_subfield_thickness_um: numberOrUndefined(e.target.value) })}
        />
      </label>
      <label>
        Current agent
        <input value={eye.current_agent ?? ""} placeholder="aflibercept" onChange={(e) => set({ current_agent: e.target.value || undefined })} />
      </label>
      <label>
        Interval (weeks)
        <input
          inputMode="numeric"
          value={eye.current_interval_weeks ?? ""}
          onChange={(e) => set({ current_interval_weeks: numberOrUndefined(e.target.value) })}
        />
      </label>
      <label>
        Injections given
        <input inputMode="numeric" value={eye.injections_given ?? ""} onChange={(e) => set({ injections_given: numberOrUndefined(e.target.value) })} />
      </label>
      <div className="checks">
        <label>
          <input type="checkbox" checked={!!eye.intraretinal_fluid} onChange={(e) => set({ intraretinal_fluid: e.target.checked })} /> Intraretinal fluid
        </label>
        <label>
          <input type="checkbox" checked={!!eye.subretinal_fluid} onChange={(e) => set({ subretinal_fluid: e.target.checked })} /> Subretinal fluid
        </label>
      </div>
    </fieldset>
  );
}

export function PatientContextPanel({ value, onChange }: Props) {
  return (
    <details className="context">
      <summary>De identified patient context (optional)</summary>
      <p className="context__note">Do not enter names, NHS numbers or dates of birth. Identifiers are redacted server side, but avoid entering them.</p>
      <div className="context__grid">
        <label>
          Age
          <input inputMode="numeric" value={value.age ?? ""} onChange={(e) => onChange({ ...value, age: numberOrUndefined(e.target.value) })} />
        </label>
        <label>
          Weight (kg)
          <input inputMode="decimal" value={value.weight_kg ?? ""} onChange={(e) => onChange({ ...value, weight_kg: numberOrUndefined(e.target.value) })} />
        </label>
        <label>
          eGFR
          <input inputMode="numeric" value={value.egfr ?? ""} onChange={(e) => onChange({ ...value, egfr: numberOrUndefined(e.target.value) })} />
        </label>
        {LIST_FIELDS.map((field) => (
          <label key={field}>
            {field[0].toUpperCase() + field.slice(1)} (comma separated)
            <input
              value={value[field].join(", ")}
              onChange={(e) => onChange({ ...value, [field]: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })}
            />
          </label>
        ))}
      </div>
      <div className="context__eyes">
        <EyeFields side="right" eye={value.right ?? {}} onChange={(right) => onChange({ ...value, right })} />
        <EyeFields side="left" eye={value.left ?? {}} onChange={(left) => onChange({ ...value, left })} />
      </div>
    </details>
  );
}
