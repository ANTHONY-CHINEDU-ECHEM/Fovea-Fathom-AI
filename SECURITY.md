# Security policy

## Reporting

Report vulnerabilities privately through GitHub security advisories for this repository. Do not open public issues for security problems, and never include patient data in a report. We acknowledge reports within five working days.

## Scope

In scope: the API, redaction, authentication and rate limiting, audit logging, the ingestion connectors, the interface and the container configuration. Clinical safety concerns that are not security issues should use the clinical safety issue template.

## Deployment guidance

* Set `FF_ENVIRONMENT=production`, `FF_API_KEYS`, `FF_ADMIN_API_KEYS` and a long random `FF_AUDIT_SALT`.
* Terminate TLS in front of the API and the interface.
* Use the local Ollama profile where information governance does not permit clinical text to leave site.
* Restrict access to Prometheus, Grafana, Qdrant and Redis to the internal network.
* Review the data protection impact assessment before connecting any patient facing system.
