"""Verification Agent: sandboxed, resource-limited recompute of closed-form claims.

Local subprocess only (no e2b/Docker, per the locked plan). Hardens the naive
"subprocess + timeout" idea with actual RAM/CPU/file-size limits via the
`resource` module on POSIX, and a hard wall-clock timeout everywhere (works on
Windows too, where `resource` isn't available).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

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
