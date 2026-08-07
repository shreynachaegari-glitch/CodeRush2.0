"""Pluggable LLM client so every module can be smoke-tested without live API keys.

Real backends (Gemini/OpenAI/Anthropic) plug in behind the same .complete()
interface later; MockLLM keeps the wiring testable offline.
"""

from __future__ import annotations

import json
import os
import time


# Safety ceiling on a single call, not a tight budget. Set generously on
# purpose: current Gemini models spend "thinking" tokens that count against
# this same limit, so a snug value truncates a legitimate reply mid-JSON --
# measured, a 4-hypothesis framing costs ~1.2k tokens with thinking included.
# A truncated framing silently degrades into the generic fallback hypothesis,
# which is worse than an expensive call. Runaway *total* spend is bounded
# separately by RUN_TOKEN_BUDGET in main.py, which is the real cost guard.
MAX_OUTPUT_TOKENS = 8192


class LLMClient:
    last_usage_tokens: int = 0

    def complete(self, prompt: str, *, system: str = "") -> str:
        raise NotImplementedError


class MockLLM(LLMClient):
    """Deterministic canned responses keyed on system-prompt content, for offline
    smoke tests. Speaks the exact JSON contract each real caller expects
    (hypothesis.py / contradiction.py), so swapping in a real client changes
    nothing about how the rest of the system parses the reply.

    `fallback_reason` is set by `get_default_client()` when this was returned
    *instead of* a real client that failed to construct -- as opposed to being
    returned because no key was configured at all. The UI surfaces this
    distinction: "no key set" is expected; "your key failed to initialize" is
    a problem the user needs to know about, not something to discover by
    noticing every response looks like a satellite bus."""
    fallback_reason: str | None = None

    def complete(self, prompt: str, *, system: str = "") -> str:
        self.last_usage_tokens = (len(prompt) + len(system)) // 4  # rough offline estimate, no real tokenizer
        s = system.lower()
        if "hypothesis framer" in s:
            return json.dumps(
                [
                    {
                        "statement": "Single-master arbitration on the shared bus keeps peak power draw "
                        "within the swarm's thermal budget under nominal link load.",
                        "confidence_prior": 0.5,
                        "expected_supporting_evidence": "Independent measurements/simulations agreeing under matching load conditions.",
                        "expected_contradicting_evidence": "A measurement or recompute showing budget overrun under nominal load.",
                        "stop_condition": "3 independent sources agree, or a code-verified contradiction is found.",
                    },
                    {
                        "statement": "Peak power draw exceeds the thermal budget once downlink duty cycle "
                        "rises above 40%, regardless of arbitration scheme.",
                        "confidence_prior": 0.5,
                        "expected_supporting_evidence": "Sources showing budget overrun above the 40% duty-cycle threshold.",
                        "expected_contradicting_evidence": "A source or recompute showing the budget holds above 40%.",
                        "stop_condition": "3 independent sources agree, or a code-verified contradiction is found.",
                    },
                ]
            )
        if "contradiction hunter" in s:
            return json.dumps({"contradicts": False, "class": None, "reason": "no same-conditions conflict found"})
        if "root cause" in s or "critique" in s:
            return "Extraction prompt did not request explicit arbitration-mode fields from spec-sheet tables."
        return "ack"


_KEY_ENV_VARS = ("GEMINI_API_KEY", "NVIDIA_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")


def get_default_client() -> LLMClient:
    """Return a real client if a key is configured, else fall back to the mock.

    `SHUTDOWN_OFFLINE=1` forces the mock even when a key is present -- the
    escape hatch for a rate-limited or dead API mid-demo, and for screenshots
    and CI runs that shouldn't spend quota.
    """
    if os.environ.get("SHUTDOWN_OFFLINE") == "1":
        return MockLLM()
    if any(os.environ.get(k) for k in _KEY_ENV_VARS):
        try:
            return _RealLLM()
        except Exception as exc:
            # A key is set but the real client still failed to come up (bad
            # key, network error, missing SDK). This used to fail silently --
            # the run would proceed on MockLLM and every "investigation"
            # would return the same canned satellite hypotheses regardless of
            # what was asked, with nothing telling you why.
            print(f"WARNING: real LLM client failed to initialize ({type(exc).__name__}: {exc}); "
                  f"falling back to MockLLM -- responses will NOT reflect your question or the API key.")
            mock = MockLLM()
            mock.fallback_reason = f"{type(exc).__name__}: {exc}"
            return mock
    return MockLLM()


class _RealLLM(LLMClient):
    """Thin wrapper picking whichever provider has a key set. Kept optional/lazy-imported."""

    def __init__(self):
        if os.environ.get("GEMINI_API_KEY"):
            from google import genai

            self._client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
            # alias, not a pinned version -- tracks whatever "flash" currently
            # resolves to instead of going stale when a dated model is retired
            self._model_name = "gemini-flash-latest"
            self._kind = "gemini"
        elif os.environ.get("NVIDIA_API_KEY"):
            # NVIDIA NIM speaks the OpenAI wire format, so it reuses that client
            # with a different base_url. Kept as a first-class backend because
            # the Gemini free tier is capped at 20 requests/day -- rehearsing a
            # demo can exhaust it, and "the model provider rate-limited us" is a
            # bad thing to discover on stage. Set NVIDIA_API_KEY to switch.
            from openai import OpenAI

            self._client = OpenAI(
                api_key=os.environ["NVIDIA_API_KEY"],
                base_url=os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
            )
            self._model_name = os.environ.get("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")
            self._kind = "openai_compatible"
        elif os.environ.get("OPENAI_API_KEY"):
            from openai import OpenAI

            self._client = OpenAI()
            self._model_name = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            self._kind = "openai_compatible"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            import anthropic

            self._client = anthropic.Anthropic()
            self._kind = "anthropic"
        else:
            raise RuntimeError("no API key configured")

    def complete(self, prompt: str, *, system: str = "") -> str:
        return _with_retry(lambda: self._complete_once(prompt, system=system))

    def _complete_once(self, prompt: str, *, system: str = "") -> str:
        if self._kind == "gemini":
            from google.genai import types

            resp = self._client.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system or None,
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                ),
            )
            self.last_usage_tokens = getattr(resp.usage_metadata, "total_token_count", 0) or 0
            return resp.text
        if self._kind == "openai_compatible":
            messages = ([{"role": "system", "content": system}] if system else []) + \
                       [{"role": "user", "content": prompt}]
            resp = self._client.chat.completions.create(
                model=self._model_name,
                messages=messages,
                max_tokens=MAX_OUTPUT_TOKENS,  # NIM-hosted models don't all accept max_completion_tokens
            )
            self.last_usage_tokens = getattr(resp.usage, "total_tokens", 0) or 0
            return resp.choices[0].message.content or ""
        if self._kind == "anthropic":
            resp = self._client.messages.create(
                model="claude-3-5-haiku-latest",
                max_tokens=MAX_OUTPUT_TOKENS,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            self.last_usage_tokens = (resp.usage.input_tokens or 0) + (resp.usage.output_tokens or 0)
            return resp.content[0].text
        raise RuntimeError("unreachable")


def _with_retry(call, *, attempts: int = 3, base_delay: float = 1.5):
    """A rate limit or network blip mid-run used to crash the whole investigation.
    Retries transient failures with exponential backoff; a non-transient error
    (bad request, auth failure) still raises immediately since retrying it
    would just waste the same call three times."""
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return call()
        except Exception as exc:  # provider SDKs raise their own exception types
            last_exc = exc
            if not _is_transient(exc) or attempt == attempts - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))
    raise last_exc if last_exc is not None else RuntimeError("retry loop exited without a call attempt")


def _is_transient(exc: Exception) -> bool:
    text = str(exc).lower()
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status in (429, 500, 502, 503, 504):
        return True
    return any(marker in text for marker in (
        "rate limit", "429", "500", "502", "503", "504",
        "timeout", "timed out", "connection", "temporarily unavailable", "overloaded",
    ))
