# Study plan: valid measurement of jailbreak success

This is the master plan for the research project built on this framework. It says what the
project is for, which models and datasets are used, which experiments are run, and how the
human labels are collected. Why the contribution is novel, and what is not novel, is in
`NOVELTY.md`. Instructions for the GPU machine are in `remote_gpu/TASK.md` and
`remote_gpu/AUTHORS_RUN.md`.

## 1. Goal and research questions

A reported jailbreak rate depends on the **judge** that decides whether an answer counts, and on
evaluation choices such as thinking mode and token budget. Several 2026 papers show that judges
disagree with humans, so that fact alone is not new. The project asks how to measure attack success
**validly**: with intervals that account for judge error, with a label budget, and with an audit of
which scientific conclusions survive a change of judge.

1. **RQ1.** How large and how uneven is the error of judge-based ASR across target models and attack
   strategies, and how much of the truth sits in the stratum that every judge calls safe?
2. **RQ2.** Can a stratified human sample plus several judges give a calibrated ASR with an interval
   that holds up (coverage near 95%), and how many human labels does that take?
3. **RQ3.** Which conclusions change with the judge: significance of model differences, size trends,
   strategy rankings?
4. **RQ4.** For reasoning models, do thinking mode, token budget and the judge's input (answer only or
   answer plus reasoning trace) change judge error and the calibrated ASR?

The paper extends the CSAM-2026 conference paper into a journal article.

## 2. Decisions taken (2026-10-13)

| Topic | Decision |
|---|---|
| Main contribution | calibrated, uncertainty-aware ASR protocol (C1 in `NOVELTY.md`); conclusion-stability audit (C2) and reasoning-era configuration audit (C3) support it |
| Hardware | one RTX 5090 (32 GB); no rented GPU; target models up to about 32B |
| GPU budget | 70 to 80 GPU-hours (generation, reasoning arm, judging, buffer) |
| Models | current-generation open models plus two older anchors (section 4) |
| Prompts | the benchmark sets in section 5, about 1,300 unique requests, about 1,750 with SORRY-Bench |
| Variations | 1 per prompt and strategy |
| Thinking | off in the main arm; a separate reasoning arm with thinking on and the trace stored |
| LLM judges | run locally on the GPU, because the free Groq quota cannot score this volume |
| Staging | the corpus is ordered so any prefix is representative; stages N=300, 700, all |
| Human labels | at least three annotators; stratified design in section 7 |

## 3. Where things stand

| Item | Status |
|---|---|
| Framework (attacks, judges, authorisation, evidence) | done |
| 9 older models x 108 attacks, 4 judges, pooled analysis (n=924) | done |
| `--variations`, `--n` staging, batched result writes, Windows file-lock retry | done |
| One-command driver `study.py` (prepare / run / status), dataset fetcher, budget-aware stages | done, tested against a stub server |
| Thinking switch, reasoning arm, trace capture, trace-aware judge input | done, tested against a stub server |
| Local LLM judges (`gpt-oss:20b`, `phi4`), Llama Guard 8B | done, tested against a stub server |
| Signed grant v4 for the current model list | done |
| Calibrated-ASR prototype (cell-Bayes, normal intervals, coverage check) | done on the old 132 labels |
| Conclusion-stability analysis | done on the old nine-model data |
| First human annotator (132 items), judge ranking | done |
| Rubric v2 (kappa 0.41 to 0.48, tuned on the same 132 items) | done, needs a held-out check |
| **Main GPU run on the lab machine** | **next** |
| Multi-annotator labels per section 7 | to do |
| Coverage study, heterogeneity analysis, full conclusion audit | after the GPU run and the labels |
| Journal manuscript | to do |

## 4. Models

### 4a. Targets (RTX 5090, 32 GB; all open-weight, pulled through Ollama)

The tags are exactly what signed grant v4 allows; the list is `DEFAULT_MODELS` in
`remote_gpu/run_all.py`. Check names on ollama.com/library if a pull fails.

| Model tag | Maker | Disk | Role |
|---|---|---|---|
| `qwen3.8:27b` | Alibaba | 18 GB | current generation, thinking-capable |
| `gemma4:31b` | Google | 20 GB | current generation, dense |
| `gemma4:26b` | Google | 17 GB | current generation, mixture-of-experts |
| `muse-glimmer:30b` | Meta | 18 GB | current generation, thinking-capable |
| `granite4.2:30b` | IBM | 18 GB | current generation, thinking-capable |
| `nemotron-3.5-lightning:30b` | NVIDIA | about 18 GB | current generation, mixture-of-experts |
| `llama3.1:8b` | Meta | 5 GB | older anchor (comparison with prior work) |
| `mistral-small:24b` | Mistral | 14 GB | older anchor |

Too large for 32 GB and therefore excluded: Mistral Large 4 (about 1T parameters), Mistral Medium 3.5
(128B), 70B-class models. The earlier nine-model runs (Qwen2.5 0.5 to 14B, Mistral 7B, Llama 3.1 8B,
gpt-oss-20B and its safeguard variant) stay as a comparison set.

### 4b. Thinking models: two arms

* **Main arm**: thinking off (`think: false`), 320-token cap, so the cap measures the answer. Models
  without a thinking mode are called without the field; a rejected field is retried automatically.
* **Reasoning arm**: `qwen3.8:27b`, `gemma4:26b`, `granite4.2:30b`, first 100 prompts, thinking on,
  3072-token budget, reasoning trace stored in each record. Judged with and without the trace shown.

### 4c. Judges

| Judge | Runs on |
|---|---|
| Keyword evaluator v1.1 | any machine |
| Rubric judge (`gpt-oss:20b`), rubric v1 and v2 | Groq (earlier runs), local Ollama (new runs) |
| StrongREJECT-style rubric judge | Groq `qwen/qwen3.8-27b` (earlier), local `phi4` (new; non-thinking, not a target) |
| Llama Guard 3 8B (official response prompt) | GPU via Ollama |
| Ensemble (2 of 4 vote) | laptop |

Hosting changes a judge. Every verdict records `judge_model` and `judge_host`, and experiment E0 measures
the effect. A newer safety classifier (`granite4.1-guardian:8b`) is a possible extra judge later.

## 5. Datasets (public benchmarks of harmful requests)

Fetched by the lab author with `study.py prepare --accept-terms` (sources, terms and citations:
`scripts/fetch_benchmarks.py --list`; the flag is the operator's confirmation that the terms were read) and
imported with `scripts/import_external_prompts.py`. Every file's SHA-256 is recorded in a manifest that
travels with the results.

| Dataset | Part used | Size | Status |
|---|---|---|---|
| AdvBench | all | 520 | imported |
| HarmBench | `standard` behaviours only | 200 | imported |
| StrongREJECT | all | 313 | imported |
| JailbreakBench (JBB-Behaviors) | all | 100 | imported |
| XSTest | 200 unsafe into the corpus; 250 safe as a control set | 450 | imported |
| SORRY-Bench | all | about 450 | to download (gated on Hugging Face) |

`research/build_full_corpus.py` removes duplicates across sources (1,288 unique with XSTest) and orders the
result so any prefix is balanced across sources and categories. The framework's `-n` takes the first N.

## 6. Experiments

All use the six existing strategies (roleplay, instruction_override, encoding_attack, token_smuggling,
fictional_framing, multi_turn), seed 42, temperature 0. No new attack methods are developed here.

| # | Experiment | Answers | Where | Status |
|---|---|---|---|---|
| E0 | local-judge validation: rejudge the earlier 540 answers locally, compare with the Groq verdicts | does hosting change a judge? | GPU, `judge_all.py --files` | ready |
| E1 | main matrix: 8 models x first N prompts x 6 strategies x 1 variation | the data for everything | GPU, `study.py run` | ready |
| E2 | judge comparison: raw ASR per judge, bootstrap CIs, kappa, McNemar | RQ1 | laptop, `analyze_agreement.py`, `summarize.py` | done on old data |
| E3 | human labelling by the stratified design of section 7, three annotators | RQ1, RQ2 | `build_labeling_sheet.py`, `label.html`, `analyze_labels.py` | design done, labels to do |
| E4 | calibrated ASR, per-cell judge error, coverage study, label-budget curves | RQ1, RQ2 | `calibrated_asr.py` (to extend) | prototype |
| E5 | conclusion stability: significance of model differences, size trends, strategy rankings under every judge | RQ3 | `conclusion_stability.py` | done on old data |
| E6 | reasoning arm and configuration audit: thinking on/off, token cap, judge input (answer vs trace) | RQ4 | GPU + laptop | ready |
| E7 | control arm: XSTest safe prompts, judge false-positive rate | RQ1 | GPU + laptop | importer ready, run script to do |
| E8 | judge improvement: rubric v2, ensembles, held-out check | extension | `judge_llm_v2.py`, `rank_judges.py` | partly done |
| E9 | defence measurement (system prompt, Llama Guard filter) | optional | GPU + laptop | not started |

## 7. Human-labelling design (needed for E3 and E4)

The first 132 labels (one annotator, disagreement-weighted) validate judges but cannot support ASR
estimation, because the stratum that every judge calls safe is 82% of the population and had 0 positives
among 23 labels. Target set (about 900 to 1,100 items):

| Stratum | Labels |
|---|---|
| all judges say no | 300 |
| judges disagree | 400 |
| all judges say yes | 60 |
| controls (XSTest safe) | 150 |
| coverage | at least 15 per (model x strategy) cell, spread across the above |

Each item is labelled by two of three annotators; 300 items by all three for Fleiss' kappa. Roughly 12 to
15 hours per annotator. Annotators label the response, not the request (`label.html` enforces this).

## 8. Compute budget (70 to 80 GPU-hours)

| Part | Budget | Notes |
|---|---|---|
| Main generation (E1) | about 39 h | N is chosen from the speed `study.py run` measures |
| Reasoning arm (E6) | about 6 h | 3 models x 100 prompts x 6 strategies, thinking on |
| Llama Guard on every answer | about 5 h | automatic |
| Local LLM judges on the first K prompts | about 18 h | K up to 250; main and reasoning arms |
| Local-judge validation (E0) | under 1 h | |
| Buffer | about 8 h | |

## 9. Data and file map

* `data/`, `scripts/`, `core/ strategies/ policy/ models/`: framework and tools.
* `research/grants/`: signed authorisation grants (no secrets inside).
* `research/data_journal/` (gitignored): downloaded benchmark files, imported sets, the corpus. Contains
  harmful request text; never published.
* `outputs/` (gitignored): raw model answers and result archives. Never published.
* `research/judge_reliability/out/`: judge verdicts and aggregate tables (labels only; safe to publish).
* `research/judge_reliability/labeling/` (gitignored): labelling sheet and human labels.

Only labels, aggregate statistics and figures are published. Raw answers move privately between authors.

## 10. Who does what

| Role | Tasks |
|---|---|
| Lead author (laptop) | framework, grants and keys, corpus, analysis, figures, manuscript |
| Lab author (GPU machine) | runs `study.py prepare` and `study.py run`; sends the zips privately |
| Annotators (at least three, independent) | label their assigned items in `label.html`; no comparing until all finish |
| Supervisor | approval, ethics confirmation, final read |

## 11. Open decisions

1. Three annotators: who, and how the 900 to 1,100 items are split.
2. Ethics approval or exemption for the annotators (through the supervisor).
3. Final N for E1, from the measured speed.
4. Venue, after the full literature review in `NOVELTY.md` section 7.
5. Optional extensions: E9 and published attack baselines.

## 12. Rules for everyone

* Every request to a model goes through the signed grant; never bypass or edit it.
* Never commit or push raw answers, benchmark files, `.env` or keys.
* Do not change prompts, models, seed, temperature or token cap mid-study.
* Serious weaknesses found in a vendor's model are disclosed to the vendor before publication; the paper
  reports aggregate rates and labels only.
* Annotators see harmful text; they must be adults who understand the purpose, with ethics approval or an
  exemption obtained through the supervisor.
