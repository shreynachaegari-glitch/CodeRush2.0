"""Verification Agent: sandboxed, resource-limited recompute of closed-form claims.

Local subprocess only (no e2b/Docker, per the locked plan). Hardens the naive
"subprocess + timeout" idea with actual RAM/CPU/file-size limits via the
`resource` module on POSIX, and a hard wall-clock timeout everywhere (works on
Windows too, where `resource` isn't available).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .llm import LLMClient

TIMEOUT_SECONDS = 8
MAX_OUTPUT_CHARS = 4000

_PRELUDE_POSIX = """
import resource
resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
resource.setrlimit(resource.RLIMIT_FSIZE, (1 * 1024 * 1024, 1 * 1024 * 1024))
try:
    resource.setrlimit(resource.RLIMIT_NPROC, (16, 16))
except Exception:
    pass
"""


@dataclass
class VerificationResult:
    ok: bool
    stdout: str
    stderr: str
    timed_out: bool
    exit_code: int | None


def run_sandboxed(code: str, timeout: int = TIMEOUT_SECONDS) -> VerificationResult:
    """Execute untrusted/generated Python in a disposable subprocess with hard limits."""
    is_posix = sys.platform != "win32"
    prelude = _PRELUDE_POSIX if is_posix else ""
    full_source = prelude + "\n" + code

    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "recompute.py"
        script.write_text(full_source, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(script)],  # -I: isolated mode, ignores env/site customizations
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmp,
            )
            return VerificationResult(
                ok=proc.returncode == 0,
                stdout=proc.stdout[:MAX_OUTPUT_CHARS],
                stderr=proc.stderr[:MAX_OUTPUT_CHARS],
                timed_out=False,
                exit_code=proc.returncode,
            )
        except subprocess.TimeoutExpired as e:
            return VerificationResult(
                ok=False,
                stdout=(e.stdout or "")[:MAX_OUTPUT_CHARS] if isinstance(e.stdout, str) else "",
                stderr=f"timed out after {timeout}s",
                timed_out=True,
                exit_code=None,
            )


def recompute_link_budget(distance_km: float, freq_ghz: float, tx_power_dbw: float, ant_gain_db: float) -> VerificationResult:
    """A concrete closed-form claim for the comms/satellite demo: free-space path loss + link budget."""
    code = f"""
import math
distance_km = {distance_km}
freq_ghz = {freq_ghz}
tx_power_dbw = {tx_power_dbw}
ant_gain_db = {ant_gain_db}

fspl_db = 20 * math.log10(distance_km) + 20 * math.log10(freq_ghz) + 92.45
received_dbw = tx_power_dbw + ant_gain_db - fspl_db

print(f"FSPL_dB={{fspl_db:.3f}}")
print(f"received_power_dBW={{received_dbw:.3f}}")
"""
    return run_sandboxed(code)


VERIFIER_SYSTEM = (
    "You are the Verification Agent inside Shutdown, a falsification-driven research agent. "
    "You are given a hypothesis and the evidence gathered for it so far. Look for a concrete, "
    "closed-form, numeric claim actually stated in the hypothesis or evidence (a formula, a "
    "threshold, a ratio, an inequality, a unit conversion) that can be independently recomputed "
    "from stdlib Python alone (math module only, no external data, no network, no file access). "
    "If one exists, respond with ONLY a fenced python code block that recomputes it from the "
    "numbers given and prints each intermediate quantity plus a final PASS/FAIL line comparing "
    "the recomputed value against the claimed one. If no such self-contained numeric claim exists "
    "in the hypothesis or evidence -- e.g. the claim is qualitative, or recomputing it would "
    "require data not given here -- respond with ONLY:\n"
    "NOT_VERIFIABLE: <one-sentence reason>\n"
    "Never fabricate numbers that were not given in the hypothesis or evidence."
)


def _extract_code(raw: str) -> str | None:
    m = re.search(r"```(?:python)?\s*(.*?)```", raw, flags=re.DOTALL)
    return m.group(1).strip() if m else None


@dataclass
class ClaimVerification:
    verifiable: bool
    reason: str  # populated when not verifiable
    result: VerificationResult | None = None


def verify_claim(llm: LLMClient, hypothesis_statement: str, evidence_excerpts: list[str]) -> ClaimVerification:
    """Grounds the "Verification Agent" stage in the actual run instead of a
    fixed satellite link-budget formula: asks the model to recompute a real
    numeric claim from THIS hypothesis's own evidence, sandboxed, or say
    honestly that nothing here is closed-form recomputable. A hardcoded
    formula run against every question regardless of domain would be
    evidence that was never really checked -- worse than admitting there's
    nothing to verify.
    """
    joined = "\n---\n".join(e.strip()[:800] for e in evidence_excerpts if e.strip())[:3000]
    prompt = f"Hypothesis: {hypothesis_statement}\n\nEvidence gathered so far:\n{joined or '(none yet)'}"
    raw = llm.complete(prompt, system=VERIFIER_SYSTEM).strip()

    if raw.upper().startswith("NOT_VERIFIABLE"):
        reason = raw.split(":", 1)[1].strip() if ":" in raw else "no closed-form numeric claim identified"
        return ClaimVerification(verifiable=False, reason=reason)

    code = _extract_code(raw)
    if not code:
        return ClaimVerification(verifiable=False, reason="model did not return a recomputable snippet")

    return ClaimVerification(verifiable=True, reason="", result=run_sandboxed(code))
