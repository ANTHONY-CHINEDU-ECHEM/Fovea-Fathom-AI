# Data sources and provenance

Every record in `ingestion/data/seed` carries a `verification` field. This page summarises how each group was verified on 30 October 2026 and how the full harvest extends it.

## Seed snapshot

| Group | Records | How verified | Licence |
| --- | --- | --- | --- |
| NICE guidelines (NG82, NG81, NG77) | 3 | Recommendations or rationale read on nice.org.uk; summarised in our own words by section. The NG81 24 mmHg threshold and the NG77 referral wording are flagged for confirmation against the recommendation text. | Summary with link |
| NICE technology appraisals | 25 | Number, title and date checked on nice.org.uk listings, scopes or recommendation pages. Recommendations summarised where read (TA294, TA672, TA799, TA800, TA820, TA824, TA953, TA1004, TA590). Others carry "check the appraisal". TA349, TA301 and TA613 are included as superseded records. | Summary with link |
| NHS Diabetic Eye Screening Programme | 2 | Pathway document dated 25 July 2023 read; grading definitions summarised and flagged for confirmation against the current criteria publication. | Open Government Licence |
| Royal College of Ophthalmologists | 1 | Hydroxychloroquine and chloroquine monitoring guideline (December 2020) read. | Link only |
| PubMed trials | 13 | Each PMID confirmed against PubMed or a PubMed mirror record on 30 October 2026. Headline results only. | Abstract, fair dealing |
| ClinicalTrials.gov | 4 | NCT numbers confirmed (TENAYA NCT03823287, LUCERNE NCT03823300, YOSEMITE NCT03622580, MARINA NCT00056836). Recruitment status not verified. | US public registry |
| openFDA label summaries | 6 | Summarised from US prescribing information warnings; replaced by harvested sections on `make ingest`. | US public domain |

Confirmed PMIDs: MARINA 17021318, ANCHOR 17021319, VIEW 23084240, TENAYA and LUCERNE 35085502, YOSEMITE and RHINE 35085503, RISE and RIDE 22330964, VIVID and VISTA 25012934, Protocol T 25692915, Protocol S 26565927, LiGHT 30862377, UKGTS 25533656, EMGT 12365904, OHTS 12049574.

## Full harvest

`ingestion/config/corpus.yaml` lists the PubMed query families, Europe PMC queries, registry conditions, label medicines, NICE guidance and MedlinePlus topics. Every harvested record states its source in `verification` and keeps its licence on every chunk.

## Rule files

The rule files in `backend/fovea/knowledge` are curated, not harvested. Each states its sources in comments and carries a version and review date. Items that summarise SmPC posology (injection regimens) or local practice (glaucoma target pressures) are labelled as local protocol defaults and must be agreed locally.
