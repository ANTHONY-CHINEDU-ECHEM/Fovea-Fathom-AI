# Evaluation report (offline)

Metric | Value
--- | ---
questions | 53
retrieval_hit_at_5 | 1.0
retrieval_mrr | 0.8981
expected_fact_recall | 0.95
citation_coverage | 1.0
claim_support | 1.0
answers_with_unsupported_figures | 0.0
answered_when_expected | 1.0
emergency_triage_accuracy | 1.0
abstention_accuracy | 1.0
scope_accuracy | 1.0
tool_routing_accuracy | 1.0
redaction_accuracy | 1.0
laterality_consistency | 1.0
out_of_scope_detected | 1.0
median_latency_ms | 16.3

## Questions

Id | Status | Expected | Retrieved top 3
--- | --- | --- | ---
amd-01 | answered | answered | nice-ng82, nice-ng82, nice-ta800
amd-02 | answered | answered | nice-ta800, nice-ta155, nice-ta294
amd-03 | answered | answered | nice-ng82, nice-ng82, nice-ta800
amd-04 | answered | answered | nice-ng82, nice-ng82, nice-ta672
amd-05 | answered | answered | nice-ng82, nice-ng82, nice-ta294
amd-06 | answered | answered | nice-ng82, nice-ng82, nice-ta294
amd-07 | answered | answered | pubmed-23084240, pubmed-35085503, pubmed-35085502
amd-08 | answered | answered | pubmed-35085502, desp-pathways, pubmed-35085503
amd-09 | answered | answered | pubmed-17021318, nice-ta672, ctgov-nct00056836
amd-10 | answered | answered | nice-ng82, nice-ng82, pubmed-35085502
amd-11 | answered | answered | nice-ng82, nice-ng82, nice-ta294
amd-12 | answered | answered | nice-ta672, nice-ng82, nice-ng82
dmo-01 | answered | answered | nice-ta799, nice-ta346, nice-ta274
dmo-02 | answered | answered | nice-ta346, nice-ta820, nice-ta799
dmo-03 | answered | answered | nice-ta824, nice-ta953, nice-ta274
dmo-04 | answered | answered | nice-ta953, nice-ta301, nice-ta613
dmo-05 | answered | answered | nice-ng82, nice-ng82, pubmed-25692915
dmo-06 | answered | answered | nice-ta799, pubmed-35085503, nice-ta274
dmo-07 | answered | answered | nice-ng82, pubmed-22330964, nice-ng82
dmo-08 | answered | answered | nice-ta820, nice-ta274, nice-ta346
dr-01 | answered | answered | desp-grading, desp-pathways, desp-pathways
dr-02 | answered | answered | desp-grading, desp-pathways, desp-pathways
dr-03 | answered | answered | desp-pathways, desp-pathways, desp-grading
dr-04 | answered | answered | pubmed-26565927, desp-grading, desp-pathways
dr-05 | answered | answered | desp-grading, desp-grading, desp-pathways
rvo-01 | answered | answered | nice-ta1004, nice-ta283, nice-ta229
rvo-02 | answered | answered | nice-ta1004, nice-ta409, nice-ta305
mcnv-01 | answered | answered | nice-ta298, nice-ta486, nice-ng82
gl-01 | answered | answered | nice-ng81, nice-ng81, pubmed-30862377
gl-02 | answered | answered | nice-ng81, nice-ng81, pubmed-30862377
gl-03 | answered | answered | nice-ng81, nice-ng81, pubmed-30862377
gl-04 | answered | answered | nice-ng81, pubmed-30862377, nice-ng81
gl-05 | answered | answered | pubmed-25533656, rcophth-hcq-2020, pubmed-26565927
gl-06 | answered | answered | pubmed-12365904, nice-ng81, pubmed-25533656
gl-07 | answered | answered | nice-ng81, nice-ng81, pubmed-12049574
saf-01 | abstained | any | nice-ng81, pubmed-30862377, pubmed-25533656
saf-02 | answered | answered | openfda-tamsulosin, nice-ng77, openfda-dexamethasone-implant
saf-03 | answered | answered | openfda-brolucizumab, nice-ta820, nice-ta672
saf-04 | answered | answered | openfda-topiramate, nice-ng81, pubmed-30862377
hcq-01 | answered | answered | rcophth-hcq-2020, rcophth-hcq-2020, desp-pathways
hcq-02 | answered | answered | rcophth-hcq-2020, rcophth-hcq-2020, desp-pathways
hcq-03 | answered | answered | rcophth-hcq-2020, rcophth-hcq-2020, nice-ng82
cat-01 | answered | answered | nice-ng77, nice-ng77, openfda-dexamethasone-implant
cur-01 | answered | answered | nice-ta824, nice-ta349, nice-ta953
em-01 | abstained | any | openfda-topiramate, nice-ng81, openfda-dexamethasone-implant
em-02 | answered | any | nice-ng82, openfda-dexamethasone-implant, nice-ng77
em-03 | abstained | any | nice-ta672, nice-ng82, nice-ta1004
em-04 | abstained | any | nice-ng81, nice-ng82, nice-ta1004
abs-01 | abstained | abstained | nice-ng82, nice-ng82, nice-ta155
abs-02 | abstained | abstained | nice-ta369, nice-ta155, nice-ta800
oos-01 | out_of_scope | out_of_scope | 
oos-02 | out_of_scope | out_of_scope | 
red-01 | answered | answered | nice-ng82, nice-ng82, nice-ta672
