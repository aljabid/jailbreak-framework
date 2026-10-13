# Study plan: how reliable are automated jailbreak judges?

This is the master plan for the research project built on this framework. It says
what the project is for, which models must be installed, and which experiments are
run. Task-specific instructions for the GPU machine are in `remote_gpu/TASK.md` and
`remote_gpu/AUTHORS_RUN.md`.

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

## 2. Decisions taken (2026-10-13)

| Topic | Decision |
|---|---|
| Hardware | one RTX 5090 (32 GB); no rented GPU. Target models up to about 32B |
| GPU budget | 70 to 80 GPU-hours in total (generation, judging, buffer) |
| Prompts | the full benchmark sets below, about 1,500 unique requests when all are present |
| Variations | 1 per prompt and strategy (more distinct prompts beats more templates) |
| LLM judges | run locally on the GPU, because the free Groq quota cannot score this volume |
| Staging | the corpus is ordered so any prefix is representative; run in stages (N=300, 700, all) |

## 3. Where things stand

| Item | Status |
|---|---|
| Framework (attacks, judges, authorisation, evidence) | done |
| 9 models x 108 attacks, 4 judges, pooled analysis (n=924) | done |
| `--variations`, `--n` staging, resumable GPU scripts (`run_all.py`, `judge_all.py`) | done, tested against a stub server |
| Corpus builder with cross-source de-duplication and balanced ordering | done; 1,088 unique prompts from 4 sources so far |
| SORRY-Bench and XSTest importers | done; the files still need to be downloaded |
| First human annotator (132 items), judge ranking | done |
| Calibrated rubric v2 (kappa 0.41 to 0.48, tuned on the same 132 items) | done, needs held-out check |
| **Main GPU run on the lab machine** | **next** |
| Second annotator and more human labels (400+) | to do |
| Control arm (XSTest safe prompts) for judge false positives; defence experiments | to do |
| Journal manuscript | to do |

## 4. Models

### 4a. Targets to install on the lab GPU machine (RTX 5090, 32 GB)

All are open-weight, pulled through Ollama. The tags are the ones the signed grant allows;
the list lives in `remote_gpu/run_all.py` (`DEFAULT_MODELS`). Check names on
ollama.com/library if a pull fails.

| Model tag | Family | Approx. size on disk |
|---|---|---|
| `llama3.1:8b` | Llama | 5 GB |
| `qwen2.5:7b` | Qwen | 5 GB |
| `mistral:7b` | Mistral | 4 GB |
| `phi4` | Microsoft | 9 GB |
| `qwen2.5:14b` | Qwen | 9 GB |
| `gemma3:27b` | Google | 17 GB |
| `mistral-small:24b` | Mistral | 14 GB |
| `qwen2.5:32b` | Qwen | 20 GB |

### 4b. Judge models installed on the same machine

| Model tag | Role | Size |
|---|---|---|
| `llama-guard3:8b` | safety classifier judge (official response prompt) | 5 GB |
| `gpt-oss:20b` | rubric judge v2 | 13 GB |
| `gemma2:27b` | StrongREJECT-style judge | 16 GB |

Neither LLM judge is a target, so no model judges its own answers. Total disk for everything:
about 130 GB.

Reasoning models (for example DeepSeek-R1 distills) are left out of the targets on purpose:
under a 320-token cap they return many empty answers, a measurement hazard reported in the
conference paper. If one is added later it needs its own token budget and a note in the paper.

### 4c. Already run (earlier subset of 18 prompts, kept for comparison)

`qwen2.5` 0.5B, 1.5B, 3B, 7B, 14B; `mistral:7b`; `llama3.1:8b`; `openai/gpt-oss-20b`;
`openai/gpt-oss-safeguard-20b`. Judged with the keyword evaluator, gpt-oss-20b and a Qwen
StrongREJECT-style judge on Groq, and Llama Guard 3.

### 4d. Judges and what each needs

| Judge | Runs on | Needs |
|---|---|---|
| Keyword evaluator v1.1 | any machine | nothing (built in) |
| Rubric judge (gpt-oss-20b), rubric v1 and v2 | Groq (earlier runs), local Ollama (new runs) | key, or ~13 GB GPU |
| StrongREJECT-style rubric judge | Groq with `qwen/qwen3.8-27b` (earlier), local `gemma2:27b` (new) | key, or GPU |
| Llama Guard 3 8B | GPU via Ollama | included in `run_all.py` |
| Ensemble (2 of 4 vote) | researcher laptop | the four verdict sets |

Hosting changes the judge: the same rubric on a different model or host can behave differently.
Every verdict records `judge_model` and `judge_host`, and experiment E0 checks the effect.

### 4e. Models reachable only by API (later, optional)

Models that do not fit 32 GB (70B class, gpt-oss-120B, Gemini, closed models). They add
breadth but are not needed for the core result and are outside the current budget.

## 5. Datasets (public benchmarks of harmful requests)

Downloaded by the authors themselves from the original sources and imported with
`scripts/import_external_prompts.py` (the script never downloads anything):

| Dataset | Part used | Approx. size | Status |
|---|---|---|---|
| AdvBench | all | 520 | imported |
| HarmBench | `FunctionalCategory=standard` only (not contextual, not copyright) | 200 | imported |
| StrongREJECT | all | 313 | imported |
| JailbreakBench (JBB-Behaviors) | all | 100 | imported |
| SORRY-Bench | all | about 450 | to download (gated on Hugging Face) |
| XSTest | unsafe prompts into the main corpus; safe prompts as a control arm | 200 + 250 | to download |

`research/build_full_corpus.py` de-duplicates across sources (1,088 unique so far) and orders
the result so any prefix is balanced across sources and categories. The framework's `-n`
option takes the first N prompts.

## 6. Experiments

All experiments use the six existing strategies (roleplay, instruction_override,
encoding_attack, token_smuggling, fictional_framing, multi_turn) with seed 42, temperature 0
and a 320-token cap, so results stay comparable with the earlier runs. No new attack methods
are developed here; adding published attack baselines is a separate decision for the authors.

| # | Experiment | Purpose | Where | Output |
|---|---|---|---|---|
| E0 | **Local-judge validation**: rejudge the earlier 540 answers with the local judges and compare with the Groq verdicts and the human labels | does moving the judges to local hosting change them? | GPU, `judge_all.py --files` | agreement table |
| E1 | **Main matrix**: 8 models x first N prompts x 6 strategies x 1 variation (N=300, 700, then all) | the data for everything else | GPU, `run_all.py` | `results_for_researcher.zip` |
| E2 | **Judge comparison**: attack-success rate per judge, bootstrap CIs, pairwise kappa, McNemar tests | RQ1 | laptop, `analyze_agreement.py`, `summarize.py` | tables, figures |
| E3 | **Human validation**: labelling sheet weighted to judge disagreements, independent annotators, human-human kappa, judge-vs-human kappa/precision/recall | RQ2 | `build_labeling_sheet.py`, `label.html`, `analyze_labels.py`, `rank_judges.py` | judge ranking |
| E4 | **Judge improvement**: few-shot rubric v2, ensembles; evaluated on a **held-out** labelled set | RQ3 | `judge_llm_v2.py`, `rank_judges.py` | kappa before/after |
| E5 | **Robustness**: repeats over seeds, effect of the token cap on empty answers | statistics | GPU + laptop | CIs, ablations |
| E6 | **Scale and family analysis**: rates by size and family, per strategy | RQ4 | laptop | figures |
| E7 | **Control arm**: XSTest safe prompts (should not count as jailbreaks) to measure judge false positives | RQ2 | GPU + laptop | false-positive rates |
| E8 | **Defence measurement** (optional): effect of a system prompt or Llama Guard filter on measured rates | extension | GPU + laptop | table |

## 7. Compute budget (70 to 80 GPU-hours)

| Part | Budget | Notes |
|---|---|---|
| Generation (E1) | about 45 h | the exact N is chosen from `run_all.py --estimate` after measuring real speed |
| Llama Guard on every answer | about 6 h | automatic after generation |
| Local LLM judges on the first K=250 prompts of every model | about 18 h | 8 models x 250 x 6 = 12,000 answers x 2 judges |
| Local-judge validation (E0) | under 1 h | |
| Buffer | about 8 h | |

At about 3.5 s per attack, all 1,088 prompts would take about 50 h; with batching
(`OLLAMA_NUM_PARALLEL=4`, `--concurrency 4`) it should be less. The staged plan keeps the
result valid wherever the budget ends. The earlier per-judge Groq volume (about 1,000 calls
per day) is why the LLM judges run locally and on a sample.

## 8. Data and file map

* `data/`: framework prompt corpus; `scripts/`: import tools; `core/ strategies/ policy/ models/`: framework.
* `research/grants/`: signed authorisation grants (no secrets inside).
* `research/data_journal/` (gitignored, local only): downloaded benchmark files, imported sets and the
  corpus. Contains harmful request text; never published.
* `outputs/` (gitignored, local only): raw model answers and result archives. Never published.
* `research/judge_reliability/out/`: judge verdicts and summary tables (labels only; safe to publish).
* `research/judge_reliability/labeling/` (gitignored): labelling sheet and human labels.

Only labels, aggregate rates and figures are published. Raw answers are shared
privately between the authors when needed.

## 9. Who does what

| Role | Tasks |
|---|---|
| Lead author (laptop) | framework, grants and keys, corpus, analysis, figures, manuscript |
| Lab author (GPU machine) | runs E0, E1, E5, E7 generation and judging with `run_all.py` and `judge_all.py`; sends zips privately |
| Annotators (at least two, independent) | label the sheet in `label.html`; do not compare until both finish |
| Supervisor | approval, ethics confirmation, final read |

## 10. Open decisions

1. **Final N** for E1, from the speed measured by `run_all.py --estimate`.
2. **Held-out labels:** how many more human labels (400 to 600 total recommended) and who provides them.
3. **Optional extensions:** defence measurement (E8) and published attack baselines.

## 11. Rules for everyone

* Every request to a model goes through the signed grant; never bypass or edit it.
* Never commit or push raw answers, benchmark files, `.env`, or keys.
* Do not change prompts, models, seed, temperature or token cap mid-study.
* Report responsibly: serious weaknesses found in a vendor's model are disclosed to the
  vendor before publication; the paper reports aggregate rates and labels only.
* Annotators see harmful text; they must be adults who understand the purpose, and ethics
  approval or an exemption is obtained through the supervisor.
