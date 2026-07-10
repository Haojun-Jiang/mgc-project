from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .schemas import LLMRequest, LLMResponse, ToolCall


class LLMGateway(Protocol):
    def chat(self, request: LLMRequest) -> LLMResponse:
        """Send a chat request and return normalized content/tool calls."""


class LLMGatewayError(RuntimeError):
    """Raised when the LLM gateway cannot complete a request."""


@dataclass(slots=True)
class LLMGatewayConfig:
    base_url: str
    api_key: str = ""
    default_model: str = ""
    timeout_seconds: int = 60
    auth_header: str = "authorization"
    verify_ssl: bool = True
    extra_headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls, prefix: str = "LLM_GATEWAY_", dotenv_path: str | Path = ".env") -> "LLMGatewayConfig":
        load_env_file(dotenv_path)
        extra_headers = parse_json_object(os.getenv(f"{prefix}EXTRA_HEADERS_JSON", "{}"))
        return cls(
            base_url=os.getenv(f"{prefix}BASE_URL", "").strip(),
            api_key=os.getenv(f"{prefix}API_KEY", "").strip(),
            default_model=os.getenv(f"{prefix}MODEL", "").strip(),
            timeout_seconds=int(os.getenv(f"{prefix}TIMEOUT_SECONDS", "60")),
            auth_header=os.getenv(f"{prefix}AUTH_HEADER", "authorization").strip().lower(),
            verify_ssl=parse_bool(os.getenv(f"{prefix}VERIFY_SSL", "true")),
            extra_headers={str(k): str(v) for k, v in extra_headers.items()},
        )

    def chat_completions_url(self) -> str:
        base = self.base_url.rstrip("/")
        if not base:
            raise LLMGatewayError("LLM_GATEWAY_BASE_URL is required")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"


class OpenAICompatibleGateway:
    """Gateway for providers exposing the OpenAI chat completions shape."""

    def __init__(self, config: LLMGatewayConfig):
        self.config = config

    def chat(self, request: LLMRequest) -> LLMResponse:
        payload = request.to_dict()
        if not payload.get("model"):
            if not self.config.default_model:
                raise LLMGatewayError("model is required by request or LLM_GATEWAY_MODEL")
            payload["model"] = self.config.default_model

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = urllib.request.Request(
            self.config.chat_completions_url(),
            data=body,
            headers=self._headers(),
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                http_request,
                timeout=self.config.timeout_seconds,
                context=self._ssl_context(),
            ) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMGatewayError(f"LLM gateway HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise LLMGatewayError(f"LLM gateway connection failed: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise LLMGatewayError(f"LLM gateway returned invalid JSON: {exc}") from exc

        return parse_openai_chat_response(data)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            **self.config.extra_headers,
        }
        if self.config.api_key:
            if self.config.auth_header in {"", "authorization"}:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            else:
                headers[self.config.auth_header] = self.config.api_key
        return headers

    def _ssl_context(self):
        if self.config.verify_ssl:
            return None
        return ssl._create_unverified_context()


class StaticLLMGateway:
    """Deterministic gateway for tests and offline demos."""

    def __init__(self, response: LLMResponse):
        self.response = response
        self.requests: list[LLMRequest] = []

    def chat(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return self.response


def build_llm_gateway(config: LLMGatewayConfig | None = None) -> OpenAICompatibleGateway:
    return OpenAICompatibleGateway(config or LLMGatewayConfig.from_env())


def parse_openai_chat_response(data: dict) -> LLMResponse:
    choices = data.get("choices") or []
    if not choices:
        return LLMResponse(content="", raw=data)

    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    calls = []
    for item in message.get("tool_calls") or []:
        function = item.get("function") or {}
        calls.append(
            ToolCall(
                id=str(item.get("id", "")),
                name=str(function.get("name", "")),
                arguments=parse_tool_arguments(function.get("arguments")),
            )
        )
    return LLMResponse(content=content, tool_calls=calls, raw=data)


def parse_tool_arguments(raw: object) -> dict:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {"_raw": raw}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"_raw": raw, "_parse_error": str(exc)}
    return parsed if isinstance(parsed, dict) else {"_raw": parsed}


def parse_json_object(raw: str) -> dict:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMGatewayError(f"invalid JSON object: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LLMGatewayError("expected a JSON object")
    return parsed


def parse_bool(raw: str) -> bool:
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def load_env_file(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = strip_env_quotes(value.strip())


def strip_env_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
