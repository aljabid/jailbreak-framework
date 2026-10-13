# Running the study on the lab GPU machine

Thank you for helping. The work runs in stages with a total budget of **70 to 80 GPU-hours**
(about 3 days of wall time) and about **130 GB of disk**. You start each stage with one
command and check on it now and then. `TASK.md` has the same plan in a form that can be
handed to a script runner; `STUDY_PLAN.md` explains what the whole project is for.

What this is: an authorised red-teaming measurement study (supervisor-approved). The scripts
send prompts from public research benchmarks to open models running locally on this machine,
record the answers, and score them. The study measures how reliable automated "jailbreak
judges" are; it does not publish any harmful text.

## Author's instructions

*(Written by the researcher. Edit this section to add anything specific before sending.)*

* Do the smoke test first, then the budget estimate, then stage 1. Report after each stage.
* Do not change any settings, prompts or models; the study depends on them being fixed.
* If something unexpected happens, stop and message me instead of working around it.
* Contact: `<name, phone, email>`

## What you need from the researcher (sent privately, not on GitHub)

1. The `signing key`, a 64-character string. It goes into `.env` (setup step 3).
2. `journal_grant_v3_signed.json` in `research/grants/` (it may already arrive with `git pull`).
3. `journal_full_corpus.json` in `research/data_journal/`.
4. For the optional validation part: a folder `validate_in/` with response files.

## One-time setup

1. Install: Git, Python 3.10+, [uv](https://docs.astral.sh/uv/), [Ollama](https://ollama.com),
   and an NVIDIA driver that supports the RTX 5090 (570 or newer). Check with `nvidia-smi`.
2. Get the code:

   ```
   git clone https://github.com/aljabid/jailbreak-framework.git
   cd jailbreak-framework
   uv sync --locked
   ```

3. Create a file named `.env` in the project folder with exactly one line
   (use the real key from the researcher; never share or commit this file):

   ```
   JBF_AUTHORIZATION_SIGNING_KEY=PASTE_THE_KEY_HERE
   ```

4. Put the files from the researcher in place (create `research/data_journal` if needed).
5. Start Ollama with parallel requests and, if the default drive is small, a model folder on a
   big disk. Set `OLLAMA_NUM_PARALLEL=4` and `OLLAMA_MODELS=<folder with 150 GB free>`
   **before** starting Ollama. Do not expose Ollama to the network.

## The stages

Each script is resumable: after any stop, run the same command again. On Linux use `tmux`
or `screen`; keep the machine awake; avoid other heavy GPU jobs.

1. **Smoke test (2 minutes)**: must end with `Smoke test passed`.

   ```
   uv run python research/remote_gpu/run_all.py --smoke
   ```

2. **Budget estimate (about 15 minutes)**: times a small real run per model and projects hours.
   Send the printed table to the researcher, who may choose a smaller N.

   ```
   uv run python research/remote_gpu/run_all.py --estimate --n 1088 --hours 45
   ```

3. **Stage 1**: generate answers for the first 300 prompts, then judge them.

   ```
   uv run python research/remote_gpu/run_all.py --n 300
   uv run python research/remote_gpu/judge_all.py --judge-n 250
   ```

   Report to the researcher before going on.

4. **Stage 2**: `uv run python research/remote_gpu/run_all.py --n 700` (reuses stage 1).
5. **Stage 3** (only if budget remains and the researcher agrees): `uv run python research/remote_gpu/run_all.py`.
6. **Validation (optional, under 1 hour)**:
   `uv run python research/remote_gpu/judge_all.py --files validate_in/*.json`
   (on Windows PowerShell list the files by name instead of `*.json`).

Progress at any time: `run_all.py --status` and `judge_all.py --status`.

## When it finishes

Send these two files to the researcher **privately** (Drive link, email, or similar). The
answers inside contain harmful content produced by the models.

* `outputs/results_for_researcher.zip`
* `outputs/judges_for_researcher.zip`

## Please do not

* commit, push, or post anything from `outputs/`, `research/data_journal/`, `validate_in/`, or `.env`;
* change the prompts, models, seed, or settings;
* share the signing key or the corpus file with anyone else.

## Troubleshooting

| Problem | What to do |
|---|---|
| `Authorization signature is invalid` | `.env` key is wrong or has spaces; paste it again with nothing around it |
| `model is outside scope` | the grant file is old or wrong; get the latest `journal_grant_v3_signed.json` |
| `could not pull ...` | model name changed on ollama.com/library; tell the researcher which one |
| Out of memory | something else is using the GPU; check `nvidia-smi` |
| Very slow | the GPU is not being used; check `nvidia-smi` while it runs |

After the study, delete the model folder, `outputs/` and `validate_in/` from this machine.
