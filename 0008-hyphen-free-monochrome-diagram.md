# 0008. Monochrome architecture diagram in Mermaid

Status: accepted

## Context

The README must render a high quality architecture diagram on GitHub in light and dark themes, with no background colour, and the README must contain no hyphen characters.

## Decision

Draw the diagram in Mermaid with thick link syntax (which needs no hyphen), outline only class definitions, layer to layer links so subgraph directions are honoured, and invisible links to arrange rows. Keep the source in docs/architecture.mmd and enforce equality and style in continuous integration.

## Consequences

The diagram renders cleanly in both themes and cannot drift from its source.
