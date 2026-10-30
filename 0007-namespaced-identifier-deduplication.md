# 0007. Namespaced identifier deduplication

Status: accepted

## Context

A trial publication and its registry record share an NCT number, so naive identifier deduplication deleted registry records.

## Decision

Deduplicate on namespaced identifiers, treating NCT numbers as identifiers only between registry records, alongside SimHash for near duplicate text.

## Consequences

Registry records survive for the trial prefilter while true duplicates from PubMed and Europe PMC still collapse.
