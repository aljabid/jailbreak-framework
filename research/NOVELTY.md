# Novelty analysis and contribution plan (journal paper)

Status: working document for the authors. Literature read at **abstract level** through web
search on 2026-10-13; every "nobody has done X" below is a claim to re-verify with a full
literature review before submission. The field moved fast in 2026 (five directly relevant
papers appeared between January and September), so this must be re-checked monthly.

## 1. Bottom line

* The plain claim "jailbreak judges disagree with humans, so attack-success rates depend on the
  judge" is **no longer novel**. It is established by several 2026 papers (section 2).
* A paper built on that claim alone will be read as incremental. It needs a sharper contribution.
* Our data support three sharper contributions (section 3). None is a guaranteed accept; together
  they are a distinctive package, and each rests on evidence we can produce with the planned runs.
* Honest risk: contribution C1 is an *application and adaptation* of known statistics
  (prediction-powered inference, stratified/active labelling) to jailbreak evaluation, not new
  statistical theory. Its value is that the 2026 literature calls for such measurement validity
  but, in our searches, nobody has built and validated it for jailbreak ASR.

## 2. What already exists (do not claim these)

| Work | What it shows | What it does not do |
|---|---|---|
| Chouldechova et al., *Comparison requires valid measurement* (arXiv 2601.18076) | ASR comparisons are often invalid; conceptual, theoretical and empirical argument using jailbreaking as the running example; points to differential-misclassification statistics | no concrete estimator or interval in the abstract; no multi-model empirical validation that we could see |
| Mu, *An Empirical Measurement of Jailbreaking Evaluators* (2609.10594) | six evaluators (HarmBench, JailbreakBench, JailbreakRadar, StrongREJECT, JADES, JailMeter) on shared human-labelled data; evaluator choice changes conclusions; JADES best | comparative only; no correction or uncertainty method stated |
| Gao, *How Reliable Is Your Jailbreak Judge?* (2606.25487) | 596 human-labelled HarmBench completions; classifier over-flags (precision 0.835, recall 0.974), LLM judges erratic recall (0.06 to 0.65); wrapper robustness; recommends precision-corrected ASR | does not propose a judge fix or a principled corrected estimator |
| JailMeter (ACL Findings 2026) | multi-agent evaluator, 97% accuracy claimed on 330 instances | self-reported; a better judge, not an estimator |
| Wu et al., *Validity-Aware Jailbreak Evaluation* (2609.00498, EMNLP 2026) | many "successful" jailbreaks are factually invalid (22 to 51% reclassified); SEAV judge | no uncertainty on ASR |
| Maple et al. (2605.09070) | report distributional ASR across attack variants (VSM, union coverage) | says nothing on judge error |
| *Position: LLM-Safety Evaluations Lack Robustness* (2503.02574) | 5.27M generations; judge bias up to 25% by attack, 24% across models | position paper |
| MultiBreak (2605.01687) | judge agreement with humans varies with the victim model (0.13 to 0.89) | benchmark, no correction |
| PPI for LLM evaluation: Angelopoulos et al. (2301.09633), stratified PPI (NeurIPS 2024), ranking via PPI (2606.05308), active/stratified active inference (ICML 2026), OPAL (2606.03211) | valid intervals from few human labels plus many model labels; optimal labelling allocation | none of these found applied to jailbreak ASR |
| Reasoning traces: HarmThoughts (2604.19001), CoT Hijacking (2510.26418), trustworthiness survey (2509.03871) | traces can carry harm the final answer hides; thinking mode raises ASR in several same-model comparisons | not studied: effect of thinking mode on judge *error* and on corrected ASR |

## 3. Candidate contributions

### C1. A calibrated, uncertainty-aware ASR protocol for jailbreak evaluation (main claim)

Idea: report ASR with an interval that accounts for judge error, estimated from a stratified human
sample, instead of treating the judge's verdicts as truth.

Concrete design, already prototyped in `judge_reliability/calibrated_asr.py`:

* strata = judge-agreement pattern (all say success / all say no / disagree); human labels drawn
  uniformly within strata; population estimate by cells (stratum x judge verdict) with Jeffreys
  posteriors, so the interval stays valid when a cell has zero observed positives;
* multi-judge ensembles as the predictor;
* label allocation: the dominant "all judges say no" stratum needs far more labels than the
  disagreement stratum to bound ASR (section 5).

**Preliminary evidence on our 9-model, 950-response set (one annotator, 132 labels):**

| Estimator | Result |
|---|---|
| raw ASR by judge | 1.5% (keyword), 7.8% (StrongREJECT), 8.3% (ensemble), 9.3% (rubric judge), 12.1% (Llama Guard): an 8x spread |
| calibrated ASR by judge | 10.3 to 10.4% for all five predictors, interval [8.0, 17.1] |
| normal-approximation interval | [7.7, 9.7]: falsely narrow, because 0 of 23 labelled all-no items were positive (the stratum is 82% of the population) |

Honest reading: the judge-invariance of the calibrated value is largely by design (strata already
encode all judges). The real findings are (i) normal intervals are dangerously overconfident for
the dominant stratum, (ii) the estimate's uncertainty is dominated by what all judges miss, which
nobody measures, (iii) a concrete label budget follows from this.

What would make C1 strong: a coverage study on a large human-labelled population (resampling label
subsets of a few hundred items from a population of about 1,000 and checking that 95% intervals cover),
per-cell calibration showing that judge error differs across models and attack strategies (the
heterogeneity that breaks pooled corrections), an allocation rule for comparing two systems, and an
open implementation with a reporting checklist. Risk: reviewers may call it "PPI applied to a new
domain". Mitigation: the domain-specific rare-event design, the heterogeneity evidence, and results
showing that corrections change published-style conclusions.

### C2. Conclusion-stability audit across judges (supporting, already partly evidenced)

Question: do scientific conclusions change with the judge, not only the raw numbers?

Preliminary evidence (`judge_reliability/conclusion_stability.py`, 9 models x 4 judges, n=924):

* significance of pairwise model differences: 41% of judge-pair x model-pair cases disagree
  (keyword finds 1 of 36 pairs significant; rubric judge and Llama Guard 22; StrongREJECT 8);
* direction reversals: **none** (0 of 216), so we must not claim that rankings flip;
* the "bigger models are safer" trend inside the Qwen2.5 family holds under three judges
  (Spearman -0.74 to -1.00) but **vanishes under StrongREJECT (+0.05)**. A plausible reason, to be
  tested with the human labels: small models' answers are often garbled and not useful, which a
  usefulness-based judge scores low (compare Wu et al. 2609.00498 on invalid jailbreaks).

To strengthen: repeat on the 8 current-generation models and more prompts, add bootstrap intervals
on every comparison, and define a fixed list of claims checked under every judge.

### C3. Evaluation-configuration audit for the reasoning era (supporting)

Modern models reason by default, so configuration choices that were invisible before now matter:
thinking on or off, the token cap, the serving template, the judge's input. Existing work shows that
thinking mode changes ASR and that traces can hide harm; we found no study of how these choices change
**judge error and the calibrated ASR**. Our pipeline can measure it: main arm with thinking off, a
reasoning arm with thinking on and the trace stored, judged with and without the trace. Our own earlier
findings (empty completions at small token caps; an Ollama Llama Guard template that grades the
wrong turn) become quantified pitfalls. Lower novelty than C1, so keep it as support.

### C4. Resources and governance (supporting)

A multi-annotator human-labelled set of (request, response, label) records for current models,
released as labels and content hashes without harmful text; the authorisation-gated, auditable
evaluation framework (signed grants, evidence chain) from the conference paper. The framework fits a
security venue such as Computers & Security.

## 4. Claims we must not make

* "Judges are unreliable" as a new finding.
* "Rankings flip across judges": our data show none; only significance and the size trend change.
* Any "first" claim before the full literature review; phrase as "to our knowledge" and cite the
  position paper 2601.18076 as the call we answer.
* Efficiency gains from prediction-powered inference: on our current labels the judges are not
  informative enough within strata to narrow intervals (the PPI intervals were slightly wider than
  human-only ones in the coverage check).

## 5. Human-labelling plan that the contributions require

The current 132 labels (one annotator, disagreement-weighted) validate judges but cannot support ASR
estimation. Target set, in this order of priority:

| Stratum | Why | Labels |
|---|---|---|
| all judges say no | dominant stratum; bounds what every judge misses | 300 (zero positives would bound the stratum rate at 1.2% and the ASR contribution at 1.0 pp) |
| judges disagree | where judge errors live | 400 |
| all judges say yes | precision check | 60 |
| controls (XSTest safe prompts) | judge false positives | 150 |
| per-cell coverage | at least 15 labels per (model x strategy) cell for the heterogeneity analysis | spread across the above |

About 900 to 1,100 items, each labelled by two of three annotators, with 300 triple-labelled to report
Fleiss' kappa. At about one minute per item that is roughly 12 to 15 hours per annotator. Published
validations used 330 to 700 items (GuidedBench 700), so this exceeds the usual bar.

## 6. Paper skeleton

Working title: *Measuring jailbreak success validly: calibrated attack-success rates, label budgets and
evaluation audits for automated judges.*

1. Introduction: ASR depends on judges and configurations; the call for valid measurement (2601.18076).
2. Related work (section 2 of this file, expanded to about 40 verified references).
3. Threat model and framework (authorisation-gated measurement, from the conference paper).
4. Calibrated ASR: estimator, intervals, label allocation, coverage study (C1).
5. Experiments: 8 current models x 6 strategies x about 1,500 prompts, five judges, three annotators.
6. Results: heterogeneity of judge error; calibrated vs raw ASR; conclusion stability (C2);
   reasoning-era configuration audit (C3).
7. Guidelines and reporting checklist; limitations; ethics and disclosure.

Candidate venues: Computers & Security, Journal of Information Security and Applications; IEEE TIFS and
ACM TOPS are stricter on novelty and theory. The extension relationship with the CSAM-2026 paper must be
stated and the conference paper cited.

## 7. Decision gates

| Gate | Pass | If it fails |
|---|---|---|
| Per-cell judge error differs across models or strategies (C1 heterogeneity) | significant on at least one axis with the 3-annotator labels | drop the heterogeneity claim; keep the protocol and label-budget results |
| Coverage of the calibrated intervals near 95% | 93 to 97% in resampling | revise the estimator before writing |
| Conclusions change under judges (C2) | the size trend or significance changes persist on the 8 current models | present as a stability audit that mostly holds; weaker paper |
| All-no stratum stays near zero positives | upper bound of ASR contribution below 2 pp | report that judges jointly capture nearly everything: also a finding |
| Full literature review finds C1 already done | no prior jailbreak-specific validated estimator | reposition around C2 and C3 or change venue |

## 8. Evidence log

* Chouldechova et al. 2026, https://arxiv.org/abs/2601.18076
* Mu 2026, https://arxiv.org/abs/2609.10594
* Gao 2026, https://arxiv.org/abs/2606.25487
* JailMeter, https://aclanthology.org/2026.findings-acl.786.pdf
* Wu et al. 2026, https://arxiv.org/abs/2609.00498
* Maple et al. 2026, https://arxiv.org/abs/2605.09070
* LLM-safety evaluations lack robustness, https://arxiv.org/html/2503.02574
* MultiBreak, https://arxiv.org/pdf/2605.01687
* Prediction-powered inference, https://arxiv.org/pdf/2301.09633
* Ranking evaluation via PPI, https://arxiv.org/pdf/2606.05308
* OPAL, https://arxiv.org/pdf/2606.03211
* HarmThoughts, https://arxiv.org/html/2604.19001
* GuidedBench (700 expert-labelled items), https://arxiv.org/pdf/2502.16903
