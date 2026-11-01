# Research gap statement (2026-11-02)

Working document for the authors. Basis: roughly 60 web searches and about 35 page or paper fetches over the
last weeks across jailbreak evaluation, LLM-as-judge statistics, e-discovery, content moderation, forensic
science, diagnostic medicine, fuzzing, regulation (EU, UK, NIST) and industry. Full texts read: Gao,
Schwinn, Fiedler (first half), Chouldechova (validity sections), Kaur, Eiras, Collot, Miller, Mu, and parts of
the SoK 2605.05058 and Nine Judges 2605.29800. Everything else: abstracts and snippets. "Not found" means not
found by these searches. Identifiers are as returned by search and must be verified before citation.

## 1. The method is old; the gap is its absence in this field

Sampling the items a classifier discards, to estimate what it misses, is standard elsewhere:
* e-discovery (technology-assisted review): the **elusion test** samples the discard pile to estimate recall;
  stratified elusion is patented and used; its reliability and the explosion of the recall interval at low
  prevalence are documented (EDRM TAR guidelines; Cormack and Grossman literature);
* content moderation: prevalence and false-negative rate of content left up are estimated from random or
  stratified samples (Wei, Zufall and Jia 2305.09601, AIES 2024; ML-assisted weighted sampling with LLM labelling
  2602.18518; Trust and Safety practice);
* forensic science: "The Neglected Error" (2412.05398) argues that validation studies report false positives and
  ignore false negatives from eliminations;
* diagnostic medicine: partial verification bias and its corrections (Begg and Greenes 1983; inverse
  probability weighting; double sampling, Tenenbein 1972);
* ML: separate-sampling recall estimation under imbalance (Shang et al. 2023).
Therefore **no statistical novelty may be claimed.**

## 2. What jailbreak and LLM-safety evaluation does instead (evidence of the gap)

| Observation | Source |
|---|---|
| Humans label judge-positives only; corrected ASR = ASR x precision; false negatives never measured; "labelling negatives is prohibitively inefficient" | Schwinn et al. 2603.06594 |
| Precision-only correction, one dataset of 596 completions, no interval | Gao 2606.25487 |
| "ΔASR" is the absolute difference between human-annotated ASR and judge ASR on a fully annotated benchmark of 300 questions; no sampling of negatives, no interval | SoK 2605.05058 |
| Comparisons of six evaluators on two existing labelled sets; accuracy, precision, recall, FPR; no population estimate | Mu 2609.10594 |
| False negatives are acknowledged to underestimate ASR but not estimated at population level | 2504.02080; JailMeter 2607.19424 |
| A position paper demands judge performance disaggregated by target and method and valid corrections, without giving an estimator or data | Chouldechova et al. 2601.18076 |
| Generic bias-correction and calibration-sharing risks for LLM judges, outside safety | Lee 2511.21140; Chen 2601.05420; Fiedler 2605.06939 |
| Null-result (clean benchmark) certification assumes the scoring rule is correct | Kaur 2607.21735 |
| Judge panels share failures: 9 judges behave like 2.2 independent votes; 5.1% of items wrong for all nine (natural-language inference, not safety) | Nine Judges 2605.29800 |
| A benign arm exposes judge over-flagging (0.61 to 0.70 of benign responses flagged by one judge) | 2609.26176 |
| NIST AI 800-2 (initial public draft): practices for automated benchmark evaluation, uncertainty quantification, reporting qualified claims | NIST CAISI |
| EU GPAI Code of Practice: evaluation procedures, scoring methods and comparisons with human baselines to be documented | Code of Practice, Measure 7.3 |

## 3. The gaps, ranked

**G1 (primary). Population-level miss rate of jailbreak judges, measured with a design that samples judge-negatives.**
No study found estimates what automated jailbreak judges miss across a population of responses, or reports
an ASR interval that includes false negatives. Existing validation is positives-only (verification bias) or on
small fully labelled sets. Our design: stratified human audit with a large all-judges-say-no stratum and
known inclusion probabilities.

**G2. Judge-adjusted evidential ceiling.** The sample size needed to support a "no jailbreak found" claim
depends on the judge's sensitivity; the null-result theory takes the scorer as given. Closed form
n >= ln(alpha) / ln(1 - s p) with a sensitivity lower bound from the audit.

**G3. Decision-level validity.** Existing judge validation reports accuracy, kappa, or absolute ASR bias.
Nobody found reports how often a judge-based comparison of models reaches a wrong or missed conclusion
against a human-grounded estimate (trial-level surrogacy in the clinical sense).

**G4. Positive-control (spike-in) audits for sensitivity when natural positives are rare.** Planted-failure
canaries exist in industry (e.g. PII detectors) but none found for jailbreak judges.

**G5. Common-mode failure of judge ensembles in safety.** Evidence exists for NLI panels; the share of true
jailbreaks that every judge in a panel misses is unmeasured.

**G6. Reasoning-trace and configuration effects on judge error against human labels** (thinking mode, trace
shown to the judge). Existing work measures trace risk (Chain of Risk) but not judge error.

**G7. A protocol that turns the above into reportable evidence for the new standards** (NIST AI 800-2 draft,
EU Code Measure 7.3): none found.

## 4. Preliminary empirical signal (not final; labels under review)
If the audit labels are valid, single judges recover roughly 7 to 42% of true successes, the union of four
about 40 to 45%, and 1.3 to 2.8% of responses that all four judges call safe are successes. These come from two
effective raters (the six returned files contain two distinct label sets) and need independent re-reading
before use; see PRELIMINARY_AUDIT_RESULTS.md.

## 5. What would remove the gap (monitor before submission)
A paper that audits judge-negatives in jailbreak or LLM-safety evaluation with an interval for the miss rate;
a follow-up to Schwinn et al.; a NIST or EU methodology document specifying negative-sample audits.
Re-run the searches in the month before submission.

## 6. Venue notes (from searches; not verified against journal scope pages)
* Computers and Security and JISA: no 2026 papers on this topic surfaced in the searches; scope must be checked
  on the journals' pages.
* A 2026 Springer *Cybersecurity* paper (RefusalGuard-M, human-machine jailbreak evaluation) shows security
  journals publishing evaluation-methodology work.
* The risk that reviewers read this as an ML-evaluation paper rather than a security paper must be answered in
  the introduction (the result decides which models are called safe and which defences are said to work).
