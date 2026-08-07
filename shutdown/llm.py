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
            return json.dumps({"relevant": True, "contradicts": False, "class": None,
                               "reason": "no same-conditions conflict found"})
        if "root cause" in s or "critique" in s:
            return "Extraction prompt did not request explicit arbitration-mode fields from spec-sheet tables."
        if "verification agent" in s:
            # Honest offline behavior: MockLLM can't actually read the evidence
            # for a numeric claim, so it says so rather than fabricating a
            # recompute -- same standard a real model is held to.
            return "NOT_VERIFIABLE: offline mock cannot extract a numeric claim from arbitrary evidence"
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
    """Builds every provider that has a key configured, in priority order, and
    tries them in that order. Gemini's free tier is capped at 20 requests/day
    project-wide -- a demo mid-investigation used to just die (or silently
    fall back to MockLLM, returning canned satellite content for whatever the
    user actually asked). Now a dead/exhausted provider gets skipped for the
    REST OF THIS RUN and the next configured one takes over, instead of
    aborting or degrading to the mock without saying so.
    """

    _PROVIDER_ORDER = ("gemini", "nvidia", "nvidia2", "openai", "anthropic")

    def __init__(self):
        self._backends: list[tuple[str, object, str | None]] = []
        for kind in self._PROVIDER_ORDER:
            backend = self._build(kind)
            if backend:
                self._backends.append(backend)
        if not self._backends:
            raise RuntimeError("no API key configured")
        self._active = 0
        self._apply_active()

    def _build(self, kind: str) -> tuple[str, object, str | None] | None:
        try:
            if kind == "gemini" and os.environ.get("GEMINI_API_KEY"):
                from google import genai

                client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
                # alias, not a pinned version -- tracks whatever "flash" currently
                # resolves to instead of going stale when a dated model is retired
                return ("gemini", client, "gemini-flash-latest")
            if kind == "nvidia" and os.environ.get("NVIDIA_API_KEY"):
                # NVIDIA NIM speaks the OpenAI wire format, so it reuses that
                # client with a different base_url -- a separate free tier
                # from Gemini's, so it's the first fallback when Gemini's
                # daily cap is hit rather than a rarely-used alternative.
                from openai import OpenAI

                client = OpenAI(
                    api_key=os.environ["NVIDIA_API_KEY"],
                    base_url=os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
                )
                return ("openai_compatible", client, os.environ.get("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct"))
            if kind == "nvidia2" and os.environ.get("NVIDIA_API_KEY_2"):
                # A second NVIDIA key/model pair -- its own separate quota pool,
                # so a run survives even if the first NVIDIA key is also
                # rate-limited (e.g. two keys under different accounts).
                from openai import OpenAI

                client = OpenAI(
                    api_key=os.environ["NVIDIA_API_KEY_2"],
                    base_url=os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
                )
                return ("openai_compatible", client, os.environ.get("NVIDIA_MODEL_2", "meta/llama-3.3-70b-instruct"))
            if kind == "openai" and os.environ.get("OPENAI_API_KEY"):
                from openai import OpenAI

                return ("openai_compatible", OpenAI(), os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
            if kind == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
                import anthropic

                return ("anthropic", anthropic.Anthropic(), None)
        except Exception as exc:
            # a key is set but the SDK/client itself wouldn't come up (missing
            # package, malformed key) -- skip it rather than taking the whole
            # run down over one bad provider when another might work
            print(f"WARNING: {kind} backend configured but failed to initialize "
                  f"({type(exc).__name__}: {exc}); skipping it.")
        return None

    def _apply_active(self) -> None:
        self._kind, self._client, self._model_name = self._backends[self._active]

    def complete(self, prompt: str, *, system: str = "") -> str:
        while True:
            # Only the LAST remaining backend gets the full retry-with-backoff
            # treatment (worth waiting out a real transient blip when there's
            # nowhere else to go). Every earlier one gets a single attempt --
            # a daily quota cap won't resolve itself in 3 backoff cycles, so
            # burning ~10s retrying a dead provider before falling back just
            # delays the run for no benefit.
            is_last = self._active == len(self._backends) - 1
            try:
                return _with_retry(lambda: self._complete_once(prompt, system=system),
                                   attempts=3 if is_last else 1)
            except Exception as exc:
                if is_last:
                    raise
                dead = self._kind
                self._active += 1
                self._apply_active()
                print(f"WARNING: {dead} backend failed ({type(exc).__name__}: {exc}); "
                      f"switching to {self._kind} for the rest of this run.")

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
