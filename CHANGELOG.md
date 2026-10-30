# Changelog

All notable changes are recorded here. Versions follow semantic versioning.

## 1.0.0 (30 October 2026)

### Added
* Six layer architecture: real knowledge sources, polite ingestion, hybrid index, question answering, deterministic ophthalmic tools, governance and operations.
* Verified seed snapshot of 54 records covering NG82, NG81, NG77, 25 technology appraisal records, NHS diabetic eye screening criteria and pathways, Royal College hydroxychloroquine monitoring, 13 pivotal trials, 4 registry records and 6 label safety summaries.
* Deterministic tools: acuity conversion, SRK/T lens power with SRK II check, diabetic retinopathy grading, treat and extend planning, NICE therapy matching per eye, NG81 threshold, target pressure, visual field progression, hydroxychloroquine monitoring, safety screen and trial prefilter.
* Guardrails: redaction with NHS number check digit, eleven eye emergency rules with negation awareness, scope check and prompt injection filter.
* Validators: citation coverage, figure check, claim support and the laterality guard.
* Provider neutral router for Claude, OpenAI and Ollama with circuit breakers and an extractive fallback.
* FastAPI service with streaming, React interface, standalone browser demo, Docker stack with Qdrant, Redis, Prometheus alert rules and a provisioned Grafana dashboard.
* 53 question golden set, continuous integration gate and 163 tests.

### Fixed during development
* Deduplication no longer removes registry records that share an NCT number with a trial publication (decision record 0007).
