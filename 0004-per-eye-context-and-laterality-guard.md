# 0004. Per eye context and laterality guard

Status: accepted

## Context

Most ophthalmic decisions are made for one eye. Free text context invites the model to transfer findings between eyes.

## Decision

Hold patient context as right and left eye objects, run tools per eye, label every card, and check every answer for references to an eye the question did not ask about.

## Consequences

Wrong eye errors become visible, measurable and alertable. The guard cannot catch answers that name no eye, which is documented.
