# 0005. Condition scoped chunks

Status: accepted

## Context

Reviews and guidelines discuss several conditions; document level tags let DMO evidence leak into AMD answers.

## Decision

Tag conditions and medicines per chunk with negation awareness, fall back to document tags only when a chunk names none, and penalise condition conflicts at ranking and generation.

## Consequences

Answers stay within the question's condition. Tagging depends on the lexicon, which is versioned.
