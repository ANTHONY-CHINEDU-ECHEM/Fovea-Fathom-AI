# Contributing

Thank you for helping make eye care decision support safer.

## Ground rules

* Never commit patient data, real or realistic identifiers, harvested data, indexes or audit logs.
* Clinical content changes (rule files, seed records, prompts, priors, validators) need a named clinical reviewer in the pull request.
* Every new clinical rule needs a reference (guidance section, SmPC section or paper) and a test.
* Seed records must be summaries in your own words, link to the authoritative source and state how they were verified.

## Workflow

1. Create a branch and make the change.
2. Run `make check` (lint, types, tests, evaluation gate and README style).
3. If seed or rule files changed, bump the rule file version and review date and run `make demo_build`.
4. If retrieval, prompts or validators changed, attach the offline evaluation report and review the hazard log in `docs/clinical_safety_case.md`.
5. Open a pull request using the template.

## Style

* Python 3.11, ruff formatting, mypy clean.
* British English in all user facing text.
* The README must contain no hyphen or dash characters and no table of contents; `scripts/check_readme_style.py` enforces this.
