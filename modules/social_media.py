"""
Social Media / Username OSINT Module
Checks username existence across Swedish and global platforms.

Result states:
  confirmed  — strong signals (confirm_text present, no redirect, real profile page)
  possible   — 200 OK with no not_found_text but no confirmation text either
  not_found  — explicit 404 or not_found_text detected
  redirected — final URL differs significantly from expected (login/home redirect)
  blocked    — 403/429/CAPTCHA detected
  error      — timeout or network failure
"""
from __future__ import annotations

import re
import concurrent.futures
from urllib.parse import urlparse

import requests
from rich.progress import (
    BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
)

from .utils import console, get_headers, print_section

# ── Redirect / generic-page detection ────────────────────────────────────────

_REDIRECT_SLUGS = re.compile(
    r"/(login|signin|signup|register|auth|home|search|explore|"
    r"captcha|challenge|404|not.?found|missing|error|sessions|"
    r"accounts/login|checkpoint)(/|$|\?)",
    re.IGNORECASE,
)

_MIN_PROFILE_BYTES = 800   # anything shorter is almost certainly an error page
_TIMEOUT = 10


def _is_redirect_url(original_url: str, final_url: str) -> bool:
    """True if the response landed on a page that is clearly NOT a profile."""
    orig = urlparse(original_url)
    final = urlparse(final_url)

    # Different domain → definitely redirected away
    if orig.netloc.lstrip("www.") != final.netloc.lstrip("www."):
        return True

    # Landed on a known generic path
    if _REDIRECT_SLUGS.search(final.path):
        return True

    # Path shrunk dramatically (e.g. /user/johndoe → /)
    orig_depth = len([p for p in orig.path.split("/") if p])
    final_depth = len([p for p in final.path.split("/") if p])
    if orig_depth >= 2 and final_depth == 0:
        return True

    return False


# ── Platform registry ─────────────────────────────────────────────────────────
#
# Each entry is a dict with:
#   name          str   — display name
#   url           str   — profile URL template ({u} = username)
#   not_found     str   — substring in body that means "no such user"
#   confirm       str   — substring that must be present for a CONFIRMED hit
#                         (empty string = rely on absence of not_found only → "possible")
#   check_redirect bool — whether to inspect the final URL after redirects

PLATFORMS: list[dict] = [
    # ── Swedish ──────────────────────────────────────────────────────────────
    {
        "name": "Flashback",
        "url": "https://www.flashback.org/member/{u}",
        "not_found": "Ingen användare",
        "confirm": "Flashback Forum",
        "check_redirect": True,
    },
    {
        "name": "Bilddagboken",
        "url": "https://www.bilddagboken.se/{u}",
        "not_found": "finns inte",
        "confirm": "",
        "check_redirect": True,
    },
    {
        "name": "Familjeliv",
        "url": "https://www.familjeliv.se/profil/{u}",
        "not_found": "Hittades inte",
        "confirm": "",
        "check_redirect": True,
    },
    # ── Global ───────────────────────────────────────────────────────────────
    {
        "name": "GitHub",
        "url": "https://github.com/{u}",
        "not_found": "Not Found",
        "confirm": "repositories",
        "check_redirect": True,
    },
    {
        "name": "Twitter/X",
        "url": "https://twitter.com/{u}",
        "not_found": "This account doesn't exist",
        "confirm": "",
        "check_redirect": True,
    },
    {
        "name": "Instagram",
        "url": "https://www.instagram.com/{u}/",
        "not_found": "Sorry, this page",
        "confirm": "",
        "check_redirect": True,
    },
    {
        "name": "TikTok",
        "url": "https://www.tiktok.com/@{u}",
        "not_found": "Couldn't find this account",
        "confirm": "",
        "check_redirect": True,
    },
    {
        "name": "Reddit",
        "url": "https://www.reddit.com/user/{u}",
        "not_found": "page not found",
        "confirm": "u/{u}",
        "check_redirect": True,
    },
    {
        "name": "LinkedIn",
        "url": "https://www.linkedin.com/in/{u}",
        "not_found": "This page doesn't exist",
        "confirm": "",
        "check_redirect": True,
    },
    {
        "name": "Pinterest",
        "url": "https://www.pinterest.com/{u}/",
        "not_found": "hmm",
        "confirm": "",
        "check_redirect": True,
    },
    {
        "name": "Tumblr",
        "url": "https://{u}.tumblr.com",
        "not_found": "There's nothing here",
        "confirm": "",
        "check_redirect": True,
    },
    {
        "name": "Twitch",
        "url": "https://www.twitch.tv/{u}",
        "not_found": "Sorry. Unless you",
        "confirm": "",
        "check_redirect": True,
    },
    {
        "name": "YouTube",
        "url": "https://www.youtube.com/@{u}",
        "not_found": "This page isn't available",
        "confirm": "",
        "check_redirect": True,
    },
    {
        "name": "Steam",
        "url": "https://steamcommunity.com/id/{u}",
        "not_found": "The specified profile could not be found",
        "confirm": "profile_header",
        "check_redirect": True,
    },
    {
        "name": "SoundCloud",
        "url": "https://soundcloud.com/{u}",
        "not_found": "We can't find",
        "confirm": "",
        "check_redirect": True,
    },
    {
        "name": "Spotify",
        "url": "https://open.spotify.com/user/{u}",
        "not_found": "Page not found",
        "confirm": "",
        "check_redirect": True,
    },
    {
        "name": "Vimeo",
        "url": "https://vimeo.com/{u}",
        "not_found": "Sorry, we couldn't find",
        "confirm": "",
        "check_redirect": True,
    },
    {
        "name": "Medium",
        "url": "https://medium.com/@{u}",
        "not_found": "Page not found",
        "confirm": "",
        "check_redirect": True,
    },
    {
        "name": "Keybase",
        "url": "https://keybase.io/{u}",
        "not_found": "Not a Keybase user",
        "confirm": "keybase.io/{u}",
        "check_redirect": False,
    },
    {
        "name": "GitLab",
        "url": "https://gitlab.com/{u}",
        "not_found": "404",
        "confirm": "gitlab.com/{u}",
        "check_redirect": True,
    },
    {
        "name": "Mastodon",
        "url": "https://mastodon.social/@{u}",
        "not_found": "The page you were looking for",
        "confirm": "@{u}@mastodon.social",
        "check_redirect": True,
    },
    {
        "name": "HackerNews",
        "url": "https://news.ycombinator.com/user?id={u}",
        "not_found": "No such user",
        "confirm": "user?id={u}",
        "check_redirect": False,
    },
    {
        "name": "DockerHub",
        "url": "https://hub.docker.com/u/{u}",
        "not_found": "Page Not Found",
        "confirm": "",
        "check_redirect": True,
    },
]


# ── Core check logic ──────────────────────────────────────────────────────────

def check_platform(username: str, platform: dict) -> dict:
    """
    Check one platform for the given username.

    Returns a dict with keys:
      platform, url, state, note (optional)

    state is one of: confirmed | possible | not_found | redirected | blocked | error
    """
    name = platform["name"]
    url = platform["url"].format(u=username)
    not_found_text = platform.get("not_found", "")
    confirm_text = platform.get("confirm", "").format(u=username)
    check_redirect = platform.get("check_redirect", True)

    def _result(state: str, note: str = "") -> dict:
        return {"platform": name, "url": url, "state": state, "note": note}

    try:
        resp = requests.get(
            url,
            headers=get_headers(),
            timeout=_TIMEOUT,
            allow_redirects=True,
        )
    except requests.Timeout:
        return _result("error", "timeout")
    except Exception as exc:
        return _result("error", str(exc)[:80])

    status = resp.status_code
    final_url = resp.url
    body = resp.text
    body_len = len(body)

    # ── Explicit not-found status codes ──────────────────────────────────────
    if status == 404:
        return _result("not_found")

    if status in (403, 429):
        return _result("blocked", f"HTTP {status}")

    if status >= 500:
        return _result("error", f"HTTP {status}")

    # ── Redirect detection ────────────────────────────────────────────────────
    if check_redirect and _is_redirect_url(url, final_url):
        return _result("redirected", f"-> {final_url[:80]}")

    # ── Body too short to be a real profile page ──────────────────────────────
    if body_len < _MIN_PROFILE_BYTES:
        return _result("not_found", f"body only {body_len} bytes")

    # ── not_found text present in body ───────────────────────────────────────
    if not_found_text and not_found_text.lower() in body.lower():
        return _result("not_found")

    # ── Confirmation text present → confirmed hit ─────────────────────────────
    if confirm_text and confirm_text.lower() in body.lower():
        return _result("confirmed")

    # ── 200 OK, no red flags, but no positive confirmation either ─────────────
    if status == 200:
        return _result("possible")

    return _result("not_found", f"HTTP {status}")


# ── Aggregation helpers ───────────────────────────────────────────────────────

# States that represent genuine hits (shown as found)
_HIT_STATES = {"confirmed", "possible"}

# State display config: (rich colour, prefix symbol)
_STATE_STYLE: dict[str, tuple[str, str]] = {
    "confirmed":  ("bold green",   "[✓]"),
    "possible":   ("yellow",       "[?]"),
    "not_found":  ("dim",          "[-]"),
    "redirected": ("dim cyan",     "[~]"),
    "blocked":    ("dim magenta",  "[x]"),
    "error":      ("dim red",      "[!]"),
}


def check_username_with_progress(
    username: str,
    threads: int = 10,
    label: str = "",
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Check all platforms with a live progress bar.
    Returns (hits, not_found, errors).
    hits = confirmed + possible
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
                state = result.get("state", "error")
                if state in _HIT_STATES:
                    hits.append(result)
                elif state in ("not_found", "redirected", "blocked"):
                    not_found.append(result)
                else:
                    errors.append(result)
                progress.update(task, advance=1, found=len(hits))

    return hits, not_found, errors


# ── Public run() ─────────────────────────────────────────────────────────────

def run(username: str, threads: int = 10) -> None:
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
            console.print(f"  [bold green]  [✓] {r['platform']:20s}[/bold green] {r['url']}")

    if possible:
        console.print(f"  [yellow]Possible — verify manually ({len(possible)}):[/yellow]")
        for r in sorted(possible, key=lambda x: x["platform"]):
            note = f"  [dim]{r['note']}[/dim]" if r.get("note") else ""
            console.print(f"  [yellow]  [?] {r['platform']:20s}[/yellow] {r['url']}{note}")

    if not hits:
        console.print("  [dim]Not found on any checked platforms.[/dim]")

    if errors:
        console.print(f"\n  [dim]Could not check {len(errors)} platform(s):[/dim]")
        for r in sorted(errors, key=lambda x: x["platform"]):
            console.print(
                f"  [dim]  [!] {r['platform']:20s} -- {r.get('note', '')}[/dim]"
            )

    redirected_count = sum(1 for r in not_found if r.get("state") == "redirected")
    blocked_count    = sum(1 for r in not_found if r.get("state") == "blocked")

    console.print(
        f"\n  [dim]Summary: {len(confirmed)} confirmed, {len(possible)} possible, "
        f"{len(not_found)} not found"
        + (f", {redirected_count} redirected" if redirected_count else "")
        + (f", {blocked_count} blocked"       if blocked_count    else "")
        + f", {len(errors)} errors[/dim]"
    )
