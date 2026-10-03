# Remote GPU box: one-time setup and remote operation

Goal: a lab machine with an RTX 5090 (32 GB) serves open-weight models to the
researcher's laptop. The friend sets it up **once** (about 45 minutes), then the
researcher operates it entirely from home. The design avoids needing anyone to
touch the machine again.

## Design in one picture

```
researcher laptop                         lab GPU box (Linux)
-----------------                         -------------------
framework (attacks, judges)  --SSH-->     sshd (key only, user "jbf")
http://127.0.0.1:21434  ==tunnel==>       Ollama on 127.0.0.1:11434 (loopback only)
                      \_ Tailscale private network _/
```

* Ollama is never exposed on the lab network or the internet. The only way in is
  an SSH key held by the researcher.
* The framework already allows loopback endpoints, so no code changes are needed:
  it just talks to `127.0.0.1:21434`, which the SSH tunnel forwards to the box.
* Models are pulled later, from home, over SSH. The friend does not download ~100 GB.

## 0. Researcher prepares (before the session)

1. Create a Tailscale account; install Tailscale on the laptop and sign in.
2. In the Tailscale admin console create an **auth key** (Settings > Keys): one-use,
   expiry 7 days. Give it to the friend over a private channel, not a public chat.
3. Generate a dedicated SSH key on the laptop (PowerShell):
   `ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\id_ed25519_gpulab -C "jbf-gpulab"`
   Send the friend ONLY the `.pub` file contents. The private key never leaves the laptop.
4. Ask the friend these questions first (answers decide whether the script applies):
   * Linux (which distro) or Windows? The script targets Linux with systemd.
   * Does the friend have sudo? Output of `nvidia-smi` (driver must support the RTX 5090;
     a recent 570+ driver is needed).
   * Free disk where models will live (need 150 GB or more)? Is the GPU shared with other lab users?
   * Can the box reach the internet (Tailscale, Ollama downloads)? Is it on 24/7?
   * Who can physically reboot it if it ever hangs (name and phone)?
5. Get the supervisor's one-line email confirming the lab machine may be used for this
   study and accessed remotely. Keep it with the paper's ethics statement.

## 1. Friend runs the setup (about 15 minutes of work)

```bash
git clone https://github.com/aljabid/jailbreak-framework.git
cd jailbreak-framework/research/remote_gpu
sudo TS_AUTHKEY='tskey-auth-...' SSH_PUBKEY='ssh-ed25519 AAAA... jbf-gpulab' bash setup_gpu_box.sh
```

If the models should live on another disk: add `MODELS_DIR=/data/ollama`.
The script is idempotent; re-running it is safe.

## 2. Before you leave (friend and researcher together on a call)

Do not skip these. They are what prevent being locked out later.

* [ ] Researcher, from the laptop: `ssh -i ~\.ssh\id_ed25519_gpulab jbf@gpu-lab` works.
* [ ] In the Tailscale admin console, open the machine `gpu-lab` and choose
      **Disable key expiry** (otherwise access silently dies after about 180 days).
* [ ] **Reboot test:** `sudo reboot`. Wait 3 minutes. Researcher SSHes in again and
      `curl -s http://127.0.0.1:11434/api/version` returns JSON. Ollama and Tailscale must come
      back by themselves.
* [ ] Power: in BIOS/UEFI set **Restore on AC Power Loss = Power On** so a power cut does not
      leave the box off.
* [ ] `nvidia-smi` shows the GPU and nothing else big is using it. Ask other lab users not to
      launch large jobs on it during runs.
* [ ] Friend leaves the researcher a phone number and names someone who can power-cycle the box.
* [ ] Friend does not update the NVIDIA driver or kernel after this without telling the researcher
      (a driver update plus reboot is the most common way a working box breaks).

## 3. Researcher operates from home

Add to `~\.ssh\config`:

```
Host gpu-lab
  HostName gpu-lab
  User jbf
  IdentityFile ~/.ssh/id_ed25519_gpulab
  ServerAliveInterval 30
  ServerAliveCountMax 6
  LocalForward 21434 127.0.0.1:11434
```

Keep the tunnel open (it reconnects if the home internet blips):

```powershell
while ($true) { ssh -N gpu-lab; Start-Sleep 5 }
```

Pull the models over the tunnel (run inside tmux on the box so a dropped connection does not
kill the download). Check names on ollama.com/library first; they change.

```bash
ssh gpu-lab
tmux new -s pull
for m in llama3.1:8b qwen2.5:7b mistral:7b phi4 qwen2.5:14b deepseek-r1:14b \
         gemma2:27b mistral-small:24b qwen2.5:32b llama-guard3:8b; do ollama pull "$m"; done
```

Run the framework from the laptop against the tunnel:

```powershell
.venv\Scripts\python main.py run --provider local --local-mode ollama `
  --ollama-base-url http://127.0.0.1:21434 --model-name qwen2.5:32b `
  --seed 42 --concurrency 4 --cache --no-report --eval-mode keyword `
  --target-id journal-study --authorization-file research\grants\journal_grant_signed.json `
  --variations 3 -o outputs\adv_remote_qwen2_5_32b.json
```

Notes:

* `--cache` makes every run resumable: after a home-internet drop, re-run the same command and
  finished requests are skipped.
* The grant lists the allowed models. Add any new model to the grant, re-sign it, and re-upload.
* Models load one at a time (`OLLAMA_MAX_LOADED_MODELS=1`); run models sequentially.

## 4. Failure plan

| Symptom | Likely cause | Fix |
|---|---|---|
| `ssh` times out | box off or Tailscale down | check `tailscale status` on laptop; call the contact to power-cycle |
| tunnel up but API errors | Ollama service stopped | `ssh gpu-lab 'sudo systemctl restart ollama'` (the setup script grants this one command, nothing else) |
| model OOM / slow | another process on the GPU | `nvidia-smi` over SSH; ask lab users |
| connection works then dies after months | Tailscale key expiry | confirm "Disable key expiry" was set |
| everything dead after a driver update | driver/kernel change | contact reverts or reinstalls the driver |

## 5. Data handling and shutdown

* Model outputs from harmful-behaviour prompts stay on the researcher's laptop in gitignored
  folders and are never published; only labels and aggregate rates are reported.
* When the study ends: delete the model files and outputs on the box
  (`rm -rf $MODELS_DIR/*`, remove `~jbf`), run `tailscale logout`, and tell the supervisor.
