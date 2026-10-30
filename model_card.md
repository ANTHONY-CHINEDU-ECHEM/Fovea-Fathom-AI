# Model card

## System

Fovea Fathom AI is a retrieval augmented system, not a trained model. It composes a retriever (hashing embeddings offline or BGE base in production, BM25 with an ophthalmic tokenizer, reciprocal rank fusion, a lexical or cross encoder reranker and clinical priors), a language model selected at run time (Claude by default, OpenAI or a local Ollama model as alternatives, and an extractive generator as the final fallback), deterministic ophthalmic tools and independent validators.

## Intended users and uses

Registered eye care professionals in the NHS asking about treatment options, guidance criteria, trial evidence, screening grades, intervals, safety checks and monitoring. See the clinical safety case for exclusions.

## Data

UK national guidance, NHS screening criteria, professional body guidance, PubMed and Europe PMC literature, ClinicalTrials.gov, openFDA label safety sections and MedlinePlus, as listed in `docs/data_sources.md`. No patient data is used for training or retrieval.

## Evaluation

The 53 question golden set measures retrieval, fact recall, citation coverage, claim support, unsupported figures, emergency triage, abstention, scope, tool routing, redaction and laterality. Offline results are in `evaluation/reports/offline_latest.md`; live results depend on the configured model and index and must be regenerated with `make eval_live`.

## Known limitations

* The seed snapshot is small; questions outside it should abstain, and do in the golden set.
* Lexical reranking is weaker than a cross encoder for paraphrased questions.
* Claim support is lexical and can miss subtle contradictions; it is a screen, not proof.
* Laterality checks the eyes named; it cannot detect an error where the answer names no eye.
* Treat and extend regimens and glaucoma targets are local defaults that need local agreement.

## Ethical considerations

The system is designed to reduce, not replace, clinical reasoning. Abstention is preferred to fluent guessing, and every figure is either computed transparently or traced to a cited source.
