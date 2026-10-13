# Study plan: how reliable are automated jailbreak judges?

This is the master plan for the research project built on this framework. It says
what the project is for, which models must be installed, and which experiments are
run. Task-specific instructions for the GPU machine are in `remote_gpu/TASK.md`.

## 1. Goal

When a paper says "model X was jailbroken Y% of the time", that number depends on
the **judge** that decides whether each answer counts as a jailbreak. Our earlier
results show the same answers get very different rates from different judges
(1.3% to 11.5% on 924 answers), and a simple keyword check misses most of what
humans call a jailbreak.

The project measures this, finds out which judges agree with humans, and shows how
to make a judge more reliable. It extends the conference paper (CSAM-2026) into a
journal article.

Research questions:

1. **RQ1.** How much does the reported jailbreak rate change with the choice of judge?
2. **RQ2.** Which judge agrees best with human annotators, and where do judges fail?
3. **RQ3.** Does a better judge (calibrated rubric, ensemble) close the gap, measured on
   labels it was not tuned on?
4. **RQ4.** Does the picture change across model families and sizes (0.5B to 32B)?

## 2. Where things stand

| Item | Status |
|---|---|
| Framework (attacks, judges, authorisation, evidence) | done |
| 9 models x 108 attacks, 4 judges, pooled analysis (n=924) | done |
| 138-prompt base corpus from public benchmarks | done |
| `--variations` (several distinct templates per prompt) | done |
| First human annotator (132 items), judge ranking | done |
| Calibrated rubric v2 (kappa 0.41 to 0.48, tuned on the same 132 items) | done, needs held-out check |
| **Main GPU run: 8 larger models on the 138-prompt corpus** | **next (lab GPU machine)** |
| Judging all new answers with every judge | after the GPU run |
| Second annotator and more human labels (400+) | to do |
| Defence experiments, statistics over repeats | to do |
| Journal manuscript | to do |

## 3. Models

### 3a. Targets to install on the lab GPU machine (RTX 5090, 32 GB)

All are open-weight, pulled through Ollama. The names below are the exact tags the
signed grant allows; the list lives in `remote_gpu/run_all.py` (`DEFAULT_MODELS`).
Check names on ollama.com/library if a pull fails.

| Model tag | Family | Approx. size on disk |
|---|---|---|
| `llama3.1:8b` | Llama | 5 GB |
| `qwen2.5:7b` | Qwen | 5 GB |
| `mistral:7b` | Mistral | 4 GB |
| `phi4` | Microsoft | 9 GB |
| `qwen2.5:14b` | Qwen | 9 GB |
| `gemma2:27b` | Google | 16 GB |
| `mistral-small:24b` | Mistral | 14 GB |
| `qwen2.5:32b` | Qwen | 20 GB |
| `llama-guard3:8b` (judge, not a target) | Meta | 5 GB |

Total about 90 to 100 GB. Reasoning models (for example DeepSeek-R1 distills) are left
out on purpose: under a 320-token cap they return many empty answers, a measurement
hazard reported in the conference paper. If one is added later it needs its own
token budget and a note in the paper.

### 3b. Already run (earlier subset of 18 prompts, kept for comparison)

`qwen2.5` 0.5B, 1.5B, 3B, 7B, 14B; `mistral:7b`; `llama3.1:8b`; `openai/gpt-oss-20b`;
`openai/gpt-oss-safeguard-20b`.

### 3c. Judges and what each needs

| Judge | Runs on | Needs |
|---|---|---|
| Keyword evaluator v1.1 | any machine | nothing (built in) |
| LLM judge (gpt-oss-20b), rubric v1 and v2 | Groq API, or locally in Ollama (`gpt-oss:20b`) | Groq key, or ~13 GB GPU |
| StrongREJECT-style rubric judge | Groq API (`qwen/qwen3.8-27b`), or a local Qwen | Groq key, or GPU |
| Llama Guard 3 8B (official response prompt) | GPU via Ollama | included in `run_all.py` |
| Ensemble (2 of 4 vote) | researcher laptop | the four verdict sets |

### 3d. Models reachable only by API (later, optional)

Larger or closed models that do not fit 32 GB (gpt-oss-120B on Groq, Gemini, Gemma 4,
Claude with API credit). They add breadth but are not required for the core result.

## 4. Experiments

All experiments use the six existing strategies (roleplay, instruction_override,
encoding_attack, token_smuggling, fictional_framing, multi_turn) with seed 42,
temperature 0 and a 320-token cap, so results stay comparable with the earlier runs.
No new attack methods are developed here; adding published attack baselines is a
separate decision for the authors.

| # | Experiment | Purpose | Where | Output |
|---|---|---|---|---|
| E1 | **Main matrix**: 8 models x 138 prompts x 6 strategies x 3 variations (2484 answers per model, 19,872 total) | the data for everything else | lab GPU, `run_all.py` | `results_for_researcher.zip` |
| E2 | **Judge comparison**: attack-success rate per judge, bootstrap CIs, pairwise kappa, McNemar tests | RQ1 | researcher laptop, `analyze_agreement.py`, `summarize.py` | tables, `fig_asr_by_judge.png` |
| E3 | **Human validation**: labelling sheet weighted to judge disagreements, two independent annotators, human-human kappa, judge-vs-human kappa/precision/recall | RQ2 | `build_labeling_sheet.py`, `label.html`, `analyze_labels.py`, `rank_judges.py` | judge ranking |
| E4 | **Judge improvement**: few-shot rubric v2, ensembles, optionally a larger judge; evaluated on a **held-out** labelled set (train/test split) | RQ3 | `judge_llm_v2.py`, `rank_judges.py` | kappa before/after |
| E5 | **Robustness and ablations**: repeat runs over seeds/temperatures, effect of token cap on empty answers, effect of variations and strategy | statistics, RQ4 | GPU + laptop | CIs, ablation tables |
| E6 | **Scale and family analysis**: rates by model size and family, per strategy | RQ4 | laptop | figures |
| E7 | **Defence measurement** (optional): how much a system prompt or Llama Guard input/output filter lowers measured rates, and whether judges still agree | extension | GPU + laptop | table |

## 5. Data and file map

* `data/`: framework prompt corpus; `scripts/`: import tools; `core/ strategies/ policy/ models/`: framework.
* `research/grants/`: signed authorisation grants (no secrets inside).
* `research/data_journal/` (gitignored, local only): downloaded benchmark files and the
  138-prompt corpus. Contains harmful request text; never published.
* `outputs/` (gitignored, local only): raw model answers. Never published.
* `research/judge_reliability/out/`: judge verdicts and summary tables (labels only; safe to publish).
* `research/judge_reliability/labeling/` (gitignored): labelling sheet and human labels.

Only labels, aggregate rates and figures are published. Raw answers are shared
privately between the authors when needed.

## 6. Who does what

| Role | Tasks |
|---|---|
| Lead author (laptop) | framework, grants and keys, judges on Groq, analysis, figures, manuscript |
| Lab author (GPU machine) | runs E1, E5 and E7 generation with `run_all.py`; sends zip privately |
| Annotators (at least two, independent) | label the sheet in `label.html`; do not compare until both finish |
| Supervisor | approval, ethics confirmation, final read |

## 7. Open decisions

1. **Judge budget (the main bottleneck).** Scoring 19,872 answers with two Groq judges is
   about 39,700 calls; at the free limit of about 1,000 calls per judge per day that is
   roughly 20 days. Options: (a) LLM-judge a stratified subset (for example 3,000
   answers); (b) run the LLM judges locally on the GPU through Ollama; (c) pay for API
   capacity. Option (b) is fastest but changes judge hosting, which must be stated in the paper.
2. **Variations per prompt:** 3 (recommended, more borderline answers) or 1 (about a third of the time).
3. **Prompt scale:** 138 prompts now; widen toward the full 520-prompt AdvBench set only if time allows.
4. **Held-out labels:** how many more human labels (400 to 600 total recommended) and who provides them.
5. **Optional extensions:** defence measurement (E7) and published attack baselines.

## 8. Rules for everyone

* Every request to a model goes through the signed grant; never bypass or edit it.
* Never commit or push raw answers, benchmark files, `.env`, or keys.
* Do not change prompts, models, seed, temperature or token cap mid-study.
* Report responsibly: serious weaknesses found in a vendor's model are disclosed to the
  vendor before publication; the paper reports aggregate rates and labels only.
* Annotators see harmful text; they must be adults who understand the purpose, and ethics
  approval or an exemption is obtained through the supervisor.

## 9. Rough compute and time

* E1 on the GPU machine: about 17 to 22 GPU-hours (1 to 2 days of wall time).
* Judging: dominated by the Groq limit unless decision 7.1 is resolved.
* Human labelling: about 1 to 1.5 hours per annotator per 130 items.
* Manuscript: written in parallel once E1 and E2 are finished.
