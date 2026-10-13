# Task brief: run the model study on the lab GPU machine

Read this whole file before doing anything. It is written so that a person or a
script runner can carry out the task end to end. Where it says "ask the human",
stop and ask the person who gave you this task.

## 1. Context (why this exists)

This repository is an authorisation-gated framework for measuring how reliable
automated "jailbreak judges" are. The study sends prompts from public research
benchmarks (AdvBench, HarmBench, StrongREJECT, JailbreakBench, SORRY-Bench, XSTest)
to open-weight models and records the answers. Judges then score those answers and the
scores are compared with human labels. The master plan is `research/STUDY_PLAN.md`.

* The study is approved by the supervisor and runs on lab hardware with permission.
* Every request is checked against a signed authorisation grant that lists the allowed
  target, models and strategies. That check is part of the method; never bypass it.
* The prompts are intentionally adversarial, and some model answers will contain
  harmful text. This is expected, authorised measurement work. You do **not** need to read
  the answers.

## 2. Your task

Run two commands on this machine (NVIDIA RTX 5090, 32 GB), within a budget of **70 to 80
GPU-hours** (about 3 days). The scripts do everything else: downloading datasets and models,
building the corpus, measuring speed, choosing how many prompts fit the budget, running in
stages, scoring, and writing the result zips. You are done when:

1. `uv run python research/remote_gpu/study.py run ...` has finished and printed `Finished`; and
2. the two files `outputs/results_for_researcher.zip` and `outputs/judges_for_researcher.zip`
   exist; and
3. you have sent the human the short report in section 7.

## 2a. Models (downloaded automatically by `run`)

Target models (open-weight, pulled through Ollama; these exact tags are what the signed grant allows):

| Model tag | Maker | Disk | Role |
|---|---|---|---|
| `qwen3.8:27b` | Alibaba | 18 GB | current generation (thinking-capable) |
| `gemma4:31b` | Google | 20 GB | current generation, dense |
| `gemma4:26b` | Google | 17 GB | current generation, mixture-of-experts |
| `muse-glimmer:30b` | Meta | 18 GB | current generation (thinking-capable) |
| `granite4.2:30b` | IBM | 18 GB | current generation (thinking-capable) |
| `nemotron-3.5-lightning:30b` | NVIDIA | about 18 GB | current generation, mixture-of-experts |
| `llama3.1:8b` | Meta | 5 GB | older anchor, for comparison with earlier work |
| `mistral-small:24b` | Mistral | 14 GB | older anchor, for comparison with earlier work |

The current-generation models reason before answering. In the main run the scripts switch thinking
**off** (so a 320-token cap measures the answer, not the reasoning). A separate **reasoning arm**
re-runs three of them (`qwen3.8:27b`, `gemma4:26b`, `granite4.2:30b`) on the first 100 prompts with
thinking **on** and a 3072-token budget, and stores the reasoning trace.

Judge models (also pulled automatically): `llama-guard3:8b` (5 GB), `gpt-oss:20b` (13 GB),
`phi4` (9 GB). Everything together is about 160 GB. Only models up to about 32B are used,
because the machine has one 32 GB GPU. If a tag cannot be pulled, report it; do not substitute.

## 3. Hard rules

* **Do not read, print, open, summarise, or paste the contents of any file in `outputs/`,
  `research/data_journal/`, `validate_in/` or `research/judge_reliability/out/*.json`.** To
  check progress use only `study.py status`. Do not echo model answers into the conversation or logs.
* **Never print, log, or commit the signing key or the `.env` file.** Ask the human to create
  `.env` themselves (section 4, step 3) so the key never passes through you.
* **Never pass `--accept-terms` yourself.** It is the human operator's confirmation that they have
  read the datasets' terms. Show the human the output of `uv run python scripts/fetch_benchmarks.py --list`
  and let them run `prepare` with the flag, or tell you explicitly to.
* **Never commit or push anything** from `outputs/`, `research/data_journal/` or `.env`. Do not
  run `git add -A`. You normally have no reason to commit anything at all.
* **Do not change** prompts, models, the model list, seed, temperature, token limit, variations
  count, strategies, judge prompts, or any file under `core/`, `strategies/`, `policy/`,
  `models/`, `main.py`. The study depends on these being fixed.
* **Do not work around the authorisation check.** If you see `Authorization signature is
  invalid`, `model is outside scope`, or `authorization is not active`, stop and ask the human.
  Never edit, re-sign, or regenerate a grant or key, and never disable the check.
* Do not expose Ollama to the network (keep it on `127.0.0.1`). Do not install anything beyond
  what section 4 lists. Do not run other models or other scripts.
* Ignore `RUNBOOK.md` and `setup_gpu_box.sh` in this folder. They describe a different
  plan (remote SSH operation) that is not being used.

## 4. Setup (once, Ubuntu)

The machine runs Ubuntu. Commands that need `sudo` must be run by the human or approved by them.

1. Prerequisites: `git`, `curl`, `tmux`, `uv` (https://astral.sh/uv/install.sh), Ollama
   (`curl -fsSL https://ollama.com/install.sh | sh`) and a working `nvidia-smi` (driver 570 or newer
   for the RTX 5090). Install only what is missing.
2. `git clone https://github.com/aljabid/jailbreak-framework.git`, `cd jailbreak-framework`,
   then `uv sync --locked`.
3. **Ask the human** to create a file named `.env` in the repository root containing exactly
   one line, `JBF_AUTHORIZATION_SIGNING_KEY=<key>`, using the key the researcher sent them
   privately. Wait until they confirm. Do not ask them to paste the key to you.
4. Configure the Ollama systemd service (settings in a shell do not reach it). Ask the human for a
   folder on a disk with 200 GB free, then: `sudo mkdir -p <folder> && sudo chown -R ollama:ollama <folder>`,
   `sudo systemctl edit ollama` and add
   `[Service]` / `Environment="OLLAMA_NUM_PARALLEL=4"` / `Environment="OLLAMA_MODELS=<folder>"`,
   then `sudo systemctl restart ollama`. Keep Ollama on `127.0.0.1`.
5. Prevent sleep: `sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target`.
6. Optional: if the human has a Hugging Face account that accepted the SORRY-Bench terms, they
   set `HF_TOKEN` in the environment. Otherwise that one dataset is skipped; that is fine.

## 5. Run

1. **Prepare.** Ask the human to run (or to tell you to run) 
   `uv run python research/remote_gpu/study.py prepare --accept-terms`. It ends with `Ready`.
   If a dataset cannot be fetched it prints the path to place the file by hand; ask the human.
2. **Run** as a background process that survives your session (use `tmux new -s study`, or
   `nohup ... &`), logging to a file:
   `uv run python research/remote_gpu/study.py run --budget-hours 75`.
   Do not hold a foreground command open for hours.
3. **Monitor** every 30 to 60 minutes with `uv run python research/remote_gpu/study.py status`,
   and read only the last few lines of the log. Keep the machine awake; avoid other heavy GPU jobs.
4. The scripts are resumable. If anything stops (crash, reboot, power cut), run the same
   command again. Report to the human after `prepare`, after each stage, and at the end.
5. If the human supplied a `validate_in/` folder, `run` processes it at the end automatically.

## 6. When something goes wrong

| Symptom | Action |
|---|---|
| `Cannot start:` followed by a list | fix exactly what it lists (missing file, Ollama not running, key not set) |
| a dataset could not be fetched | ask the human to place the file at the printed path, then rerun `prepare` |
| `could not pull <model>` | model name may have changed on ollama.com/library; report the name to the human, do not substitute another model |
| `Authorization signature is invalid` | stop; ask the human to re-check the key in `.env` (no spaces, 64 characters) and run `git pull` for the latest grant |
| `model is outside scope` or `not active` | stop; run `git pull`; if it persists ask the human |
| out of memory / very slow | check `nvidia-smi`; another process may be using the GPU; ask the human before killing anything |
| anything else unexpected | stop and report the last 30 lines of output; do not improvise fixes |

If you hit an error you cannot resolve in two attempts, stop and ask the human.

## 7. Reports and hand-over (short, no model text)

Send the human: the output of `study.py status`, hours used, any model that needed a restart or
could not be used, and any warnings. At the end tell the human to send these files to the
researcher **privately** (not through GitHub):

* `outputs/results_for_researcher.zip` (answers, Llama Guard verdicts, data-version records);
* `outputs/judges_for_researcher.zip` and `outputs/judges_think_for_researcher.zip` (LLM judge verdicts only).

The human should delete the model folder, `outputs/` and `validate_in/` after the researcher
confirms receipt.
