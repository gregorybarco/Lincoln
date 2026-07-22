"""
Lincoln Ban List Checker  v0.7.0
==================================
Scans AI-generated code for two categories of problems:

1. PROJECT BAN LIST -- patterns banned in OptionsPricing (and similar projects).
   Based on ProjectA_CODE_PRACTICES.md Section 2. These patterns indicate
   architectural violations (wrong compiler, hardcoded paths, etc.).

2. PROTECTED FUNCTIONS -- Lincoln's own UI/backend symbols.
   Patterns loaded from build_decisions/PROTECTED_FUNCTIONS.md.
   If generated code redefines lincolnChat, sendMessage, lincolnCanvas etc.,
   it will silently break the Lincoln UI when saved or run. These checks fire
   WARNING banners that tell the user before they take action.

Called from lincoln_routes_chat.py on every response that contains a code block.
Violations are returned as a list and forwarded to the UI as a 'ban_check' SSE
event. The UI shows a collapsible warning banner. Nothing is blocked -- the user
always retains the final say.
"""

import re
from dataclasses import dataclass
from pathlib import Path


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

# ── Protected Lincoln UI / backend functions ──────────────────────────────────
# These patterns detect generated code that would overwrite Lincoln's own
# internals. Detailed definitions are in build_decisions/PROTECTED_FUNCTIONS.md.

_PROTECTED_PATTERNS = [
    {
        "name":   "Redefines Lincoln JS namespace",
        "reason": "This code declares a top-level symbol with the same name as a "
                  "Lincoln module (lincolnChat, lincolnCanvas, etc.). Saving this "
                  "will overwrite Lincoln's UI. Rename the variable.",
        "regex":  r"(?:^|\n)\s*(?:const|let|var|function)\s+"
                  r"(lincolnChat|lincolnCanvas|lincolnSidebar|lincolnSettings|lincolnCanvasUI)\b",
        "flags":  re.MULTILINE,
    },
    {
        "name":   "Reassigns critical Lincoln method",
        "reason": "This code replaces a core Lincoln method via assignment "
                  "(e.g. lincolnChat.sendMessage = ...). This will break Lincoln "
                  "immediately. Use a different function name.",
        "regex":  r"\b(lincolnChat|lincolnSettings|lincolnCanvas|lincolnSidebar)\s*\.\s*"
                  r"(sendMessage|loadSession|newSession|setActiveProject|open|close|"
                  r"loadModels|toggleModelDropdown|selectModel|addPromptBlock|"
                  r"pinCodeBlock|clear|switchTab|loadHistory|loadMemory|"
                  r"handleInputKeydown|init|toggleWebSearch|toggleThinkDropdown)\s*=",
        "flags":  re.MULTILINE,
    },
    {
        "name":   "Redefines protected Python function",
        "reason": "This code defines a function with the same name as a Lincoln "
                  "core function. If saved via Aider, it will replace Lincoln's "
                  "implementation. Use a different function name.",
        "regex":  r"^\s*def\s+(initialise_database|get_active_system_prompt|"
                  r"stream_chat|build_messages_with_rag_context|"
                  r"resolve_num_ctx_for_request|send_message|create_new_session|"
                  r"get_all_settings|save_settings|get_setting|"
                  r"check_against_ban_list)\s*\(",
        "flags":  re.MULTILINE,
    },
    {
        "name":   "Writes to protected HTML ID",
        "reason": "This HTML uses an id= that Lincoln already owns. This will "
                  "conflict with Lincoln's own elements and break the UI.",
        "regex":  r"""id\s*=\s*["'](chatMessages|chatInput|sendBtn|canvasBody|"""
                  r"""settingsOverlay|modelDropdown|modelPill|thinkModePill|"""
                  r"""thinkDropdown|webSearchPill|toastContainer|"""
                  r"""topbarProjectBadge|globalPromptBlocks|pendingFileChip|"""
                  r"""contextStrip|settingsPanelContent)["']""",
        "flags":  re.IGNORECASE,
    },
]


# Non-ASCII character detection (ASCII-127 law)
_NON_ASCII_REGEX = re.compile(r"[^\x00-\x7F]")


def check_against_ban_list(
    code:                str,
    include_ascii_check: bool = True,
    check_protected:     bool = True,
) -> list[BanViolation]:
    """
    Scan generated code for banned patterns AND protected Lincoln symbols.

    Args:
        code                : The code string to scan (from canvas or response)
        include_ascii_check : Also flag non-ASCII characters (ASCII-127 law)
        check_protected     : Also check for Lincoln protected function patterns
                              (v0.7.0 -- prevents generated code breaking Lincoln UI)

    Returns:
        List of BanViolation objects. Empty list means no violations found.
    """
    violations = []
    lines      = code.splitlines()

    # --- Project ban list (OptionsPricing architectural rules) ---------------
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

    # --- Protected Lincoln functions (always checked, any project) -----------
    if check_protected:
        # Run multi-line patterns against the full code string (for MULTILINE)
        for prot in _PROTECTED_PATTERNS:
            pattern = re.compile(prot["regex"], prot["flags"])
            for match in pattern.finditer(code):
                # Find the line number of the match
                line_number = code[:match.start()].count("\n") + 1
                line_text   = lines[line_number - 1].strip()[:120] if line_number <= len(lines) else ""
                violations.append(BanViolation(
                    pattern_name="⚠ PROTECTED: " + prot["name"],
                    reason=prot["reason"],
                    line_number=line_number,
                    line_text=line_text,
                ))

    # --- ASCII-127 law -------------------------------------------------------
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
