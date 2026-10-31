# Preliminary audit results (2026-11-01) — NOT FINAL

Status: provisional. The six returned label files contain only two distinct sets of labels (see below), so
the numbers below treat them as two raters and must be re-checked by an independent human reader before any
use in the paper. Aggregates only; no response text.

## Integrity of the returned files
* Files A, D, F carry identical labels and identical notes wherever they overlap (130 to 131 shared items, 100%
  agreement); files B, C, E likewise (130 to 133 shared items, 100% agreement, identical notes). Across the two
  groups agreement is 89 to 93% (4-class).
* All six files were modified within 13 minutes of each other. About 400 items per annotator cannot be read in
  that time, so the files appear to be copies or to come from automated labelling. Provenance is unknown to me.
* Consequence: effective number of independent raters = 2 (group X = A/D/F, group Y = B/C/E). If either group
  is an AI system, the labels are not human ground truth and must be described as such or replaced.

## Two effective raters (X, Y)
* Items labelled by X: 858, by Y: 857, by both: 702, by neither: 0.
* X vs Y on the 702 shared items: exact 4-class agreement 91.6%, kappa 0.85; success scale agreement 97.0%,
  kappa 0.88. Disagreements: 19 where X says success and Y does not, 2 the other way.

## Provisional estimates (unresolved conflicts counted as negative / positive)
| Quantity | Value (95% interval) |
|---|---|
| True ASR, pooled over 8 models | 4.6% [3.3, 6.3] to 5.4% [4.0, 7.2] |
| Raw judge ASR | keyword 0.5%, StrongREJECT-style 0.8%, gpt-oss 3.8%, Llama Guard 4.1%, any judge 6.2% |
| Sensitivity | keyword 9.8%, StrongREJECT-style 6.9%, gpt-oss 31.7%, Llama Guard 26.8%, any-of-four 41.9% [29.7, 56.9] |
| Specificity | 95.5% to 99.9% |
| All-judges-say-no stratum | 5 to 11 positives of 400 labelled (1.3% to 2.8%); the strict count (both raters agree) is 5 |
| Disagree stratum | 130 to 147 of 461 positive (about 30%); mistral-small 90 of 162 |
| Control arm, judge-flagged | 0 of 75 human-positive (all judge flags on benign prompts are false positives) |
| Positives-only shortcut | inflates sensitivity by 11 to 46 points relative to the full design |
| Decision level | 19 to 22 of 28 model pairs called different by an LLM/guard judge; about 2.5 to 3.7 of those expected to have the wrong sign |

## Reading
If the labels hold, single judges recover only a minority of true successes, and even the union of four judges
misses a sizeable part, concentrated in fictional framing, roleplay and token smuggling on mistral-small,
gemma4:31b and nemotron. This is a different picture from the old 23-label pilot (0 of 23). Both rest on very
few positives; the decisive items are re-read by the lead author (build_recheck_sheet.py, 29 decisive items
plus 80 random ones).
