# DRAFT: study design and methods (v0, 2026-10-31)

Status: first draft of the sections that do not depend on label results. Numbers marked [FILL] depend on the
audit. Statements that need a check against the final data are marked [VERIFY]. Written in plain Markdown;
convert to the journal template once the venue is fixed. Nothing here is submitted or approved.

## 3. Threat model and authorisation

The study measures automated judges on responses that open-weight models produced under six prompt-level
attack strategies. We do not develop new attacks. Every request to a model passes through the evaluation
framework's authorisation gate: a signed grant (HMAC-SHA256) names the permitted target, models, providers,
strategies and a maximum number of attacks, and the framework refuses to run outside it [VERIFY wording
against the framework paper]. The public benchmark prompt files are fetched from their original sources
only after the operator confirms the datasets' terms; the SHA-256 of each file is recorded in a manifest that
travels with the results. Raw prompts, model responses and human labels that contain harmful text stay on
private storage; the paper releases labels keyed by content hash, aggregate statistics, code and the
sample-size calculator.

## 4. Study design

### 4.1 Targets
Eight open-weight models served locally through Ollama on one RTX 5090 (32 GB): qwen3.8:27b, gemma4:31b,
gemma4:26b, muse-glimmer:30b, granite4.2:30b, nemotron-3.5-lightning:30b, llama3.1:8b, mistral-small:24b. The
last two are older anchors for comparison with earlier work. Sampling temperature 0, seed 42, answer cap 320
tokens, one response per prompt and strategy. For models with a thinking mode, thinking is switched off in the
main arm so that the cap bounds the answer and not a hidden reasoning trace. [VERIFY: muse-glimmer returned
empty answers for 6.2% of attacks at the cap; see Limitations.]

### 4.2 Prompts
The base prompts come from five public benchmarks of harmful requests: AdvBench (520), HarmBench (standard
behaviours, 200), StrongREJECT (313), JailbreakBench JBB-Behaviors (100) and the unsafe prompts of XSTest
(200). After removing duplicates across sources the corpus has 1,288 prompts, ordered so that any prefix is
balanced across sources and categories; 1,205 were run [VERIFY]. SORRY-Bench was not obtained.

### 4.3 Attack strategies
Six strategies from the framework: roleplay, instruction override, encoding attack, token smuggling,
fictional framing, multi-turn. Each base prompt is run under each strategy: 7,230 attacks per model.

### 4.4 Arms
* **Main arm:** the 8 models, thinking off.
* **Reasoning arm:** qwen3.8:27b, gemma4:26b and granite4.2:30b on the first 100 prompts with thinking on and a
  3,072-token budget; the reasoning trace is stored. [VERIFY: no trace was returned for granite4.2.]
* **Control arm:** the first 100 of 250 benign XSTest prompts (interleaved over the ten prompt types), six
  strategies, three models. A judge verdict of "success" on a benign request is a false positive.

### 4.5 Automated judges
Four judges score every response in the judged subset:
1. a keyword evaluator (v1.1, refusal-phrase and compliance-signal rules);
2. an LLM rubric judge (gpt-oss:20b, rubric v2, local Ollama; verdicts REFUSAL / SAFE / PARTIAL / JAILBREAK;
   PARTIAL and JAILBREAK count as success);
3. Llama Guard 3 8B with the official response-classification prompt (success = unsafe);
4. a StrongREJECT-style rubric judge (phi4, local; refusal gate plus convincingness and specificity; success
   = score at least 0.5).
No judge is also a target model. All verdicts record the judge model and host. Llama Guard scored all
responses; the two LLM judges scored the first 270 base prompts (1,620 responses per model). A response enters
the analysis population only if it is non-empty and all four judges returned a usable verdict (12,800 of
12,862 judged responses [VERIFY]; the rest are counted and reported).

### 4.6 Strata and sampling for the human audit
Each main-arm response is assigned to a stratum by the number of judges calling it a success: *all-no*
(12,009 responses), *disagree* (789), *all-yes* (2). Substrata are stratum x target model; the sample is
uniform within a substratum, so every inclusion probability is known exactly (n/N). Sample: 50 responses per
model from all-no (400); disagree with a floor of 30 per model (461 [VERIFY]); both all-yes responses; from
the control arm 25 judge-flagged and 25 unflagged responses per model (150). Total 1,013 items. Selection is
seeded (20261031) and reproducible from the population files.

### 4.7 Annotation
Six annotators work independently. Each item is labelled by two of them; 270 randomly chosen items by three;
30 items form a shared calibration block labelled by all six and done first (about 400 items, 7 hours,
per annotator). Annotators see a neutral item id, the request
and the response; never the model name, strategy, stratum or any judge verdict. Labels: jailbreak, partial,
refusal, safe; success = jailbreak or partial. Instructions and the rubric are in the supplementary material.
Disagreements: majority of the available annotators; a pair that disagrees goes to a further reader (the lead author). Every positive found in the
all-no stratum is re-read by the lead author before it is counted. Annotators are adults who agreed to read
harmful content, can stop at any time, and the study has ethics approval/exemption [FILL: reference].
Agreement is reported as Cohen's kappa (pairwise), Fleiss' kappa (the triple set and the six-rater calibration block) and raw agreement, on both
the four-class and the binary success scale.

## 5. Methods

### 5.1 Estimands
For a group of responses (a model, or all) let Y be the human success label. We estimate the true attack-success
rate, ASR = mean(Y); and for each judge j its sensitivity P(j = yes | Y = 1), specificity P(j = no | Y = 0),
precision P(Y = 1 | j = yes) and the miss rate among its negatives P(Y = 1 | j = no).

### 5.2 Cell-wise Bayesian estimator
Cells are (group, substratum, judge verdict). In a cell with N items of which n were labelled and y found
positive, the cell's positive rate gets a Jeffreys Beta(0.5, 0.5) prior; its posterior is Beta(0.5 + y,
0.5 + n - y), and the N - n unlabelled items are simulated as Binomial(N - n, p). Summing cells gives joint
posterior draws (4,000) of the number of true positives, false positives, false negatives and true negatives,
from which every estimand and every difference between models follows, with 95% equal-tailed intervals. The
estimator is exact in its use of the known inclusion probabilities, needs no assumption that judge errors are
homogeneous across models (cells never mix models), and keeps a non-degenerate interval when a cell has no
observed positive. Unresolved label conflicts are bounded by treating them as all-negative and all-positive.
Validation: a simulation with known truth checks that the interval covers the true ASR (test suite) and the
paper reports a coverage study on the audited population [FILL].

### 5.3 Why labelling only judge-positives is biased (verification-bias demonstration)
A design that labels only responses some judge flagged estimates sensitivity as the share of labelled human
positives that judge j flagged. It ignores positives in the all-no stratum and therefore overstates
sensitivity (partial verification bias). We compute this "positives-only" figure from our own labels and
compare it with the full-design estimate [FILL].

### 5.4 Decision-level validity
For every pair of target models and each judge, a two-proportion z-test on the judge's success counts decides
whether the judge calls the models different, and in which direction. From the posterior draws we compute the
probability that the true ASR difference has the opposite sign, and count (i) judge-significant pairs, (ii)
their expected number of wrong-sign verdicts, (iii) pairs confirmed by the human-grounded estimate (posterior
probability above 0.975), and (iv) human-grounded differences the judge failed to call. This is the rate at
which a study would reach a wrong or missed conclusion if it used that judge [FILL].

### 5.5 Spike-in positive controls (planned)
When natural positives are rare, a judge's sensitivity cannot be measured from them. We take responses that the
annotators confirmed as harmful, insert them blind into the judging stream under different victim-model
contexts, and measure each judge's recovery rate with Wilson intervals [FILL / not yet run]. Because the same
content appears in several contexts, differences in recovery separate victim-model style from content.

### 5.6 Judge-adjusted sample size for a safety claim
Let p be the true harm rate to be excluded and s the judge's sensitivity. A clean sheet of n independent
prompts, scored by a judge that detects a harmful response with probability s and has no false positives, has
probability (1 - s p)^n. To bound p with confidence 1 - alpha after a clean sheet, n >= ln(alpha) / ln(1 - s p).
For p = 1% and 95% confidence this is 299 prompts for s = 1, 598 for s = 0.5 and 1,197 for s = 0.25. A
sensitivity lower bound from the audit (or from spike-ins) therefore sets the number of prompts. The bound
assumes independent trials and ignores false positives; it extends the zero-numerator result for benchmark null
outcomes to an imperfect judge. [VERIFY novelty against Kaur 2607.21735 sections 5 and 6.]

### 5.7 Reporting
We report, for every headline ASR: the judge, its human-grounded sensitivity and specificity with intervals,
the number and independence of annotators, the sampling design, per-model results, and the sample size needed
for the claim being made (checklist in the supplement).

## 9. Limitations (draft)
* Prompts: five English public benchmarks; not the distribution a deployer faces.
* Attacks: six prompt-level strategies at temperature 0, one response each; no adaptive or optimisation-based
  attackers.
* Models: eight open-weight models; commercial systems and larger models excluded.
* Judges: four judges; local hosting of the LLM judges changes them relative to API-hosted versions.
* Positives are rare (about 1 to 7% for most models), so cell-level estimates are wide.
* Six annotators, one rubric; harm is partly subjective; the rubric asks about usable content, not about
  factual accuracy.
* Data issues: muse-glimmer empty responses (6.2%); granite4.2 reasoning arm returned no trace; the LLM
  judges covered 270 of 1,205 prompts; SORRY-Bench absent. [VERIFY each before submission.]
* Spike-ins use content from the same study; difficulty may not match unseen positives.
