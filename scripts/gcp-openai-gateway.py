"""Private, systemd socket-activated GPT-6.2 Sol relay for ReproLab AI."""

import getpass
import http.client
import json
import os
import re
import socket
import socketserver
import sys
import tempfile
from http.server import BaseHTTPRequestHandler
from pathlib import Path

MODEL = "gpt-6.2-sol"
MAX_REQUEST_BYTES = 320 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
KEY_PATH = Path("/etc/reprolab-openai-gateway/openai_api_key")
COMPLETIONS = "/v1/chat/completions"


class Gateway(BaseHTTPRequestHandler):
    timeout = 12

    def log_message(self, format, *args):
        pass

    def send_json(self, status, data, request_id=None):
        body = json.dumps(data).encode("utf-8") if isinstance(data, dict) else data
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if request_id and re.fullmatch(r"req_[a-zA-Z0-9_-]{1,96}", request_id):
            self.send_header("X-Request-ID", request_id)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/healthz":
            self.send_json(200, {"model": MODEL, "credential_configured": bool(self.server.api_key)})
        else:
            self.send_json(404, {"error": "Unknown route"})

    def do_POST(self):
        if self.path != COMPLETIONS:
            self.send_json(404, {"error": "Unknown route"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_REQUEST_BYTES or self.headers.get("Transfer-Encoding"):
                raise ValueError
            request = json.loads(self.rfile.read(size))
            messages = request["messages"]
            if request["model"] != MODEL or request.get("stream", False) is not False:
                raise ValueError
            if not isinstance(messages, list) or not 1 <= len(messages) <= 32:
                raise ValueError
            if any(
                not isinstance(message, dict)
                or message.get("role") not in ("system", "user", "assistant")
                or not isinstance(message.get("content"), str)
                for message in messages
            ):
                raise ValueError
        except (KeyError, TimeoutError, TypeError, ValueError):
            self.send_json(400, {"error": "Expected a bounded non-streaming GPT-6.2 Sol text request"})
            return
        if not self.server.api_key:
            self.send_json(503, {"error": "OpenAI credential has not been configured"})
            return

        payload = {
            "model": MODEL,
            "messages": [{"role": item["role"], "content": item["content"]} for item in messages],
            "max_completion_tokens": 4096,
            "reasoning_effort": "low",
        }
        if request.get("response_format") == {"type": "json_object"}:
            payload["response_format"] = {"type": "json_object"}
        upstream = http.client.HTTPSConnection("api.openai.com", timeout=65)
        try:
            upstream.request("POST", COMPLETIONS, json.dumps(payload).encode(), {
                "Content-Type": "application/json", "Authorization": f"Bearer {self.server.api_key}",
            })
            response = upstream.getresponse()
            request_id = response.getheader("x-request-id")
            if not 200 <= response.status < 300:
                status = response.status if 400 <= response.status < 600 else 502
                self.send_json(status, {"error": "OpenAI rejected the request", "upstream_status": response.status}, request_id)
                return
            content = response.read(MAX_RESPONSE_BYTES + 1)
        except (OSError, http.client.HTTPException):
            self.send_json(502, {"error": "OpenAI connection failed"})
            return
        finally:
            upstream.close()
        if len(content) > MAX_RESPONSE_BYTES:
            self.send_json(502, {"error": "OpenAI response exceeded gateway limit"}, request_id)
            return
        self.send_json(response.status, content, request_id)


def serve():
    if int(os.environ.get("LISTEN_PID", "0")) != os.getpid() or os.environ.get("LISTEN_FDS") != "1":
        raise SystemExit("Start the gateway using its systemd socket")
    credential = Path(os.environ["CREDENTIALS_DIRECTORY"]) / "openai_api_key"
    with socketserver.UnixStreamServer("", Gateway, bind_and_activate=False) as server:
        server.socket.close()
        server.socket = socket.socket(fileno=3)
        server.api_key = credential.read_text().strip()
        server.serve_forever()


def configure_key():
    if os.geteuid() != 0 or not sys.stdin.isatty():
        raise SystemExit("Run the configure-key command with sudo in the SSH terminal")
    key = getpass.getpass("OpenAI API key (hidden): ").strip()
    if not re.fullmatch(r"sk-[A-Za-z0-9_-]{16,500}", key):
        raise SystemExit("Key format was invalid. The credential was unchanged.")
    os.umask(0o077)
    with tempfile.NamedTemporaryFile(mode="w", dir=KEY_PATH.parent, delete=False) as temp:
        temp.write(key + "\n")
    os.replace(temp.name, KEY_PATH)
    print("Credential saved. Restart reprolab-openai-gateway.service to load it.")


if __name__ == "__main__":
    if sys.argv[1:] == ["configure-key"]:
        configure_key()
    else:
        serve()
