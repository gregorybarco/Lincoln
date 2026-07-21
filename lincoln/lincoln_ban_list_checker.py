"""
Lincoln Ban List Checker  v0.6.0
==================================
Scans AI-generated code for patterns banned in the OptionsPricing project.
Based on ProjectA_CODE_PRACTICES.md Section 2.

Called optionally from lincoln_routes_chat.py when the active project
is OptionsPricing (or any project flagged as 'enforce_ban_list' in future).

Returns a list of violations so the UI can display a warning banner
before the user acts on generated code.
"""

import re
from dataclasses import dataclass


@dataclass
class BanViolation:
    pattern_name: str
    reason:       str
    line_number:  int
    line_text:    str


# Ban list from ProjectA_CODE_PRACTICES.md Section 2
_BAN_PATTERNS = [
    {
        "name":    "ctypes VRAM bridging",
        "reason":  "Memory leaks, GPU driver crashes (WDDM kill). Use f2py only.",
        "regex":   r"\bctypes\b.*(?:VRAM|GPU|cuda|device)",
        "flags":   re.IGNORECASE,
    },
    {
        "name":    "ctypes import",
        "reason":  "ctypes is banned for Fortran bridging. Use f2py bridge only.",
        "regex":   r"^\s*(?:import\s+ctypes|from\s+ctypes\s+import)",
        "flags":   re.MULTILINE,
    },
    {
        "name":    "subprocess cross-OS Popen",
        "reason":  "Phantom WSL environments, no tracking or kill. "
                   "Windows-side triggers only one WSL call at a time.",
        "regex":   r"subprocess\.Popen\s*\(.*(?:wsl|bash|sh)",
        "flags":   re.IGNORECASE,
    },
    {
        "name":    "JSON pointer files",
        "reason":  "NTFS race conditions and file lock conflicts.",
        "regex":   r"(?:json\.dump|json\.load).*pointer|pointer.*(?:json\.dump|json\.load)",
        "flags":   re.IGNORECASE,
    },
    {
        "name":    "gfortran compiler reference",
        "reason":  "Incompatible ABI with Intel MKL. Use nvfortran at absolute path only.",
        "regex":   r"\bgfortran\b",
        "flags":   re.IGNORECASE,
    },
    {
        "name":    "hardcoded Windows drive letter path",
        "reason":  "FileNotFoundError when project moves. Use relative paths or path resolvers.",
        "regex":   r"""(?:["'`])[A-Za-z]:[/\\\\]""",
        "flags":   0,
    },
    {
        "name":    "Python logic injected into .sh pipeline (Pattern 9)",
        "reason":  "Violates one-seam build rule. .sh files may only contain bash-native "
                   "tools and the two permitted Python calls ($VENV_PY -m numpy.f2py "
                   "and the introspection heredoc).",
        "regex":   r"python\s+-c\s+['\"]|subprocess.*python|os\.system.*python",
        "flags":   re.IGNORECASE,
    },
    {
        "name":    "numerical math moved to Python",
        "reason":  "Rule 4 violation. All numerical computation must stay in Fortran/MKL. "
                   "Python owns orchestration only.",
        "regex":   r"(?:numpy|scipy)\s*\.\s*(?:exp|log|sqrt|sin|cos|cumsum|einsum)\s*\(",
        "flags":   re.IGNORECASE,
    },
    {
        "name":    "sequential optimizer dispatch",
        "reason":  ">95% GPU idle, MKL stream re-seeding. Use batched GPU replay.",
        "regex":   r"for\s+\w+\s+in\s+population.*optimize|sequential.*candidate",
        "flags":   re.IGNORECASE,
    },
    {
        "name":    "CMake usage",
        "reason":  "Cache poisoning, SDK path incompatibilities. Use the .bat/.sh pipeline only.",
        "regex":   r"\bcmake\b",
        "flags":   re.IGNORECASE,
    },
]

# Non-ASCII character detection (ASCII-127 law)
_NON_ASCII_REGEX = re.compile(r"[^\x00-\x7F]")


def check_against_ban_list(code: str, include_ascii_check: bool = True) -> list[BanViolation]:
    """
    Scan generated code for banned patterns.

    Args:
        code                : The code string to scan (from canvas or response)
        include_ascii_check : Also flag non-ASCII characters (ASCII-127 law)

    Returns:
        List of BanViolation objects. Empty list means no violations found.
    """
    violations = []
    lines      = code.splitlines()

    for ban in _BAN_PATTERNS:
        pattern = re.compile(ban["regex"], ban["flags"])
        for i, line in enumerate(lines, start=1):
            if pattern.search(line):
                violations.append(BanViolation(
                    pattern_name=ban["name"],
                    reason=ban["reason"],
                    line_number=i,
                    line_text=line.strip()[:120],
                ))

    if include_ascii_check:
        for i, line in enumerate(lines, start=1):
            match = _NON_ASCII_REGEX.search(line)
            if match:
                violations.append(BanViolation(
                    pattern_name="Non-ASCII character (ASCII-127 law violation)",
                    reason=(
                        "All source files must be within ASCII 0-127. "
                        "Unicode causes silent encoding bugs at the NTFS Windows/Linux boundary "
                        "and crackfortran parser failures during f2py compilation."
                    ),
                    line_number=i,
                    line_text=line.strip()[:120],
                ))

    return violations


def format_violations_for_ui(violations: list[BanViolation]) -> list[dict]:
    """Convert violations to JSON-serialisable dicts for the UI warning banner."""
    return [
        {
            "pattern_name": v.pattern_name,
            "reason":       v.reason,
            "line_number":  v.line_number,
            "line_text":    v.line_text,
        }
        for v in violations
    ]
