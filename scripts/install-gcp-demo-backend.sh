#!/usr/bin/env bash
# Run on the existing Debian/systemd VM after publishing the source repository.
set -euo pipefail

ref=${1:?Usage: bash install-gcp-demo-backend.sh RELEASE_COMMIT GATEWAY_GROUP}
gateway_group=${2:?Missing Unix group that owns the private Sol gateway socket}
[[ $ref =~ ^[0-9a-f]{40}$ ]]
getent group "$gateway_group" >/dev/null
test -S /run/reprolab-openai-gateway.sock

root=/opt/reprolab-ai
private_cfg=/etc/reprolab-ai
for path in "$root" "$private_cfg" /var/lib/reprolab-demo-public /var/lib/reprolab-demo-operator; do
  test ! -e "$path" || { printf 'Existing path: %s\n' "$path" >&2; exit 1; }
done
for role in public operator; do
  if id "reprolab-$role" >/dev/null 2>&1; then exit 1; fi
  test ! -e "/etc/systemd/system/reprolab-demo-$role.service"
done

sudo -n install -d -m 0755 "$root"
sudo -n git clone --quiet https://github.com/cy642/reprolab-ai.git "$root/source"
sudo -n git -C "$root/source" checkout --quiet --detach "$ref"
sudo -n python3 -m venv "$root/venv"
sudo -n "$root/venv/bin/python" -m pip install -q -r "$root/source/backend/requirements.txt"
sudo -n install -d -m 0700 "$private_cfg"
sudo -n sh -c 'umask 077; openssl rand -hex 32 > /etc/reprolab-ai/demo_access_code'

for role in public operator; do
  account="reprolab-$role"
  storage="/var/lib/reprolab-demo-$role"
  sudo -n useradd --system --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin "$account"
  sudo -n install -d -m 0700 -o "$account" -g "$account" "$storage"
  (
    cd "$root/source/backend"
    sudo -n -u "$account" env REPROLAB_DISABLE_LLM=1 REPROLAB_STORAGE_DIR="$storage" \
      "$root/venv/bin/python" -m app.phase7_demo --storage-dir "$storage" >/dev/null
  )
  if [ "$role" = public ]; then
    port=18880
    mode=readonly
    extra='Environment=REPROLAB_DISABLE_LLM=1'
  else
    port=18881
    mode=protected
    extra="SupplementaryGroups=$gateway_group
LoadCredential=demo_access_code:$private_cfg/demo_access_code
Environment=LLM_BASE_URL=http://localhost/v1
Environment=LLM_UNIX_SOCKET=/run/reprolab-openai-gateway.sock
Environment=LLM_MODEL=gpt-6.2-sol
Environment=LLM_API_KEY=reprolab-private-socket
Environment=REPROLAB_LLM_REQUEST_LIMIT=12
Environment=LLM_TIMEOUT_SECONDS=85"
  fi
  sudo -n tee "/etc/systemd/system/reprolab-demo-$role.service" >/dev/null <<UNIT
[Unit]
Description=ReproLab AI contest backend ($role)
After=network-online.target reprolab-openai-gateway.socket

[Service]
User=$account
Group=$account
WorkingDirectory=$root/source/backend
Environment=REPROLAB_DEMO_MODE=$mode
Environment=REPROLAB_STORAGE_DIR=$storage
Environment=FRONTEND_ORIGINS=https://cy642.github.io
Environment=PYTHONDONTWRITEBYTECODE=1
$extra
ExecStart=$root/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port $port --timeout-keep-alive 5
Restart=on-failure
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadWritePaths=$storage
UMask=0077

[Install]
WantedBy=multi-user.target
UNIT
done

sudo -n systemd-analyze verify /etc/systemd/system/reprolab-demo-{public,operator}.service
sudo -n systemctl daemon-reload
sudo -n systemctl enable --now reprolab-demo-public.service reprolab-demo-operator.service
