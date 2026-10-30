export type Severity = "info" | "monitor" | "caution" | "major" | "contraindication";
export type Side = "right" | "left";

export interface Finding {
  severity: Severity;
  message: string;
  reference: string;
}

export interface ToolCard {
  tool: string;
  title: string;
  summary: string;
  eye: Side | null;
  details: Record<string, unknown>;
  working: string[];
  findings: Finding[];
  references: string[];
  provenance: string;
  missing: string[];
}

export interface EmergencyAlert {
  id: string;
  name: string;
  urgency: string;
  action: string;
  guidance: string;
  matched: string;
}

export interface Source {
  number: number;
  doc_id: string;
  title: string;
  section: string;
  url: string;
  source_label: string;
  grade: number;
  grade_label: string;
  year: number | null;
  jurisdiction: string;
  superseded_by: string | null;
  score: number;
  reasons: string[];
  excerpt: string;
}

export interface Grounding {
  citation_coverage: number;
  invalid_citations: number[];
  unsupported_figures: string[];
  claim_support: number;
  claims: number;
  unsupported_claims: string[];
  cited_sources: number[];
  grounded: boolean;
}

export interface FinalEvent {
  request_id: string;
  status: "answered" | "abstained" | "out_of_scope";
  answer: string;
  grounding: Grounding | null;
  laterality: { requested: string[]; mentioned: string[]; consistent: boolean; issues: string[] } | null;
  answerability: { best_score: number; query_coverage: number; reason: string } | null;
  provider: string | null;
  model: string | null;
  fallbacks: string[];
  latency_ms: number;
  superseded_cited: string[];
}

export interface EyeContext {
  diagnosis?: string;
  bcva?: string;
  lens_status?: "phakic" | "pseudophakic" | "aphakic" | "unknown";
  iop_mmhg?: number;
  central_subfield_thickness_um?: number;
  intraretinal_fluid?: boolean;
  subretinal_fluid?: boolean;
  current_agent?: string;
  current_interval_weeks?: number;
  injections_given?: number;
}

export interface PatientContext {
  age?: number;
  weight_kg?: number;
  egfr?: number;
  conditions: string[];
  medicines: string[];
  allergies: string[];
  right?: EyeContext;
  left?: EyeContext;
}

export type Provider = "anthropic" | "openai" | "ollama" | "extractive";
