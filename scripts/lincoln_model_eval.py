"""
Lincoln Model Evaluation Harness
==================================
Standalone script -- talks directly to Ollama's API (localhost:11434).
Does NOT import from or touch the Flask app, lincoln_database.py, or any
Lincoln core file. Safe to run any time without affecting the live app.

Runs a fixed task set against a fixed model list, captures full output
(including <think> reasoning where the model supports it), and logs
performance + VRAM metrics for side-by-side comparison.

Usage:
    python scripts/lincoln_model_eval.py
    python scripts/lincoln_model_eval.py --models deepseek-r1:14b,qwen3.5:9b
    python scripts/lincoln_model_eval.py --long-context-file lincoln/lincoln_ollama_service.py
    python scripts/lincoln_model_eval.py --output my_report.md
"""

import argparse
import json
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import requests

OLLAMA_BASE_URL = "http://localhost:11434"

# Matches Lincoln's own default ceiling (see D22 -- max_context_tokens).
# Using the same value here keeps the harness honest: it tests what the
# model will actually get when running inside Lincoln, not an inflated
# best-case number.
DEFAULT_NUM_CTX = 16384

# Only the long-context task gets a bigger window -- that's the one
# specifically testing how much headroom each model leaves for real input.
LONG_CONTEXT_NUM_CTX = 32768

DEFAULT_MODELS = ["qwen3.5:9b", "deepseek-r1:14b", "danielsheep/gpt-oss-20b-Unsloth"]

# Hard wall-clock limit per task per model. The requests timeout=300 only
# covers time between receiving individual chunks -- a model grinding at
# 0.1 tok/s never hits it. This ceiling kills and skips the task instead.
DEFAULT_TASK_TIMEOUT_SEC = 120

# Same pattern list as lincoln_ollama_service.py's _is_thinking_model().
# Duplicated here on purpose -- this script has zero imports from the
# Lincoln package so it stays completely decoupled from the running app.
_THINKING_MODEL_PATTERNS = ("qwen3", "qwq", "deepseek-r", "phi4-reasoning")


def _is_thinking_model(model: str) -> bool:
    return any(p in model.lower() for p in _THINKING_MODEL_PATTERNS)


# ── Task definitions ──────────────────────────────────────────────────────
#
# NOTE on task 1: this is a PLACEHOLDER. Swap `prompt` below for a real
# BARCO/OptionsPricing prompt whenever you have one -- nothing else in the
# script depends on its content.

def _build_tasks(long_context_file: str | None) -> list[dict]:
    long_ctx_content = ""
    if long_context_file:
        path = Path(long_context_file)
        if path.exists():
            long_ctx_content = path.read_text(encoding="utf-8", errors="ignore")
        else:
            print(f"[harness] WARNING: --long-context-file not found: {path}")

    tasks = [
        {
            "id": "1_domain_reasoning",
            "title": "Fortran / quant finance domain reasoning (PLACEHOLDER -- swap this prompt)",
            "num_ctx": DEFAULT_NUM_CTX,
            "tools": None,
            "prompt": (
                "You are working in a quantitative finance codebase using BARCO/"
                "OptionsPricing Fortran conventions (ASCII-127 source only, no "
                "hardcoded values, everything configurable). Explain how you would "
                "numerically compute the Greeks (Delta, Gamma, Vega) for a European "
                "call option using a finite-difference approach on the Black-Scholes "
                "formula, and sketch the Fortran subroutine signature you'd use."
            ),
        },
        {
            "id": "2_tool_call_reliability",
            "title": "Agentic tool-call schema compliance",
            "num_ctx": DEFAULT_NUM_CTX,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "description": "Read the contents of a file from the project directory.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "Relative path to the file to read.",
                                }
                            },
                            "required": ["path"],
                        },
                    },
                }
            ],
            "prompt": (
                "Read the file lincoln_ollama_service.py so you can tell me how "
                "context window sizing works in this project."
            ),
        },
        {
            "id": "3_python_coding",
            "title": "General Python coding task",
            "num_ctx": DEFAULT_NUM_CTX,
            "tools": None,
            "prompt": (
                "Write a Python function that takes a list of float prices and "
                "returns the maximum drawdown as a percentage. Include a short "
                "docstring and handle the empty-list edge case."
            ),
        },
        {
            "id": "4_long_context",
            "title": "Long-context handling",
            "num_ctx": LONG_CONTEXT_NUM_CTX,
            "tools": None,
            "prompt": (
                (
                    f"Here is a Python source file:\n\n```python\n{long_ctx_content}\n```\n\n"
                    "Summarize what this file is responsible for, and name every "
                    "function that reads a setting from the database."
                )
                if long_ctx_content
                else (
                    "No --long-context-file was provided, so this task was skipped. "
                    "Re-run with e.g. --long-context-file lincoln/lincoln_ollama_service.py "
                    "for a real long-context test."
                )
            ),
            "skipped": not bool(long_ctx_content),
        },
        {
            "id": "5_sanity_check",
            "title": "Plain conversational sanity check",
            "num_ctx": DEFAULT_NUM_CTX,
            "tools": None,
            "prompt": "Briefly explain what makes a locally-run AI assistant more privacy-preserving than a cloud-based one.",
        },
    ]
    return tasks


# ── System snapshots ──────────────────────────────────────────────────────

def _nvidia_smi_snapshot() -> dict:
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=10,
        )
        used, total, util, temp = [x.strip() for x in out.stdout.strip().split(",")]
        return {
            "vram_used_mb": int(used),
            "vram_total_mb": int(total),
            "gpu_util_pct": int(util),
            "gpu_temp_c": int(temp),
        }
    except Exception as e:
        return {"error": str(e)}


def _ollama_ps_processor(model: str) -> str:
    """
    Returns the PROCESSOR column from `ollama ps` for the given model
    (e.g. "100% GPU" or "45%/55% CPU/GPU"). Empty string if the model
    isn't currently loaded or `ollama ps` couldn't be parsed.

    Uses header-position-based extraction (not split()) because columns
    like "6.4 GB" and "100% GPU" contain spaces that break index alignment.
    """
    try:
        out = subprocess.run(
            ["ollama", "ps"], capture_output=True, text=True, timeout=10,
        )
        lines = out.stdout.strip().splitlines()
        if len(lines) < 2:
            return ""
        header = lines[0]
        proc_start = header.find("PROCESSOR")
        until_start = header.find("UNTIL")
        if proc_start == -1:
            return ""
        for line in lines[1:]:
            if model in line:
                if until_start != -1 and proc_start < until_start:
                    return line[proc_start:until_start].strip()
                return " ".join(line[proc_start:].strip().split()[:2])
        return ""
    except Exception:
        return ""


# ── Model run ──────────────────────────────────────────────────────────────

def _run_one_inner(model: str, task: dict) -> dict:
    if task.get("skipped"):
        return {"skipped": True, "reason": task["prompt"]}

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": task["prompt"]}],
        "stream": True,
        "options": {"temperature": 0.7, "num_ctx": task["num_ctx"], "num_predict": -1},
    }
    if task.get("tools"):
        payload["tools"] = task["tools"]

    think = _is_thinking_model(model)
    if think:
        payload["think"] = True

    before = _nvidia_smi_snapshot()

    think_text, response_text = "", ""
    tool_calls: list[dict] = []
    final_meta: dict = {}
    error = None

    try:
        with requests.post(
            f"{OLLAMA_BASE_URL}/api/chat", json=payload, stream=True, timeout=300,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line.decode("utf-8"))
                message = chunk.get("message", {})

                if think:
                    think_text += message.get("thinking", "")

                if message.get("tool_calls"):
                    tool_calls.extend(message["tool_calls"])

                response_text += message.get("content", "")

                if chunk.get("done"):
                    final_meta = {
                        k: chunk.get(k)
                        for k in (
                            "total_duration", "load_duration",
                            "prompt_eval_count", "prompt_eval_duration",
                            "eval_count", "eval_duration",
                        )
                    }
                    break
    except Exception as e:
        error = str(e)

    after = _nvidia_smi_snapshot()
    processor = _ollama_ps_processor(model)

    tokens_per_sec = None
    if final_meta.get("eval_count") and final_meta.get("eval_duration"):
        tokens_per_sec = round(
            final_meta["eval_count"] / (final_meta["eval_duration"] / 1e9), 1
        )

    return {
        "skipped": False,
        "error": error,
        "think_text": think_text,
        "response_text": response_text,
        "tool_calls": tool_calls,
        "meta": final_meta,
        "tokens_per_sec": tokens_per_sec,
        "vram_before_mb": before.get("vram_used_mb"),
        "vram_after_mb": after.get("vram_used_mb"),
        "processor": processor,
    }


def _run_one(model: str, task: dict, timeout_sec: int = DEFAULT_TASK_TIMEOUT_SEC) -> dict:
    """
    Runs _run_one_inner in a daemon thread with a hard wall-clock timeout.
    If the model stalls and the thread hasn't finished within timeout_sec,
    the task is recorded as TIMEOUT and the harness moves on immediately.
    The daemon thread is left to die when the process exits.
    """
    result: dict = {}

    def _worker():
        result.update(_run_one_inner(model, task))

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout=timeout_sec)

    if thread.is_alive():
        print(
            f"[harness] TIMEOUT: {model} / {task['id']} exceeded {timeout_sec}s "
            f"-- skipping and moving on"
        )
        return {
            "skipped": False,
            "error": (
                f"TIMEOUT after {timeout_sec}s -- model stalled (likely insufficient "
                f"capacity for this context size). Re-run with --task-timeout N to adjust."
            ),
            "think_text": "",
            "response_text": "",
            "tool_calls": [],
            "meta": {},
            "tokens_per_sec": None,
            "vram_before_mb": None,
            "vram_after_mb": None,
            "processor": "",
        }

    return result


# ── Report generation ───────────────────────────────────────────────────────

def _format_report(models: list[str], tasks: list[dict], results: dict) -> str:
    lines = [
        f"# Lincoln Model Evaluation Report",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Models: {', '.join(models)}",
        "",
        "## Summary",
        "",
        "| Task | Model | Tokens/sec | VRAM delta (MB) | Processor | Tool call valid? |",
        "|---|---|---|---|---|---|",
    ]

    for task in tasks:
        for model in models:
            r = results[task["id"]][model]
            if r.get("skipped"):
                lines.append(f"| {task['id']} | {model} | - | - | - | SKIPPED |")
                continue
            if r.get("error"):
                lines.append(f"| {task['id']} | {model} | - | - | - | ERROR: {r['error']} |")
                continue
            vram_delta = ""
            if r.get("vram_before_mb") is not None and r.get("vram_after_mb") is not None:
                vram_delta = str(r["vram_after_mb"] - r["vram_before_mb"])
            tool_valid = "-"
            if task.get("tools"):
                tool_valid = "yes" if r.get("tool_calls") else "no tool call made"
            lines.append(
                f"| {task['id']} | {model} | {r.get('tokens_per_sec', '-')} "
                f"| {vram_delta} | {r.get('processor', '-')} | {tool_valid} |"
            )

    lines.append("")
    lines.append("---")

    for task in tasks:
        lines.append(f"\n## {task['id']} — {task['title']}\n")
        for model in models:
            r = results[task["id"]][model]
            lines.append(f"### {model}\n")
            if r.get("skipped"):
                lines.append(f"_Skipped: {r['reason']}_\n")
                continue
            if r.get("error"):
                lines.append(f"**ERROR:** {r['error']}\n")
                continue
            if r.get("think_text"):
                lines.append("**Thinking:**\n```\n" + r["think_text"].strip() + "\n```\n")
            if r.get("tool_calls"):
                lines.append("**Tool calls:**\n```json\n" + json.dumps(r["tool_calls"], indent=2) + "\n```\n")
            lines.append("**Response:**\n```\n" + r["response_text"].strip() + "\n```\n")
            lines.append(f"_tokens/sec: {r.get('tokens_per_sec', '-')}, "
                          f"VRAM: {r.get('vram_before_mb')} -> {r.get('vram_after_mb')} MB, "
                          f"processor: {r.get('processor', '-')}_\n")

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Lincoln model comparison harness")
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS))
    parser.add_argument("--output", default=None)
    parser.add_argument("--long-context-file", default=None)
    parser.add_argument(
        "--tasks", default=None,
        help="Comma-separated task IDs to run, e.g. 4_long_context,5_sanity_check. "
             "Omit to run all tasks.",
    )
    parser.add_argument(
        "--task-timeout", type=int, default=DEFAULT_TASK_TIMEOUT_SEC,
        help=f"Wall-clock seconds before a stalled task is skipped (default {DEFAULT_TASK_TIMEOUT_SEC}). "
             f"Use 0 to disable.",
    )
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    tasks = _build_tasks(args.long_context_file)
    if args.tasks:
        allowed = {t.strip() for t in args.tasks.split(",") if t.strip()}
        tasks = [t for t in tasks if t["id"] in allowed]

    timeout = args.task_timeout if args.task_timeout > 0 else 999999

    results: dict = {t["id"]: {} for t in tasks}

    for task in tasks:
        for model in models:
            print(f"[harness] running {task['id']} on {model} ...")
            results[task["id"]][model] = _run_one(model, task, timeout_sec=timeout)

    report = _format_report(models, tasks, results)

    output_path = Path(args.output) if args.output else Path(
        f"model_eval_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    )
    output_path.write_text(report, encoding="utf-8")
    print(f"[harness] report written to {output_path}")


if __name__ == "__main__":
    main()