# Deep research round (2026-10-19): sources outside the jailbreak literature, and a new idea

Working document for the authors. Method: roughly 30 web searches and about 20 page fetches across
jailbreak evaluation, LLM-judge statistics, epidemiology and diagnostic-test methodology, software
fuzzing, auditing and acceptance sampling, surrogate-endpoint theory, cryptographic attestation,
regulation (EU, UK), insurance and industry blogs. Mostly abstracts and search snippets; full texts were
read only for Kaur (2607.21735) and the earlier round. Books were not read (only open web sources).
Every "not found" below means "not found by these searches", not "does not exist".

## 1. What the outside fields already have (so none of it is ours to claim)

| Field | Tool | Source | Status in LLM safety |
|---|---|---|---|
| Diagnostic-test studies | partial verification bias: if only test-positives are checked against the gold standard, sensitivity is inflated (Begg and Greenes 1983) | classic | No application to jailbreak-judge validation found. Schwinn et al. 2603.06594 labelled judge-positives only |
| Survey statistics | double (two-phase) sampling with a fallible classifier and a verified subsample; optimal allocation (Tenenbein 1972) | classic | Generic LLM versions exist: PPI, Rogan-Gladen (Lee 2511.21140, Chen 2601.05420), Neyman allocation with judges (2605.23362, 2605.16354, 2605.10075), stratified/active inference |
| Diagnostic statistics | zero-numerator bound, "rule of three" (Hanley and Lippman-Hand 1983) | classic | Kaur 2607.21735 derives "evidential ceiling" of a clean benchmark; assumes the scoring rule is correct |
| Software testing | species discovery and Good-Turing residual risk for fuzzing (Boehme, STADS; ICSE 2026 dependency-aware version) | 1803.02130 | No application to jailbreak discovery found; "Blind-Spot Mass" 2604.05057 uses Good-Turing for ML deployment coverage |
| Epidemiology | capture-recapture / multiple-systems estimation of unobserved cases | classic | One pre-registered test on benchmark label errors: well calibrated but too imprecise (negative result, GitHub ParitKansal/label-error-capture-recapture) |
| Clinical trials | surrogate endpoints: a proxy is valid only if the effect on the proxy predicts the effect on the true endpoint across trials (Prentice, Buyse trial-level surrogacy) | classic | Not applied to LLM judges in anything found |
| Rare-event simulation | importance sampling for harmful-output probabilities (Wu and Hilton 2410.13211; 2604.22167; 2607.18454; 2610.19202) | arXiv | Treats the harm judge as truth |
| Psychometrics | item response theory for safety benchmarks (2606.20626, 2608.05086) | arXiv | Judge error treated as noise |
| Reliability engineering | five-nines sampling by cross-entropy (Kim, Kolter 2605.11209) | arXiv | Judge not modelled |
| Cryptography | TEE-based attestable audits of safety benchmarks (2506.23706); zero-knowledge proofs of inference | arXiv | Exists; our signed manifest is weaker and must not be sold as new |
| Medicine | STARD reporting, QUADAS-2 bias assessment, spectrum bias | guidelines | No LLM-judge version found |
| Hierarchical models | prompt-level random effects, per-prompt variance dominates at temperature 0 (2608.28502; 2510.05709) | arXiv | Judge error and generation randomness not decomposed in one model |

## 2. Regulatory and business facts that matter

* EU General-Purpose AI Code of Practice, Safety and Security chapter, Measure 7.3: model reports must
  document evaluation procedures, scoring methods and **evaluation score comparisons with human
  baselines**; Article 55 requires adversarial testing for systemic-risk models; the Code is voluntary;
  enforcement possible from August 2026. It names no ASR metric. A protocol that produces a human-baseline
  comparison with uncertainty fits the wording.
* UK: Trusted Third-Party AI Assurance Roadmap (September 2025); a Centre for AI Measurement at NPL announced
  January 2026 to develop testing and validation standards; first ISO/IEC 42001 accreditation (BSI,
  January 2026). The roadmap itself lists unresolved quality of assurance as a problem.
* Evidence that headline jailbreak numbers are fragile: ASR moved from 2% to 58% by changing only an ordinary
  system prompt (2608.30748, seven models, three attacks); the same model ranged 0 to 94% across attacks
  (benchmark paper in the 2026 SoK literature).
* Vendor claims of "no universal jailbreak after thousands of red-team hours" (Anthropic constitutional
  classifiers, 3,000+ hours, then 1,700 hours and 198,000 attempts) are zero-numerator statements whose
  statistical meaning is not spelled out in the sources seen.
* I found no market-size data and no evidence that insurers require red-team reports; do not claim either.

## 3. What this does to our position

Everything statistical in our plan is classical or already adapted to LLM judges. A paper that claims a new
estimator will be rejected. What remains open, as far as these searches show:
1. no jailbreak study labels judge-negatives at scale (verification bias is present in published designs);
2. no joint treatment of judge error with the null-result ("clean benchmark") certification of Kaur;
3. judge validity is judged at the item level (accuracy, kappa), never at the level of the **decision**
   the study is used for (is model A less safe than B?), although Chouldechova and Fiedler show this is what
   matters;
4. sensitivity cannot be estimated from natural positives in the regime that matters (ASR near zero).

## 4. New idea: judge-adjusted safety claims (working title)

> *How many prompts and how many human labels does a jailbreak safety claim need?* A diagnostic-accuracy
> framework for automated judges.

Five parts, each small, together one paper:

1. **Verification-bias-free design.** The stratified audit of our plan (large all-judges-say-no stratum),
   with a short demonstration of how a positives-only design inflates sensitivity, using our own data
   (subsample the positives-only labels and compare).
2. **Spike-in positive controls.** To estimate a judge's sensitivity when natural positives are rare,
   insert responses already confirmed harmful by humans into the stream of other models (blind to the
   judge) and measure how often each judge recovers them. Because the same harmful content is placed in
   different victim-model contexts, this is a controlled test of differential misclassification
   (does sensitivity depend on the victim model's style or on the content?). Warning from the literature:
   recall depends on how elicitable the content is ("Recall Is Not Protection", 2609.05797), so spike-ins
   must be realistic and span difficulty. No source found that does this.
3. **Judge-adjusted evidential ceiling.** Extend Kaur: with judge sensitivity s and specificity t, a clean
   sheet over n prompts at true harm rate p has probability about (1 - s p)^n of being observed. Example,
   certifying p at most 1% with 95% confidence: n = 298 with a perfect judge, 598 at s = 0.5, 1,197 at
   s = 0.25. So the sensitivity lower bound (from part 2) sets the sample size. A short derivation plus a
   calculator is the deliverable.
4. **Decision-level validity.** Replace "judge accuracy" by the rate at which a judge-based comparison
   reaches the wrong sign or the wrong significance verdict relative to the human-grounded estimate, over
   all model pairs and strategies (28 pairs x 6 strategies in our data). This is trial-level surrogacy in
   the clinical sense. Our preliminary stability numbers (41% significance disagreement, 0% reversals on the
   old data) are the starting point.
5. **STARD-style reporting checklist** for jailbreak judges (spectrum, verification, blinding, number and
   independence of annotators, intervals, per-cell results), mapped to EU Code Measure 7.3. Released with
   the labels and a calculator.

Why this could pass as a contribution in a security journal: it answers a practical question (what may a
red-team result be used to claim), it is anchored in a human-labelled study of current models, it brings
established methodology from medicine and survey statistics, and it ties to a named regulatory requirement.

Why it may not: parts 1 and 3 are applications of classical results; parts 2 and 4 are new designs but
unproven; Kaur, Chouldechova, Fiedler and Schwinn are close neighbours; the venue may ask for a security
contribution rather than a measurement one.

### What each part needs
| Part | Needs | GPU | Labels |
|---|---|---|---|
| 1 | the planned audit | no | yes (planned) |
| 2 | human-confirmed positives from the audit; a blind insertion script | no | reuses audit |
| 3 | part 2; algebra and a calculator | no | no |
| 4 | per-model/strategy labels, Bayesian cell model | no | yes (planned) |
| 5 | writing | no | no |
Extra, optional: a repeat run at temperature above zero on a subset to separate generation randomness from
prompt effects and judge error (hierarchical model); about 3 GPU-hours.

### Ideas considered and parked
* Capture-recapture on judge overlap: as a test of whether judge overlap predicts human-measured misses
  (likely not, since judge errors are correlated); cheap add-on once labels exist, not a headline.
* Good-Turing residual risk for attack discovery: relevant to red-team effort claims, but detached from
  judge error; park.
* Zero-knowledge proofs of evaluation: exists (TEE, ZK); out of scope.
* IRT for prompts: exists; could be used inside part 4 to weight prompts.

## 5. Honest status of the search
Searches surfaced abstracts and snippets; arXiv identifiers and numbers are as returned and must be verified
before citation. Several result lists included vendor blogs and aggregators, which I did not rely on. No
books or paywalled sources were read.

## 6. References to verify (identifiers as returned)
2506.23706, 2607.21735, 2604.21854, 2609.20538, 2608.30748, 2609.28859, 2606.19057, 2604.05057, 2605.11209,
2605.12869, 2602.11786, 2608.02786, 2609.28335, 2606.20626, 2608.05086, 2410.13211, 2604.22167, 2607.18454,
2610.19202, 2605.23362, 2605.16354, 2605.10075, 2604.17267, 2606.08418, 2609.05797, 2608.28502, 2510.05709,
2605.14418, 2605.05058, 2506.10597, 2501.18837, 2601.04603, 1803.02130.
