"""OpenAI-compatible LLM provider adapter.

The API key is only read on the backend from environment variables and is never
returned through the API.
"""

from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from ..config import get_settings

_requests: ContextVar[list[dict] | None] = ContextVar("llm_requests", default=None)


@contextmanager
def capture_llm_requests():
    """Collect HTTP attempts for just the current synchronous workflow node."""
    requests: list[dict] = []
    token = _requests.set(requests)
    try:
        yield requests
    finally:
        _requests.reset(token)


class LLMError(Exception):
    """Raised when the configured model cannot produce a usable response."""


class LLMProvider:
    """Minimal chat-completions adapter usable with OpenAI-compatible gateways."""

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.llm_base_url.rstrip("/")
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model
        self.timeout = settings.llm_timeout
        self.configured = settings.llm_configured
        self.unix_socket = os.getenv("LLM_UNIX_SOCKET")

    def _post(self, client: httpx.Client, payload: dict, *, retry: bool) -> tuple[httpx.Response, dict]:
        trace = {
            "provider": "openai" if urlsplit(self.base_url).hostname == "api.openai.com" else "openai_compatible",
            "model": self.model,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "compatibility_retry": retry,
        }
        requests = _requests.get()
        if requests is not None:
            requests.append(trace)
        started = time.perf_counter()
        try:
            response = client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            trace.update(http_status=response.status_code, status="http_error" if response.is_error else "http_response")
            request_id = response.headers.get("x-request-id", "")
            if re.fullmatch(r"req_[a-zA-Z0-9_-]{1,96}", request_id):
                trace["request_id"] = request_id
            return response, trace
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            trace.update(status="timeout" if isinstance(exc, httpx.TimeoutException) else "request_error",
                         error_type=type(exc).__name__)
            raise LLMError(f"模型接口请求失败：{type(exc).__name__}") from exc
        finally:
            trace["duration_ms"] = round((time.perf_counter() - started) * 1000)

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        if not self.configured:
            raise LLMError("AI 解析尚未配置。")

        payload: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        transport = httpx.HTTPTransport(uds=self.unix_socket) if self.unix_socket else None
        with httpx.Client(timeout=self.timeout, transport=transport) as client:
            response, trace = self._post(client, payload, retry=False)
            if response.status_code in (400, 422):
                # Some compatible gateways reject response_format; retry plainly.
                payload.pop("response_format")
                response, trace = self._post(client, payload, retry=True)

        if not response.is_success:
            trace["status"] = "http_error"
            raise LLMError(f"模型接口返回 HTTP {response.status_code}。")

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            trace["status"] = "invalid_response"
            raise LLMError("模型响应格式不符合预期。") from exc
        reported = data.get("model")
        if isinstance(reported, str) and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,127}", reported) and self.api_key not in reported:
            trace["reported_model"] = reported
        usage = data.get("usage")
        if isinstance(usage, dict):
            trace["usage"] = {
                name: usage[name] for name in ("prompt_tokens", "completion_tokens", "total_tokens")
                if type(usage.get(name)) is int and usage[name] >= 0
            }
        try:
            result = _parse_json_content(content)
        except LLMError:
            trace["status"] = "invalid_response"
            raise
        trace["status"] = "json_received"
        return result


def _parse_json_content(content: object) -> dict:
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    if not isinstance(content, str) or not content.strip():
        raise LLMError("模型返回了空内容。")

    text = content.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise LLMError("模型未返回 JSON 对象。")
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError("模型返回的 JSON 无法解析。") from exc
    if not isinstance(parsed, dict):
        raise LLMError("模型返回的 JSON 不是对象。")
    return parsed
