# 0006. Extractive generator as final fallback

Status: accepted

## Context

A vendor outage during clinic must not leave clinicians without an answer, and an offline evaluation needs a deterministic generator.

## Decision

End every provider chain with an extractive generator that copies cited sentences, anchored on the question's rarest terms and filtered by condition.

## Consequences

The system always answers or abstains. Extractive answers are less fluent than model answers.
