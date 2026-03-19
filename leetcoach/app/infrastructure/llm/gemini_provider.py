from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Callable
from urllib import error, parse, request


DEFAULT_GEMINI_MODEL_PRIORITY: tuple[str, ...] = (
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
)


@dataclass(frozen=True)
class GeminiGenerateResult:
    model: str
    text: str


@dataclass(frozen=True)
class GeminiModelFailure:
    model: str
    reason: str


@dataclass(frozen=True)
class GeminiApiError(Exception):
    message: str
    status_code: int | None = None
    retryable: bool = False
    quota_exhausted: bool = False

    def __str__(self) -> str:
        code = f"{self.status_code} " if self.status_code is not None else ""
        return f"{code}{self.message}".strip()


@dataclass(frozen=True)
class GeminiAllModelsFailed(Exception):
    failures: tuple[GeminiModelFailure, ...]

    def __str__(self) -> str:
        details = "; ".join(f"{f.model}: {f.reason}" for f in self.failures)
        return f"All Gemini models failed: {details}"


TransportFn = Callable[[str, str], str]
SleepFn = Callable[[float], None]


class GeminiProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model_priority: tuple[str, ...] = DEFAULT_GEMINI_MODEL_PRIORITY,
        timeout_seconds: float = 20.0,
        max_transient_retries: int = 1,
        transport: TransportFn | None = None,
        sleep_fn: SleepFn = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._model_priority = tuple(model_priority)
        self._timeout_seconds = timeout_seconds
        self._max_transient_retries = max(0, max_transient_retries)
        self._sleep_fn = sleep_fn
        self._transport = transport or self._make_transport()

    def generate_text(self, prompt: str) -> GeminiGenerateResult:
        failures: list[GeminiModelFailure] = []
        for model in self._model_priority:
            attempts_left = self._max_transient_retries + 1
            while attempts_left > 0:
                try:
                    text = self._transport(model, prompt)
                    return GeminiGenerateResult(model=model, text=text)
                except GeminiApiError as exc:
                    if exc.quota_exhausted:
                        failures.append(
                            GeminiModelFailure(model=model, reason=f"quota/rate: {exc}")
                        )
                        break
                    if exc.retryable and attempts_left > 1:
                        attempts_left -= 1
                        self._sleep_fn(0.2)
                        continue
                    failures.append(GeminiModelFailure(model=model, reason=str(exc)))
                    break

        raise GeminiAllModelsFailed(failures=tuple(failures))

    def _make_transport(self) -> TransportFn:
        def _transport(model: str, prompt: str) -> str:
            return _generate_with_http(
                api_key=self._api_key,
                model=model,
                prompt=prompt,
                timeout_seconds=self._timeout_seconds,
            )

        return _transport


def _generate_with_http(
    *,
    api_key: str,
    model: str,
    prompt: str,
    timeout_seconds: float,
) -> str:
    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{parse.quote(model)}:generateContent?key={parse.quote(api_key)}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
    }
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as resp:
            parsed = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise _classify_http_error(exc.code, detail) from exc
    except error.URLError as exc:
        raise GeminiApiError(
            message=f"network error: {exc.reason}",
            retryable=True,
        ) from exc
    except TimeoutError as exc:
        raise GeminiApiError(message="request timed out", retryable=True) from exc
    except json.JSONDecodeError as exc:
        raise GeminiApiError(message="invalid JSON from provider", retryable=True) from exc

    text = _extract_text(parsed)
    if not text:
        raise GeminiApiError(message="provider returned empty text")
    return text


def _extract_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return ""
    first = candidates[0]
    if not isinstance(first, dict):
        return ""
    content = first.get("content")
    if not isinstance(content, dict):
        return ""
    parts = content.get("parts")
    if not isinstance(parts, list):
        return ""
    texts: list[str] = []
    for part in parts:
        if isinstance(part, dict):
            value = part.get("text")
            if isinstance(value, str):
                texts.append(value)
    return "\n".join(texts).strip()


def _classify_http_error(code: int, detail: str) -> GeminiApiError:
    detail_l = detail.lower()
    quota = (
        code == 429
        or "resource_exhausted" in detail_l
        or "quota" in detail_l
        or "rate limit" in detail_l
    )
    retryable = code >= 500 or code == 429
    return GeminiApiError(
        message=f"http {code}: {detail}",
        status_code=code,
        retryable=retryable,
        quota_exhausted=quota,
    )

