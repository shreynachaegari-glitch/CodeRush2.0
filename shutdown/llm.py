"""Pluggable LLM client so every module can be smoke-tested without live API keys.

Real backends (Gemini/OpenAI/Anthropic) plug in behind the same .complete()
interface later; MockLLM keeps the wiring testable offline.
"""

from __future__ import annotations

import json
import os


class LLMClient:
    last_usage_tokens: int = 0

    def complete(self, prompt: str, *, system: str = "") -> str:
        raise NotImplementedError


class MockLLM(LLMClient):
    """Deterministic canned responses keyed on system-prompt content, for offline
    smoke tests. Speaks the exact JSON contract each real caller expects
    (hypothesis.py / contradiction.py), so swapping in a real client changes
    nothing about how the rest of the system parses the reply."""

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


def get_default_client() -> LLMClient:
    """Return a real client if a key is configured, else fall back to the mock."""
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return _RealLLM()
        except Exception:
            pass
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
        elif os.environ.get("OPENAI_API_KEY"):
            from openai import OpenAI

            self._client = OpenAI()
            self._kind = "openai"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            import anthropic

            self._client = anthropic.Anthropic()
            self._kind = "anthropic"
        else:
            raise RuntimeError("no API key configured")

    def complete(self, prompt: str, *, system: str = "") -> str:
        if self._kind == "gemini":
            from google.genai import types

            resp = self._client.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=types.GenerateContentConfig(system_instruction=system) if system else None,
            )
            self.last_usage_tokens = getattr(resp.usage_metadata, "total_token_count", 0) or 0
            return resp.text
        if self._kind == "openai":
            resp = self._client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            )
            self.last_usage_tokens = getattr(resp.usage, "total_tokens", 0) or 0
            return resp.choices[0].message.content
        if self._kind == "anthropic":
            resp = self._client.messages.create(
                model="claude-3-5-haiku-latest",
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            self.last_usage_tokens = (resp.usage.input_tokens or 0) + (resp.usage.output_tokens or 0)
            return resp.content[0].text
        raise RuntimeError("unreachable")
