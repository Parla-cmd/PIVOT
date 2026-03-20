"""
Watcher / Scheduled Scan Diff
-------------------------------
Saves a baseline scan result and lets you re-run to detect changes.

Usage:
  python main.py watch --target anna@example.se          # save baseline
  python main.py watch --target anna@example.se --check  # re-scan & diff

State is stored in: ~/.sweden-osint/watch/<target_hash>.json
"""
import json
import hashlib
import datetime
from pathlib import Path
from .utils import console, print_section, safe
from . import reporter as _reporter


_STATE_DIR = Path.home() / ".sweden-osint" / "watch"


def _state_path(target: str) -> Path:
    h = hashlib.md5(target.lower().encode()).hexdigest()[:12]
    return _STATE_DIR / f"{h}.json"


def _save_state(target: str, findings: list[dict]) -> Path:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    state = {
        "target":    target,
        "timestamp": datetime.datetime.now().isoformat(),
        "findings":  findings,
    }
    path = _state_path(target)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return path


def _load_state(target: str) -> dict | None:
    path = _state_path(target)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_watched() -> list[dict]:
    """Return all saved watch targets."""
    if not _STATE_DIR.exists():
        return []
    results = []
    for p in _STATE_DIR.glob("*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                state = json.load(f)
            results.append({
                "target":    state.get("target", "?"),
                "timestamp": state.get("timestamp", "?"),
                "findings":  len(state.get("findings", [])),
                "file":      str(p),
            })
        except Exception:
            pass
    return sorted(results, key=lambda x: x["timestamp"], reverse=True)


# ── diff logic ────────────────────────────────────────────────────────────────

def _finding_key(row: dict) -> str:
    """Stable fingerprint for a finding row (ignores _section)."""
    filtered = {k: v for k, v in row.items() if k not in ("_section",)}
    return json.dumps(filtered, sort_keys=True, ensure_ascii=False)


def compute_diff(old: list[dict], new: list[dict]) -> dict[str, list[dict]]:
    old_keys = {_finding_key(r) for r in old}
    new_keys = {_finding_key(r) for r in new}

    added   = [r for r in new if _finding_key(r) not in old_keys]
    removed = [r for r in old if _finding_key(r) not in new_keys]

    return {"added": added, "removed": removed}


# ── display diff ──────────────────────────────────────────────────────────────

def _display_diff(diff: dict[str, list[dict]], old_ts: str) -> None:
    added   = diff["added"]
    removed = diff["removed"]

    console.print(f"\n  [dim]Baseline from:[/dim] {old_ts}")
    console.print(f"  [dim]Re-scanned:   [/dim] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")

    if not added and not removed:
        console.print("\n  [bold green][=][/bold green] No changes detected.")
        return

    if added:
        console.print(f"\n  [bold green][+] {len(added)} NEW finding(s):[/bold green]")
        for row in added:
            section = row.get("_section", "")
            summary = _row_summary(row)
            console.print(f"    [green]+[/green] [{section}] {safe(summary)}")

    if removed:
        console.print(f"\n  [bold red][-] {len(removed)} REMOVED finding(s):[/bold red]")
        for row in removed:
            section = row.get("_section", "")
            summary = _row_summary(row)
            console.print(f"    [red]-[/red] [{section}] {safe(summary)}")


def _row_summary(row: dict) -> str:
    """One-line human summary of a finding row."""
    priority = ["name", "email", "phone", "company", "domain", "title",
                "url", "platform", "address", "record", "breach"]
    parts = []
    for key in priority:
        val = row.get(key, "")
        if val and val != row.get("_section", ""):
            parts.append(str(val))
        if len(parts) >= 3:
            break
    return "  |  ".join(parts) if parts else str(row)[:80]


# ── run ───────────────────────────────────────────────────────────────────────

def run(target: str, check: bool = False, output: str = "") -> None:
    print_section("WATCHER — CHANGE DETECTION")
    console.print(f"  [dim]Target:[/dim] [bold]{target}[/bold]")

    # Run the scan (reuse correlate logic)
    _reporter.init(target=target)
    from .correlate import run as correlate_run
    correlate_run(target=target)
    new_findings = _reporter.get_all()

    if check:
        # ── diff mode ─────────────────────────────────────────────────────────
        old_state = _load_state(target)
        if not old_state:
            console.print(
                f"\n  [yellow][!][/yellow] No baseline found for [bold]{target}[/bold].\n"
                f"  Run without [bold]--check[/bold] first to save a baseline."
            )
            return

        diff = compute_diff(old_state["findings"], new_findings)
        _display_diff(diff, old_state["timestamp"])

        # Save new state as updated baseline
        path = _save_state(target, new_findings)
        console.print(f"\n  [dim]Baseline updated:[/dim] {path}")

        if output:
            # Save diff as JSON
            diff_out = output.replace(".html", "_diff.json")
            with open(diff_out, "w", encoding="utf-8") as f:
                json.dump({
                    "target":     target,
                    "checked_at": datetime.datetime.now().isoformat(),
                    "baseline":   old_state["timestamp"],
                    "added":      diff["added"],
                    "removed":    diff["removed"],
                }, f, ensure_ascii=False, indent=2)
            console.print(f"  [green]Diff saved:[/green] {diff_out}")
    else:
        # ── baseline mode ─────────────────────────────────────────────────────
        path = _save_state(target, new_findings)
        console.print(
            f"\n  [green][+][/green] Baseline saved: [cyan]{path}[/cyan]\n"
            f"  [dim]{len(new_findings)} findings stored.[/dim]\n\n"
            f"  Next time run with [bold]--check[/bold] to detect changes."
        )


def run_list() -> None:
    """Print all watched targets."""
    print_section("WATCHER — MONITORED TARGETS")
    targets = list_watched()
    if not targets:
        console.print("  [dim]No watched targets. Run [bold]pivot watch --target ...[/bold] first.[/dim]")
        return
    for t in targets:
        console.print(
            f"  [bold]{safe(t['target'])}[/bold]\n"
            f"    [dim]Last scan: {t['timestamp']}  |  {t['findings']} findings[/dim]\n"
            f"    [dim]State file: {t['file']}[/dim]"
        )
