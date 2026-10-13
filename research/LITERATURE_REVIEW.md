# Literature review and novelty re-check (2026-10-13)

Working document for the authors. Method: web searches on 2026-10-13 plus reading the abstract
pages of the key papers. Full texts were NOT read, so every statement below about what a paper
"does not do" is a claim to verify in the full text before submission. Numbers quoted are from
abstracts or search summaries. This replaces the "nobody has done X" claims in `NOVELTY.md`.

## 1. What is already established

### 1a. Jailbreak judges are unreliable (not novel)
* Gao, *How Reliable Is Your Jailbreak Judge?* (arXiv 2606.25487): 596 human-labelled HarmBench items;
  classifier precision 0.835 / recall 0.974; LLM judges recall 0.06 to 0.65; recommends reporting judge
  precision/recall on a human slice and a precision-corrected ASR (a simple correction, no interval theory).
* Mu, *An Empirical Measurement of Jailbreaking Evaluators* (2609.10594); JailMeter (2607.19424, ACL
  Findings 2026); CASCADE (2609.21793: judge reliability depends on dataset, target and attack outputs);
  GuidedBench (2502.16903: 200 cases, CI-width analysis); StrongREJECT (2402.10260); JailbreakRadar
  (2402.05668); Wu et al. *Validity-Aware Jailbreak Evaluation* (2609.00498: invalid "jailbreaks");
  *Rethinking Jailbreak Evaluation* (EMNLP Findings 2025); Do Encoders Suffice? (2606.25782); *LLM Judges
  Inconsistently Disagree Across Safety Criteria and Harm Categories* (2605.31381; Fleiss kappa about 0.23
  across seven judges).

### 1b. Comparing ASRs requires valid measurement (the call we answer)
* Chouldechova et al. (2601.18076): ASR comparisons are often invalid; conceptual/theoretical argument, no
  concrete jailbreak estimator seen in the abstract.
* Promptfoo note (non-peer-reviewed): judge errors vary by model and attack; two judges with equal accuracy
  can differ by 14 points of ASR. Same idea as ours, informal.

### 1c. Generic bias correction for LLM judges (this pre-empts the generic part of C1)
* Lee et al., *How to Correctly Report LLM-as-a-Judge Evaluations* (2511.21140, ICML 2026): plug-in
  (Rogan-Gladen style) correction with sensitivity/specificity, confidence intervals that include
  calibration-set uncertainty, adaptive allocation of calibration labels.
* Fiedler, *Bias and Uncertainty in LLM-as-a-Judge Estimation* (2605.06939): sharing a calibration across
  compared systems can **reverse the sign of a comparison with high apparent confidence**; proposes
  diagnostics J and delta-J. Closest conceptual neighbour of our heterogeneity idea. Not about safety.
* Prediction-powered inference: Angelopoulos et al. (2301.09633); stratified PPI; active/stratified active
  inference (ICML 2026); ranking via PPI (2606.05308); OPAL (2606.03211).
* *Calibrate, Don't Curate* (2605.09702) and *Decomposing LLM-Judge Uncertainty* (2609.06444): label-efficient
  estimation from noisy judges and uncertainty decomposition. Only titles/abstract snippets seen.
* Open-source tools exist for the correction itself (e.g. a judge-debiasing package, a judge-calibrator
  calculator). The arithmetic is commodity.

### 1d. Reasoning models and traces
* Chain of Risk (2605.05678): scores traces and answers separately on 15 models and about 41K prompts per
  model; "leak" (unsafe trace, safe answer) and "escape" (benign trace, unsafe answer) failures; answer-only
  evaluation under-counts risk.
* HarmThoughts (2604.19001), ReasoningShield (2505.17244), SafeRBench (2511.15169), TRACE (2608.24232),
  H-CoT (2502.12893), RECAP-related deceptive-alignment paper (2609.36254).
* Not found: a study of how thinking mode and judge input change judge **error against human labels** and
  the **corrected** ASR.

## 2. Consequences for our claims

| Earlier claim | New status |
|---|---|
| "Judges disagree with humans" | established; never a contribution |
| "A corrected ASR with an interval" (generic C1) | **generic method exists** (Lee et al., ICML 2026). A paper that only applies it to jailbreaks is an application paper |
| "Calibration should not be shared across systems" | **Fiedler 2605.06939 shows this in general**, with a sign reversal on MMLU-Pro. Our contribution would be the jailbreak-specific empirical measurement |
| "No one applied PPI/correction to jailbreak ASR" | still true in our searches except Gao's simple precision correction; weak claim, re-check |
| "Rankings flip across judges" | false in our data (0 of 216 raw reversals); must not be claimed |
| Trace vs answer matter | established by Chain of Risk; what remains is judge **error** and corrected ASR |

Honest verdict: what survives as novel is the **jailbreak-specific empirical and methodological content**,
not the generic estimator. Section 3 lists what to build on top.

## 3. Ideas that are novel relative to the above

Each idea names the evidence we would need and the way it can fail.

**I1. Differential-misclassification map for jailbreak ASR.** Estimate judge sensitivity and specificity
separately for every target model x attack strategy cell (using the 900 to 1,100 labels), and test whether
a pooled correction (what Lee et al. and Gao use) reverses or hides real comparisons. Fiedler's delta-J,
measured on real red-teaming data, is the new part. Fails if the error rates turn out homogeneous.
Needs: the 3-annotator labels. Strongest and cheapest.

**I2. Anytime-valid ASR audit with certified blind-spot bound.** Use confidence sequences / e-values
instead of fixed-n intervals, so labelling can stop the moment the interval is tight enough, and give a
guaranteed upper bound on what **all** judges miss (the dominant all-judges-say-no stratum). Sequential
label allocation for jailbreak ASR was not found in our searches. Output: an "ASR certificate" with a stated
miss bound. Fails if the all-no stratum contains many positives (then the bound is simply large, still a
finding).

**I3. Verifiable ASR: signed evaluation records.** Our framework already signs authorisation grants and
keeps an evidence chain. Extend it so a reported ASR is accompanied by a signed manifest of prompts, model
tags, seeds, judge versions and label hashes that a reviewer can re-verify. Fits Computers & Security and
the governance angle; no jailbreak-evaluation paper found doing this. Fails only if reviewers see it as
engineering; mitigate by quantifying how often published ASR claims cannot be reproduced from their
artefacts (a small audit of public repositories).

**I4. Two-dimensional ASR: compliance vs usefulness.** Collect human labels on two axes (did it comply;
was the content correct and actionable) and estimate both, building on Wu et al.'s invalidity finding. Our
Qwen size trend disappears under the usefulness-oriented judge, which is the hypothesis: small models comply
but produce garbage, so "bigger is safer" is a measurement artefact. Needs: a second label column.

**I5. Trace-aware judge error.** For the reasoning arm, label trace and answer separately and measure
judge error under three inputs (answer only, trace only, both). Chain of Risk shows the failure modes
exist; the judge-error and corrected-ASR measurement is what is missing. Small, well-scoped.

**I6. Calibration transfer test.** Fit a correction on one model family and apply it to another, and across
judge hosting (Groq vs local) and judge versions. Quantifies when a published correction is safe to reuse.
Pairs with I1.

**I7. Self-preference check for judges.** Our older nine-model set includes gpt-oss-20B both as a target and
as the rubric judge. Measure whether a judge is more lenient on its own family's outputs. Cheap, uses data
we already have. Fails if no effect.

**I8. Evaluation-protocol optimiser (tool).** Given a label budget and a set of judges, pick the strata and
the number of labels that minimise interval width, and print a reporting checklist. A usable artefact
(library + notebook) increases the paper's value beyond an analysis.

### Suggested package
Core: **I1 + I2 + I3** (differential error map, certified bound with sequential labelling, verifiable
records), with **I4/I5** as the two data-collection extras and **I8** as the released tool. This answers
Chouldechova et al.'s call with concrete methods, goes beyond the generic Lee et al. and Fiedler results by
being jailbreak-specific, and fits a security journal.

### Ideas rejected
* Building stronger attacks (outside project scope).
* Training a new judge as the main contribution (crowded: JailMeter, JADES, SEAV, encoders).
* Claims about ranking flips (not supported by our data).

## 4. Next verification steps
1. Read the full texts of 2511.21140, 2605.06939, 2606.25487, 2601.18076, 2605.05678 and 2605.09702; check
   what each really covers.
2. Search again for jailbreak-specific uses of confidence sequences, stratified PPI and per-cell error
   rates in the venues for the target journal.
3. Run I1 and I7 on existing data first (cheap) to see whether they have signal before committing.
4. Repeat this search monthly until submission; the field changed five times in nine months.

## 5. References (arXiv ids as returned by search; verify before citing)
2601.18076, 2606.25487, 2609.10594, 2607.19424, 2609.21793, 2502.16903, 2402.10260, 2402.05668,
2609.00498, 2606.25782, 2605.31381, 2511.21140, 2605.06939, 2301.09633, 2606.05308, 2606.03211,
2605.09702, 2609.06444, 2605.05678, 2604.19001, 2505.17244, 2511.15169, 2608.24232, 2502.12893,
2609.36254, 2605.09070, 2503.02574, 2605.01687.

## 6. Full-text reading (2026-10-13) and what it changes

Read in full: Gao 2606.25487, Fiedler 2605.06939 (first half plus tables), Chouldechova 2601.18076
(measurement-validity sections), Lee 2511.21140 (keyword scan of the text), Chain of Risk 2605.05678
(judge-validation appendix), Calibrate-Don't-Curate 2605.09702 (keyword scan). Not read in full: Schwinn
2603.06594 ("A Coin Flip for Safety", abstract only), Chen 2601.05420 (abstract only), Collot 2512.08121
(abstract only). Statements about those three are provisional.

| Paper | What the full text shows | Effect on our ideas |
|---|---|---|
| Chouldechova | Section 5 states that judges with different TPR/FPR across target systems and across jailbreak methods bias ASR comparisons, that studies "rarely assess, much less report" judge performance disaggregated by target model, and that misclassification statistics (Yi 2016) can give more valid ASRs. Recommendation 4: report judge performance disaggregated by target system and method and correct where errors differ. A position paper: no estimator, no data | I1 is the **empirical execution of their recommendation 4**, not a new idea. Cite and frame it that way |
| Fiedler | Defines Youden J and delta-J (cross-model calibration gap), shows 1/J amplification and a sign reversal on MMLU-Pro, recommends model-specific calibration (PPI++) and bootstrap intervals, and calls delta-J "novel as a formal diagnostic". Not about safety | The statistics of I1 exist. What remains is jailbreak data with per-cell delta-J, which nobody (in what I read) reports |
| Gao | One dataset (HarmBench classifier validation set, 596 items), three small open LLM judges, a precision-only correction with no interval, no per-model or per-attack analysis. Its limitations section lists exactly those gaps. Cites Schwinn and Miller (error bars) as closest work | Confirms the gap for a jailbreak estimator with intervals; also shows the field already accepts "report precision/recall and corrected ASR" as advice |
| Lee et al. | Rogan-Gladen with intervals that include calibration uncertainty; robust to shift in the true-positive rate if judge behaviour depends only on latent correctness (an assumption that fails if error depends on the victim model). No stratification, no safety, no rare-event treatment | Their assumption is the formal reason per-cell error matters for jailbreaks; use it as motivation |
| Chain of Risk | Judges (two LLMs) validated on 80 examples by three humans: binary-unsafe kappa 0.708 (trace) and 0.741 (answer). No judge-error correction or interval for the reported rates found in my keyword scan (not exhaustive) | I5 stays open, but the baseline human validation is small (80 items), so a larger labelled trace study is a real step up |
| Calibrate-Don't-Curate | Estimation from noisy judges with a limited label budget; judge-panel heterogeneity; datasets are judge benchmarks (JudgeBench, RewardBench), not safety | Label-budget idea is not unique to us; the jailbreak rare-event stratum is our angle |
| Schwinn (abstract) | 6,642 human-verified labels; judge accuracy often near chance under shifts of victim model, attack and ambiguity; many attacks inflate ASR by exploiting judges; releases ReliableBench and JudgeStressTest | **Overlaps the empirical half of I1 strongly** and has about six times our planned labels. What the abstract does not mention: corrected ASR, intervals, conclusion-stability re-analysis |
| Chen (abstract) | Efficient influence-function estimators unifying Rogan-Gladen and PPI, intervals up to about 10x narrower than Rogan-Gladen (secondary source) | The generic estimator is settled; we should use PPI++/EIF rather than invent one |

### Revised honest assessment
* "Judge error varies by victim model and attack" is **established** (Schwinn, Chouldechova, MultiBreak,
  CASCADE). It cannot be a headline.
* "A better correction estimator" is **not available to us**: Lee, Chen and Fiedler cover the generic
  statistics, and the stratified/active variants exist in PPI work.
* What the papers read do **not** contain: (a) per-cell sensitivity/specificity with delta-J and
  coverage-checked corrected ASRs on current-generation open models; (b) a re-analysis showing which
  published-style conclusions change after correction; (c) a certified bound on what all judges miss in a
  rare-event setting; (d) signed, re-verifiable evaluation records; (e) a large human-labelled trace-vs-answer
  study. Items (d) and (a)-(b) are the most distinctive in combination; (c) rests on classical bounds
  (rule of three) and would be a modest contribution on its own.
* Consequence: the paper is an **applied measurement-validity study with a verifiable protocol**, not a
  statistics-novelty paper. That fits a security/applied journal (Computers & Security, JISA) and is a stretch
  for venues that demand new theory. A possible change of plan: put I3 (verifiable evaluation) and the
  conclusion re-analysis first, and present I1 as the empirical answer to Chouldechova's recommendation 4.

### Still to read before claiming anything
Schwinn et al. 2603.06594 in full (closest empirical competitor), Chen 2601.05420, Collot 2512.08121,
Know Thy Judge 2503.04474, Miller 2411.00640, MultiBreak 2605.01687, Mu 2609.10594.
