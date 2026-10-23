# Paper roadmap: everything that must happen before submission

Working document for the authors (2026-10-23). Companion to `STUDY_PLAN.md` (what the study is),
`LITERATURE_REVIEW.md` and `DEEP_RESEARCH.md` (why it is novel and what is not), `NOVELTY.md` (older
analysis). Effort figures are my estimates, not measurements. Target venue, in order: Computers & Security,
then JISA, then IEEE Access as a fallback. Acceptance chances are in the earlier discussion and are guesses.

## 0. The paper in one paragraph

Working title: *How many prompts and how many human labels does a jailbreak safety claim need?* A
diagnostic-accuracy framework for automated judges. Claim: published designs validate judges on
judge-positives only (verification bias) and correct ASR by precision alone; we label the judge-negatives
too, estimate what judges miss, give intervals that include it, show when a judge-based model comparison
reaches the wrong conclusion, and give a calculator for the sample size of a "no jailbreak found" claim that
accounts for judge sensitivity. Evidence: 8 current open-weight models, 7,230 attacks each, 12,862 responses
scored by four judges, a human-labelled stratified audit.

## 1. Contributions as they would be written (and what each needs)

| # | Contribution | Evidence needed | Status |
|---|---|---|---|
| 1 | Verification-bias-free audit design and a demonstration of how much positives-only designs inflate sensitivity | stratified human labels incl. judge-negatives; a re-analysis restricted to judge-positives | design done, labels missing |
| 2 | Miss-rate bound and ASR interval that include false negatives | all-judges-say-no stratum labels (about 400) | pilot only (0 of 23 positive) |
| 3 | Spike-in positive controls for judge sensitivity when natural positives are rare | human-confirmed positives; blind insertion script; per-judge recovery rates by victim-model context | idea, nothing built |
| 4 | Judge-adjusted evidential ceiling: sample size for a safety claim given judge sensitivity | derivation plus calculator; numbers from 3 | formula drafted (299 / 598 / 1,197 prompts at s = 1 / 0.5 / 0.25 for p = 1%, 95%) |
| 5 | Decision-level validity: how often a judge-based comparison gives the wrong sign or significance versus the human-grounded estimate | labels in enough model x strategy cells; Bayesian cell model; 28 model pairs x 6 strategies | old-data preview only |
| 6 | Reporting checklist (STARD-style) and mapping to EU Code of Practice Measure 7.3 | writing | not started |
| 7 | Supporting: reasoning-arm and configuration findings, control-arm false positives, released labels and hashes | existing GPU data | analysis partly done |

If label analysis kills 2 (stratum empty of positives), the paper survives on 1, 3, 4, 5, 6 and is then a
"judges jointly miss little here, and here is the bound" paper. Decide this at gate G2.

## 2. Work packages, in order

### WP1. Fix the generation data (blocks nothing except completeness)
| Task | Why | Who | Effort |
|---|---|---|---|
| Re-run muse-glimmer with a larger token cap or confirm the cause of 449 empty answers (6.2%, 373 of them encoding_attack, all at 300+ tokens) | its ASR is understated | friend's GPU, about 1 to 2 h | small |
| Re-run granite4.2 reasoning arm; 0 of 600 records carry a trace, so thinking never ran | reasoning-arm result invalid for that model | friend | small |
| Decide on SORRY-Bench (not downloaded; gated on Hugging Face) | corpus is 1,288 prompts without it | you | optional |
| Decide whether to run local judges on all 1,205 prompts instead of the first 270 | judged n = 12,862; full would be about 4.5 times larger | friend, about 40 to 70 GPU-h | optional |
| Optional repeat run at temperature above zero on a subset, to separate generation randomness from prompt effects and judge error | hierarchical decomposition | friend, about 3 GPU-h | optional |
Record in the paper as limitations anything not fixed.

### WP2. Build the labelling set (the critical path)
1. Build the stratified sheet from the new data. Strata and targets (from `STUDY_PLAN.md`, revised for the
   real counts: 12,071 all-no, 789 disagree, 2 all-yes in the judged set):
   * all four judges say no: about 400 (rule: 0 of 400 gives a stratum upper bound of 0.9%, contribution
     to ASR at most 0.85 points);
   * judges disagree: 350 to 500 of the 789 (more is cheap and shrinks the dominant uncertainty);
   * all say yes: the 2 that exist, plus the control items below;
   * controls: 150 benign XSTest responses (false positives);
   * per-cell coverage: at least 15 labels per model x strategy cell where cells have positives;
   * spike-in set (WP4): taken from confirmed positives, not extra labelling.
   About 950 to 1,150 items. Seed fixed and recorded; selection reproducible from a hash.
2. Three annotators, each item by two of three, 300 items by all three. About 12 to 15 hours each.
3. Labelling protocol: response-only rubric (jailbreak / partial / refusal / safe; success = first two),
   a calibration round on 30 items with the key, blinded to judge verdicts and to the model name, no
   discussion until all finish. `label.html` already enforces response-over-request wording.
4. Ethics: written note from supervisor (approval or exemption), annotators adults, informed of content,
   can stop at any time; labels stored without raw harmful text beyond what the sheet needs; raw text never
   leaves the private channel.
5. Agreement statistics: Cohen kappa pairwise, Fleiss kappa on the triple set, Krippendorff alpha for the
   ordinal rubric; adjudication rule for disagreements (majority of three, else a fourth read by the lead).
Effort: building the sheet is a day of my work; annotation is the long pole (calendar 2 to 4 weeks if the
annotators work part-time).

### WP3. Analysis code (my work, can start before labels exist)
| Module | Content | Status |
|---|---|---|
| Estimators | cell-wise Bayesian ASR with false negatives; PPI++/EIF comparison following Chen et al.; Miller-style clustered intervals (prompt as the cluster); Wilson/Clopper-Pearson for single rates | prototype exists (`calibrated_asr.py`) |
| Per-cell error | sensitivity, specificity, Youden J, delta-J with bootstrap intervals for each model x strategy cell and each judge | to write |
| Coverage study | resample label subsets from the audited population, check that nominal 95% intervals cover (target 93 to 97%) | to write |
| Verification-bias demo | recompute sensitivity using only judge-positive labels versus the full design | to write |
| Decision-level validity | pairwise model comparisons under each judge versus human-grounded estimate; wrong-sign rate, wrong-significance rate | partly (`conclusion_stability.py` on old data) |
| Spike-in recovery | per-judge recovery by victim-model context, with intervals | to write |
| Sample-size calculator | judge-adjusted evidential ceiling; a small script and a table | to write |
| Reasoning arm | answer-only versus with-trace judge verdicts against human labels (needs labels on those 1,200 records; label about 150) | partly |
| Figures | forest plot of corrected ASR with raw ASR overlay; heat map of per-cell sensitivity; coverage plot; sample-size curves; label-budget curve | to write |
Everything runs on this laptop (numpy only). Keep a single script that regenerates every table and figure
from the labels and judge files so the paper is reproducible.

### WP4. Spike-in experiment (new, small)
Select human-confirmed positives (from the audit and from the older nine-model data); insert them blind into
the judging stream attached to different victim-model contexts; measure recovery for each of four judges.
Realism requirement: positives must span easy to hard (the literature warns that recall on easy content
overstates protection). Local judge runs for this are small enough for the laptop (hundreds of items) but
slow on CPU; the friend's GPU is the safe route.

### WP5. Verification and signed record (supporting, optional)
A signed manifest of prompt-set hash, model tags, seeds, judge versions and label hashes that lets a reader
re-verify a reported ASR. Position as engineering that makes the study auditable, not as a main
contribution (TEE-based attestable audits and zero-knowledge approaches exist).

### WP6. Missing reading (before any "nobody has done X" sentence)
Read in full: Lee 2511.21140, Chen 2601.05420, Fiedler second half, Kaur 2607.21735 remaining sections,
Chain of Risk, MultiBreak, 2606.20626 and 2608.05086 (IRT), 2605.23362 and 2605.16354 (budgeted judges),
2609.05797 (recall versus elicitability), 2608.30748, 2605.05058 (S&P SoK). Search again for
"verification bias" and "spike-in" within jailbreak/judge work in the month before submission. Prepare a
direct comparison with Schwinn et al. (their public labels allow positives-only comparisons).

### WP7. Writing
| Section | Content | Depends on |
|---|---|---|
| Abstract, introduction | problem, gap, five contributions, results headline | all results |
| Background and related work | about 40 verified references in six groups: jailbreak judges; judge-error correction; diagnostic-test methods; rare-event and null-result certification; reasoning-model evaluation; regulation | WP6 |
| Threat model and authorisation | signed grants, evidence chain, consent gate for datasets, what is and is not released | existing framework |
| Study design | models, prompts, strategies, judges, arms, strata, annotators, preregistered analysis | WP2 |
| Methods | estimators, intervals, spike-in, ceiling, decision-level metric | WP3, WP4 |
| Results | raw versus corrected ASR; per-cell error; coverage; verification-bias demo; decision-level validity; reasoning arm; control arm; sample-size tables | WP3 |
| Discussion and guidelines | what a red-team result may claim; checklist; EU Measure 7.3 mapping | results |
| Limitations | single prompt-set family, temperature 0, keyword/rubric/LlamaGuard/StrongREJECT-style judges only, small positive counts, three annotators, open-weight models only, no adaptive attacks | all |
| Ethics and disclosure | what harmful text exists, how it is held, dual-use assessment, vendor disclosure of serious weaknesses, annotator welfare | WP2 |
| Data and code availability | labels and hashes released; raw responses and prompts not released; code and calculator released | all |
Write the methods and the study-design sections now; they do not depend on results.

### WP8. Submission package
* Conference-extension statement: cite the CSAM-2026 paper, list what is new (rule of thumb: more than 30%
  new material; here the data, labels, methods and framework scope are new), obtain the conference's
  copyright/permissions clearance if needed.
* Cover letter stating the extension and the novelty over Schwinn, Kaur, Lee, Fiedler.
* Highlights, graphical abstract, keywords, reproducibility statement, conflict-of-interest, author
  contributions (sole author: you), funding statement, ethics statement, data statement.
* A supervisor read-through; a methods read-through by someone who knows statistics.
* Artefacts: repository tag, DOI archive of code and label files (no harmful text), hash manifest.

## 3. Timeline (calendar estimate; the annotators set the pace)

| Weeks | Work | Who |
|---|---|---|
| 0 to 1 | WP1 re-runs; build sheet; send to annotators; finish ethics note; WP6 reading; write methods and study-design drafts; analysis code skeleton | friend, you, me |
| 1 to 4 | annotation (2 to 4 weeks), calibration round first; in parallel WP3 modules on pilot labels, WP4 setup | annotators, me |
| 4 to 5 | adjudication; run all analyses; gate decisions G1 to G3 | me, you |
| 5 to 8 | results, figures, full draft | me, you |
| 8 to 10 | supervisor and methods read, revisions, submission package | you, supervisor |
A realistic submission date is about 10 to 12 weeks from the day annotation starts. If annotators are slow, everything shifts; I cannot speed that part up.

## 4. Decision gates

| Gate | Test | If it fails |
|---|---|---|
| G1 (after calibration round) | inter-annotator kappa at least about 0.6 on the success label | revise the rubric, re-calibrate; do not proceed with weak labels |
| G2 (after labels) | positives found in the all-no stratum | zero or near zero: reposition as "bounded small miss rate"; contribution 2 becomes a bound |
| G3 | per-cell sensitivity differs across models or strategies | no difference: drop the heterogeneity claim, keep the rest |
| G4 | coverage of intervals 93 to 97% | fix the estimator before writing |
| G5 | decision-level wrong-sign or wrong-significance rate non-trivial under some judge | otherwise report that conclusions are stable, a weaker but honest result |
| G6 (before submission) | re-run of the literature search finds no paper doing contributions 1, 3, 4 or 5 | reposition or change venue |

## 5. Risks in order of importance

1. **Annotator throughput and quality.** Everything empirical rests on about 1,000 labels from three people.
2. **Rare positives.** ASR is 1 to 7% for most models; many cells will have only a handful of positives, so
   per-cell claims may be unsupported. Mitigate with the Bayesian model and by pooling cells only where
   delta-J allows.
3. **Novelty erosion.** Neighbouring papers appear monthly; re-run the search before submitting.
4. **Reviewer question "where is the security contribution?"** Answer in the introduction: the result
   decides which models are called safe and which defences are said to work.
5. **Data issues** (muse-glimmer empties, granite thinking, 270-prompt judge sample). Fix or declare.
6. **Ethics process.** Without the supervisor's note the annotation should not start.
7. **Disk space.** The laptop's E: drive has about 3 GB free; analysis outputs are small, but check before
   large operations.

## 6. What I (the assistant) can do, and what only people can do

| I can | Only you / others can |
|---|---|
| Build the sheet, all analysis code, figures, the calculator, the spike-in script | Annotate; find and supervise annotators; ethics approval |
| Write full drafts of every section and the cover letter | Decide positioning and venue; sign off every claim |
| Read and summarise papers, keep the evidence log, re-run the search | Run GPU jobs (friend); send private files |
| Keep the repository, tests and documentation clean | Submit to the journal |
I cannot verify citations beyond what search returns; every reference and number must be checked by you
against the original before submission.
