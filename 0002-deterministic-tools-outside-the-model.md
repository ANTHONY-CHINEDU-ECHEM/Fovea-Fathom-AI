# 0002. Deterministic tools outside the model

Status: accepted

## Context

Language models produce plausible numbers. In eye care a plausible interval, lens power or acuity conversion can harm.

## Decision

Compute every safety critical quantity in versioned Python tools driven by reviewed YAML rules. Stream results as separate cards, label them by eye, and never put them in the prompt.

## Consequences

The figure check stays honest because any number in the answer must come from a cited source. Tools need unit tests and clinical review like any other clinical rule.
