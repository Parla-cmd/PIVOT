"""
Social Media / Username OSINT Module
Checks username existence across 300+ platforms.

Platform data sourced from gosearch (github.com/ibnaleem/gosearch) +
custom Swedish platforms. Stored in data/gosearch_data.json.

Result states:
  confirmed  — strong signal: status_code check passed, profilePresence text found,
               or errorMsg absent with positive body evidence
  possible   — 200 OK, no red flags, but no strong confirmation
  not_found  — 404, errorMsg found, or profilePresence text absent
  redirected — final URL differs significantly from expected (login/home redirect)
  blocked    — 403/429 detected
  error      — timeout or network failure
  skipped    — platform errorType is 'unknown' (unreliable, gosearch marks these)
"""
from __future__ import annotations

import json
import re
import concurrent.futures
from pathlib import Path
from urllib.parse import urlparse

import requests
from rich.progress import (
    BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn,
)

from .utils import console, get_headers, print_section

# ── Redirect / generic-page detection ─────────────────────────────────────────

_REDIRECT_SLUGS = re.compile(
    r"/(login|signin|signup|register|auth|home|search|explore|"
    r"captcha|challenge|404|not.?found|missing|error|sessions|"
    r"accounts/login|checkpoint)(/|$|\?)",
    re.IGNORECASE,
)

_MIN_PROFILE_BYTES = 800
_TIMEOUT = 12


def _is_redirect_url(original_url: str, final_url: str) -> bool:
    """True if the response landed on a generic/login page."""
    orig  = urlparse(original_url)
    final = urlparse(final_url)

    if orig.netloc.lstrip("www.") != final.netloc.lstrip("www."):
        return True
    if _REDIRECT_SLUGS.search(final.path):
        return True
    orig_depth  = len([p for p in orig.path.split("/")  if p])
    final_depth = len([p for p in final.path.split("/") if p])
    if orig_depth >= 2 and final_depth == 0:
        return True
    return False


# ── Load platform registry from gosearch data.json ───────────────────────────

_DATA_PATH = Path(__file__).parent.parent / "data" / "gosearch_data.json"

# Swedish-specific platforms not in gosearch
_SWEDISH_PLATFORMS: list[dict] = [
    {
        "name": "Flashback",
        "base_url": "https://www.flashback.org/member/{u}",
        "url_probe": "https://www.flashback.org/member/{u}",
        "follow_redirects": True,
        "errorType": "errorMsg",
        "errorMsg": "Ingen användare",
        "_confirm": "Flashback Forum",
        "_source": "custom",
    },
    {
        "name": "Bilddagboken",
        "base_url": "https://www.bilddagboken.se/{u}",
        "url_probe": "https://www.bilddagboken.se/{u}",
        "follow_redirects": True,
        "errorType": "errorMsg",
        "errorMsg": "finns inte",
        "_source": "custom",
    },
    {
        "name": "Familjeliv",
        "base_url": "https://www.familjeliv.se/profil/{u}",
        "url_probe": "https://www.familjeliv.se/profil/{u}",
        "follow_redirects": True,
        "errorType": "errorMsg",
        "errorMsg": "Hittades inte",
        "_source": "custom",
    },
]


def _load_platforms() -> list[dict]:
    """
    Load platforms from gosearch data.json, skip 'unknown' errorType,
    then prepend Swedish custom platforms (overriding duplicates by name).
    """
    platforms: list[dict] = []

    if _DATA_PATH.exists():
        with open(_DATA_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        for entry in raw.get("websites", []):
            if entry.get("errorType") == "unknown":
                continue  # gosearch explicitly marks these as unreliable
            platforms.append(entry)

    # Build a name→index map so Swedish platforms can override gosearch ones
    name_map: dict[str, int] = {p["name"]: i for i, p in enumerate(platforms)}

    for sw in _SWEDISH_PLATFORMS:
        if sw["name"] in name_map:
            platforms[name_map[sw["name"]]] = sw  # override
        else:
            platforms.insert(0, sw)  # prepend

    return platforms


PLATFORMS: list[dict] = _load_platforms()

# States that represent genuine hits
_HIT_STATES = {"confirmed", "possible"}

_STATE_STYLE: dict[str, tuple[str, str]] = {
    "confirmed":  ("bold green",  "[✓]"),
    "possible":   ("yellow",      "[?]"),
    "not_found":  ("dim",         "[-]"),
    "redirected": ("dim cyan",    "[~]"),
    "blocked":    ("dim magenta", "[x]"),
    "error":      ("dim red",     "[!]"),
    "skipped":    ("dim",         "[ ]"),
}


# ── Core check ────────────────────────────────────────────────────────────────

def check_platform(username: str, platform: dict) -> dict:
    """
    Check one platform for the given username.
    Maps gosearch errorType logic to our state system.
    """
    name         = platform["name"]
    base_url     = platform.get("base_url", "").replace("{}", username).replace("{u}", username)
    probe_url    = platform.get("url_probe", base_url).replace("{}", username).replace("{u}", username)
    error_type   = platform.get("errorType", "status_code")
    error_msg    = platform.get("errorMsg", "")
    response_url = platform.get("response_url", "").replace("{}", username).replace("{u}", username)
    confirm_text = platform.get("_confirm", "").replace("{u}", username)
    follow_redir = platform.get("follow_redirects", True)

    def _result(state: str, note: str = "") -> dict:
        return {"platform": name, "url": base_url, "state": state, "note": note}

    try:
        resp = requests.get(
            probe_url,
            headers=get_headers(),
            timeout=_TIMEOUT,
            allow_redirects=follow_redir,
        )
    except requests.Timeout:
        return _result("error", "timeout")
    except Exception as exc:
        return _result("error", str(exc)[:80])

    status    = resp.status_code
    final_url = resp.url
    body      = resp.text
    body_len  = len(body)

    # ── Blocked ───────────────────────────────────────────────────────────────
    if status in (403, 429):
        return _result("blocked", f"HTTP {status}")
    if status >= 500:
        return _result("error", f"HTTP {status}")

    # ── gosearch: status_code ─────────────────────────────────────────────────
    if error_type == "status_code":
        if status == 404:
            return _result("not_found")
        if status == 200:
            # Apply redirect check on top
            if follow_redir and _is_redirect_url(probe_url, final_url):
                return _result("redirected", f"-> {final_url[:80]}")
            if body_len < _MIN_PROFILE_BYTES:
                return _result("not_found", f"body {body_len}b")
            if confirm_text and confirm_text.lower() in body.lower():
                return _result("confirmed")
            return _result("possible")
        return _result("not_found", f"HTTP {status}")

    # ── gosearch: errorMsg ────────────────────────────────────────────────────
    if error_type == "errorMsg":
        if status == 404:
            return _result("not_found")
        if error_msg and error_msg.lower() in body.lower():
            return _result("not_found")
        if follow_redir and _is_redirect_url(probe_url, final_url):
            return _result("redirected", f"-> {final_url[:80]}")
        if body_len < _MIN_PROFILE_BYTES:
            return _result("not_found", f"body {body_len}b")
        if confirm_text and confirm_text.lower() in body.lower():
            return _result("confirmed")
        if status == 200:
            return _result("possible")
        return _result("not_found", f"HTTP {status}")

    # ── gosearch: profilePresence — text must be PRESENT for a real profile ───
    if error_type == "profilePresence":
        if status == 404:
            return _result("not_found")
        if not error_msg:
            return _result("possible")
        if error_msg.lower() in body.lower():
            return _result("confirmed")
        return _result("not_found")

    # ── gosearch: response_url — detect redirect to known not-found URL ───────
    if error_type == "response_url":
        if response_url and response_url.lower() in final_url.lower():
            return _result("not_found", "redirected to not-found URL")
        if status == 200:
            return _result("possible")
        return _result("not_found", f"HTTP {status}")

    # ── Fallback ──────────────────────────────────────────────────────────────
    return _result("error", f"unhandled errorType={error_type}")


# ── Progress runner ───────────────────────────────────────────────────────────

def check_username_with_progress(
    username: str,
    threads: int = 20,
    label: str = "",
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Check all platforms concurrently with a live progress bar.
    Returns (hits, not_found, errors).
    """
    total = len(PLATFORMS)
    hits, not_found, errors = [], [], []

    with Progress(
        SpinnerColumn("line"),
        TextColumn(f"  [bold cyan]{label or username}[/bold cyan]"),
        BarColumn(bar_width=28),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("[dim]{task.completed}/{task.total}[/dim]"),
        TextColumn("[bold green]{task.fields[found]} hits[/bold green]"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("checking", total=total, found=0)

        with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {
                executor.submit(check_platform, username, p): p["name"]
                for p in PLATFORMS
            }
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                state  = result.get("state", "error")
                if state in _HIT_STATES:
                    hits.append(result)
                elif state in ("not_found", "redirected", "blocked", "skipped"):
                    not_found.append(result)
                else:
                    errors.append(result)
                progress.update(task, advance=1, found=len(hits))

    return hits, not_found, errors


# ── Public run() ──────────────────────────────────────────────────────────────

def run(username: str, threads: int = 20) -> None:
    print_section("USERNAME / SOCIAL MEDIA SEARCH")
    console.print(
        f"  [dim]Username:[/dim] [bold]{username}[/bold]  "
        f"[dim]Checking {len(PLATFORMS)} platforms...[/dim]\n"
    )

    hits, not_found, errors = check_username_with_progress(username, threads)

    confirmed = [r for r in hits if r["state"] == "confirmed"]
    possible  = [r for r in hits if r["state"] == "possible"]

    console.print()

    if confirmed:
        console.print(f"  [bold green]Confirmed ({len(confirmed)}):[/bold green]")
        for r in sorted(confirmed, key=lambda x: x["platform"]):
            console.print(f"  [bold green]  [✓] {r['platform']:22s}[/bold green] {r['url']}")

    if possible:
        console.print(f"\n  [yellow]Possible — verify manually ({len(possible)}):[/yellow]")
        for r in sorted(possible, key=lambda x: x["platform"]):
            note = f"  [dim]{r['note']}[/dim]" if r.get("note") else ""
            console.print(f"  [yellow]  [?] {r['platform']:22s}[/yellow] {r['url']}{note}")

    if not hits:
        console.print("  [dim]Not found on any checked platforms.[/dim]")

    if errors:
        console.print(f"\n  [dim]Could not check {len(errors)} platform(s):[/dim]")
        for r in sorted(errors, key=lambda x: x["platform"]):
            console.print(
                f"  [dim]  [!] {r['platform']:22s} -- {r.get('note', '')}[/dim]"
            )

    redirected_count = sum(1 for r in not_found if r.get("state") == "redirected")
    blocked_count    = sum(1 for r in not_found if r.get("state") == "blocked")

    console.print(
        f"\n  [dim]Summary: {len(confirmed)} confirmed, {len(possible)} possible"
        + (f", {redirected_count} redirected" if redirected_count else "")
        + (f", {blocked_count} blocked"       if blocked_count    else "")
        + f", {len(errors)} errors — {len(PLATFORMS)} platforms checked[/dim]"
    )
