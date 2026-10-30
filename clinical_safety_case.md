# Clinical safety case (draft for DCB0129)

Status: draft prepared by the manufacturer's development team. It must be reviewed and signed by a named Clinical Safety Officer before any use in patient care, and each deploying organisation must complete its own DCB0160 assessment.

## 1. Intended use

Fovea Fathom AI supports registered eye care professionals (ophthalmologists, optometrists with extended roles, specialist nurses and pharmacists) by answering questions about NHS eye treatment from cited, licence tracked evidence and by computing routine ophthalmic quantities with deterministic tools. It does not diagnose, it does not prescribe, and it is not a medical device. Every output is advisory and must be confirmed against the full guidance, the SmPC, the local protocol and the patient's own findings.

Out of scope: direct patient use without a clinician, paediatric dosing, emergency triage in place of local emergency eye care pathways, and any automated action on patient records.

## 2. Hazard log

Likelihood and severity use the DCB0129 five point scales (1 very low to 5 very high). Risk = likelihood x severity before and after controls.

| Id | Hazard | Cause | Effect | Controls | L x S before | L x S after |
| --- | --- | --- | --- | --- | --- | --- |
| H1 | Advice applied to the wrong eye | Model transfers findings between eyes; clinician misreads a card | Treatment of the wrong eye (never event) | Per eye context and tool cards labelled by eye; laterality guard on every answer; alert `LateralityMismatch`; audit field; prompt rule 6 | 3 x 5 | 1 x 5 |
| H2 | Invented injection interval, dose or lens power | Model generates a plausible number | Under or over treatment; refractive surprise | Numbers from deterministic tools only; figure check against cited sources; US dosage sections never indexed; biometry recheck triggers | 4 x 4 | 1 x 4 |
| H3 | Treatment presented as NHS funded when criteria are not met | Appraisal criteria omitted or misremembered | Inappropriate treatment or funding dispute | Therapy matrix with criterion by criterion eligibility; check the appraisal status when unconfirmed | 3 x 3 | 1 x 3 |
| H4 | Evidence for one condition applied to another | Retrieval mixes DMO and AMD evidence | Wrong criteria (thickness versus acuity window) | Chunk level condition tags; condition priors and conflict penalty; extractive condition filter; prompt rule 7 | 3 x 3 | 1 x 3 |
| H5 | Superseded guidance presented as current | Old appraisal ranks highly | Outdated eligibility (for example phakic eyes and the dexamethasone implant) | Supersession graph; ranking penalty; labels in answer and interface; alert `SupersededGuidanceCited` | 3 x 3 | 1 x 3 |
| H6 | Delay in an eye emergency | Emergency described as a routine question | Permanent visual loss | Triage before retrieval; banner first; never cached; never suppressed by abstention | 2 x 5 | 1 x 5 |
| H7 | Missed contraindication | Medicine history not considered | Bronchospasm, hypersensitivity, raised pressure, implant migration | Safety screen with SmPC referenced rules; brand to generic mapping; missing information listed | 3 x 4 | 2 x 4 |
| H8 | Patient data disclosed to a third party | Identifiers in free text sent to a model vendor | Data protection breach | Redaction before retrieval, model, cache and logs; keyed hash audit; local Ollama option | 3 x 3 | 1 x 3 |
| H9 | Prompt injection in harvested content | Malicious or malformed source text | Model follows injected instructions | Injection filter; sources marked untrusted; validators independent of the model | 2 x 3 | 1 x 3 |
| H10 | Referral to a closed or unsuitable trial | Stale registry data | Wasted referral, false hope | Status verified flag and cautions; refresh job | 3 x 2 | 1 x 2 |
| H11 | Service unavailable during clinic | Vendor outage | Delay, workarounds | Fallback chain with circuit breakers ending in the extractive generator | 3 x 2 | 1 x 2 |
| H12 | Over reliance on the tool | Fluent answers trusted without checking | Unchecked errors reach patients | Mandatory clinical judgement line; grounding report on every answer; abstention when evidence is thin; training | 3 x 4 | 2 x 4 |

## 3. Verification evidence

* Unit and integration tests (163) cover each control above, including every emergency rule, every screening grade, SRK/T inversion, the laterality guard, redaction of each identifier type and provider fallbacks.
* The golden set evaluation gate runs in continuous integration with thresholds that must be met before merge, including emergency triage, redaction and laterality consistency at 1.0.
* Rule files carry a version and review date that appear in every tool card and in `GET /v1/knowledge`.

## 4. Residual risk and conditions of use

Residual risks H7 and H12 remain at 2 x 4 and are acceptable only with clinician training, local protocol review of the treat and extend regimens and glaucoma targets, and the monitoring described below.

## 5. Post deployment monitoring

* Prometheus alerts: unsupported figures, laterality mismatch, low grounding rate, abstention spike, superseded guidance cited, negative feedback spike, open circuit breakers.
* Monthly review of the audit summary and clinician feedback by the Clinical Safety Officer.
* Re evaluation with `make eval_live` after any change to the model, prompts, priors or rule files.
