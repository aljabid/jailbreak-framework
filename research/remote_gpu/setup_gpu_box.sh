#!/usr/bin/env bash
# One-time setup of a Linux GPU box as a remote Ollama model server.
#
# What it does (idempotent, safe to re-run):
#   1. creates an unprivileged user `jbf` and installs the researcher's SSH PUBLIC key
#   2. makes sure sshd is running
#   3. installs Tailscale and joins the researcher's private tailnet
#   4. installs Ollama as a systemd service, listening on 127.0.0.1 ONLY
#      (reached through the SSH tunnel, never exposed to the lab network)
#   5. stops the machine from suspending or auto-rebooting
#   6. prints a health summary
#
# Models are NOT pulled here - the researcher pulls them later over SSH.
#
# Usage (run by someone with sudo):
#   sudo TS_AUTHKEY='tskey-auth-...' SSH_PUBKEY='ssh-ed25519 AAAA... jbf-gpulab' \
#        bash setup_gpu_box.sh
#
# Optional: MODELS_DIR=/data/ollama  (put model files on a big disk)
set -euo pipefail

: "${TS_AUTHKEY:?set TS_AUTHKEY (Tailscale auth key from the researcher)}"
: "${SSH_PUBKEY:?set SSH_PUBKEY (the PUBLIC key from the researcher, one line)}"
MODELS_DIR="${MODELS_DIR:-/var/lib/ollama/models}"
RUN_USER="jbf"
HOSTNAME_TS="gpu-lab"
MIN_FREE_GB=150

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run with sudo"
command -v systemctl >/dev/null || die "systemd is required"
command -v nvidia-smi >/dev/null || die "NVIDIA driver not found (nvidia-smi missing)"
case "$SSH_PUBKEY" in ssh-ed25519\ *|ssh-rsa\ *|ecdsa-*) ;; *) die "SSH_PUBKEY must be a public key line";; esac
case "$SSH_PUBKEY" in *PRIVATE*) die "that looks like a PRIVATE key - never send it";; esac

log "1/6 checks"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
mkdir -p "$MODELS_DIR"
free_gb=$(df -BG --output=avail "$MODELS_DIR" | tail -1 | tr -dc '0-9')
[ "$free_gb" -ge "$MIN_FREE_GB" ] || die "only ${free_gb}GB free at $MODELS_DIR (need ${MIN_FREE_GB}GB); set MODELS_DIR on a bigger disk"

log "2/6 user + SSH key"
id "$RUN_USER" >/dev/null 2>&1 || useradd --create-home --shell /bin/bash "$RUN_USER"
install -d -m 700 -o "$RUN_USER" -g "$RUN_USER" "/home/$RUN_USER/.ssh"
AK="/home/$RUN_USER/.ssh/authorized_keys"
touch "$AK"
grep -qxF "$SSH_PUBKEY" "$AK" || printf '%s\n' "$SSH_PUBKEY" >> "$AK"
chown "$RUN_USER:$RUN_USER" "$AK"; chmod 600 "$AK"
if ! command -v sshd >/dev/null && [ ! -x /usr/sbin/sshd ]; then
  apt-get update -y && apt-get install -y openssh-server
fi
install -d /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/99-jbf.conf <<EOF
Match User $RUN_USER
    PasswordAuthentication no
    AllowTcpForwarding yes
EOF
if sshd -t 2>/dev/null || /usr/sbin/sshd -t; then :; else rm -f /etc/ssh/sshd_config.d/99-jbf.conf; die "sshd config test failed (override removed)"; fi
systemctl enable --now ssh 2>/dev/null || systemctl enable --now sshd
systemctl reload ssh 2>/dev/null || systemctl reload sshd || true

# let the unprivileged user restart ONLY the Ollama service, so most hangs can be
# fixed remotely without anyone visiting the lab
SYSTEMCTL="$(command -v systemctl)"
SUDOERS="/etc/sudoers.d/jbf-ollama"
printf '%s ALL=(root) NOPASSWD: %s restart ollama, %s status ollama\n' "$RUN_USER" "$SYSTEMCTL" "$SYSTEMCTL" > "$SUDOERS"
chmod 440 "$SUDOERS"
visudo -cf "$SUDOERS" >/dev/null || { rm -f "$SUDOERS"; die "sudoers rule invalid (removed)"; }

log "3/6 Tailscale"
command -v tailscale >/dev/null || curl -fsSL https://tailscale.com/install.sh | sh
systemctl enable --now tailscaled
tailscale up --authkey "$TS_AUTHKEY" --hostname "$HOSTNAME_TS" --accept-dns=false
tailscale ip -4

log "4/6 Ollama (127.0.0.1 only)"
command -v ollama >/dev/null || curl -fsSL https://ollama.com/install.sh | sh
id ollama >/dev/null 2>&1 || die "ollama user missing after install"
chown -R ollama:ollama "$MODELS_DIR"
install -d /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/override.conf <<EOF
[Service]
Environment="OLLAMA_HOST=127.0.0.1:11434"
Environment="OLLAMA_MODELS=$MODELS_DIR"
Environment="OLLAMA_KEEP_ALIVE=30m"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_NUM_PARALLEL=4"
Environment="OLLAMA_FLASH_ATTENTION=1"
Restart=always
RestartSec=5
EOF
systemctl daemon-reload
systemctl enable ollama
systemctl restart ollama

log "5/6 never sleep, never auto-reboot"
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
if [ -d /etc/apt/apt.conf.d ]; then
  printf 'Unattended-Upgrade::Automatic-Reboot "false";\n' > /etc/apt/apt.conf.d/51jbf-no-reboot
fi
systemctl enable --now nvidia-persistenced 2>/dev/null || nvidia-smi -pm 1 || true
command -v tmux >/dev/null || apt-get install -y tmux || true

log "6/6 health summary"
sleep 3
{
  echo "date: $(date -Is)"
  echo "tailscale: $(tailscale ip -4 | head -1)  host=$HOSTNAME_TS"
  echo "ollama listening: $(ss -ltn | grep -c '127.0.0.1:11434') (1 = loopback only OK)"
  echo "ollama exposed on 0.0.0.0: $(ss -ltn | grep -c '0.0.0.0:11434') (must be 0)"
  echo "ollama api: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:11434/api/version) (200 = OK)"
  echo "gpu: $(nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader)"
  echo "disk free at models dir: $(df -h --output=avail "$MODELS_DIR" | tail -1)"
} | tee "/home/$RUN_USER/HEALTH.txt"
chown "$RUN_USER:$RUN_USER" "/home/$RUN_USER/HEALTH.txt"

cat <<'EOF'

DONE. Before leaving, still do the checks in RUNBOOK.md section "Before you leave":
reboot test, and ask the researcher to confirm SSH works from their laptop.
EOF
