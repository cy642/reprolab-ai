#!/usr/bin/env bash
# Install once on a Debian/systemd VM. Invoke as the SSH user, not as root.
set -eu
app=/opt/reprolab-openai-gateway
etc=/etc/reprolab-openai-gateway
unit=/etc/systemd/system/reprolab-openai-gateway
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for path in "$app" "$etc" "$unit.service" "$unit.socket" /run/reprolab-openai-gateway.sock; do
  if test -e "$path"; then printf 'Existing path, install stopped: %s\n' "$path" >&2; exit 1; fi
done
group=$(id -gn)
test -f "$source_dir/gcp-openai-gateway.py"
sudo -n install -d -m 0755 "$app"
sudo -n install -d -m 0700 "$etc"
sudo -n install -m 0600 /dev/null "$etc/openai_api_key"
sudo -n install -m 0644 "$source_dir/gcp-openai-gateway.py" "$app/gateway.py"
sudo -n tee "$unit.service" >/dev/null <<'UNIT'
[Unit]
Description=ReproLab OpenAI text gateway

[Service]
DynamicUser=yes
ExecStart=/usr/bin/python3 /opt/reprolab-openai-gateway/gateway.py
LoadCredential=openai_api_key:/etc/reprolab-openai-gateway/openai_api_key
UMask=0077
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
Restart=on-failure
UNIT
sudo -n tee "$unit.socket" >/dev/null <<UNIT
[Unit]
Description=Private ReproLab OpenAI socket

[Socket]
ListenStream=/run/reprolab-openai-gateway.sock
SocketMode=0660
SocketGroup=$group
RemoveOnStop=yes

[Install]
WantedBy=sockets.target
UNIT
sudo -n /usr/bin/python3 -m py_compile "$app/gateway.py"
sudo -n systemd-analyze verify "$unit.service" "$unit.socket"
sudo -n systemctl daemon-reload
sudo -n systemctl enable --now reprolab-openai-gateway.socket
curl -qfsS --max-time 8 --unix-socket /run/reprolab-openai-gateway.sock http://localhost/healthz
printf '\n'
