"""
Paste Search Module
-------------------
Search public paste sites and data dump indexes for an email or phone number.

Sources (all free, no mandatory API key):
  - psbdmp.ws     -- indexes Pastebin dumps, free JSON API
  - GitHub code   -- search code for the target string
  - GrayhatWarfare open S3 buckets (email only)
  - IntelX        -- free-tier search (3 results without API key)
"""
import re
import time
import requests
import urllib.parse
from .utils import fetch, soup, console, print_section, safe
from .config import get as cfg
from . import reporter

_GH_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "sweden-osint-educational-tool",
}


def _gh_token_header() -> dict[str, str]:
    token = cfg("GITHUB_TOKEN")
    if token:
        return {**_GH_HEADERS, "Authorization": f"Bearer {token}"}
    return _GH_HEADERS


# ---- source: psbdmp.ws (Pastebin index) -------------------------------------

def search_psbdmp(query: str) -> list[dict]:
    """
    Search psbdmp.ws for pastes containing the query.
    API: GET https://psbdmp.ws/api/v3/search/{query}
    Returns list of {id, time, text_preview, url}
    """
    results = []
    q = urllib.parse.quote(query, safe="")
    url = f"https://psbdmp.ws/api/v3/search/{q}"

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "sweden-osint-educational-tool"},
            timeout=12,
        )
        if resp.status_code == 200:
            data = resp.json()
            pastes = data if isinstance(data, list) else data.get("data", [])
            for p in pastes[:15]:
                paste_id = p.get("id", "")
                results.append({
                    "id": paste_id,
                    "date": p.get("time", ""),
                    "preview": p.get("text", "")[:150].replace("\n", " "),
                    "url": f"https://pastebin.com/{paste_id}",
                    "source": "psbdmp.ws (Pastebin index)",
                })
        elif resp.status_code == 429:
            console.print("  [yellow]psbdmp.ws rate limit hit -- try again later.[/yellow]")
        elif resp.status_code == 404:
            pass  # No results
    except Exception as e:
        console.print(f"  [dim]psbdmp.ws error: {e}[/dim]")

    return results


# ---- source: GitHub code search ---------------------------------------------

def search_github_code(query: str) -> list[dict]:
    """Search GitHub code for the target string."""
    results = []
    q = urllib.parse.quote(f'"{query}"')
    url = f"https://api.github.com/search/code?q={q}&per_page=10"

    try:
        resp = requests.get(url, headers=_gh_token_header(), timeout=12)
        if resp.status_code == 200:
            for item in resp.json().get("items", []):
                repo = item.get("repository", {}).get("full_name", "")
                path = item.get("path", "")
                html_url = item.get("html_url", "")
                results.append({
                    "repository": repo,
                    "file": path,
                    "url": html_url,
                    "source": "github.com (code search)",
                })
        elif resp.status_code == 403:
            console.print("  [dim]GitHub: rate limit -- set GITHUB_TOKEN for higher limits.[/dim]")
        time.sleep(0.5)
    except Exception as e:
        console.print(f"  [dim]GitHub search error: {e}[/dim]")

    return results


# ---- source: GitHub Gist search ---------------------------------------------

def search_github_gists(query: str) -> list[dict]:
    """Search GitHub Gists (public gist content) for the query."""
    results = []
    # GitHub doesn't have a direct Gist search API for content,
    # so we use the code search which includes gists
    q = urllib.parse.quote(f'"{query}" path:*.txt OR path:*.csv OR path:*.log')
    url = f"https://api.github.com/search/code?q={q}&per_page=5"

    try:
        resp = requests.get(url, headers=_gh_token_header(), timeout=12)
        if resp.status_code == 200:
            for item in resp.json().get("items", []):
                html_url = item.get("html_url", "")
                if "gist.github" in html_url:
                    results.append({
                        "gist_url": html_url,
                        "file": item.get("path", ""),
                        "source": "github.com (gist)",
                    })
        time.sleep(0.5)
    except Exception:
        pass

    return results


# ---- source: IntelX free tier -----------------------------------------------

def search_intelx(query: str) -> list[dict]:
    """
    IntelX free-tier search (no API key, limited to 3 results).
    Full results require an API key: cfg("INTELX_API_KEY")
    """
    results = []
    api_key = cfg("INTELX_API_KEY") or "public"

    # Free public search endpoint
    search_url = "https://2.intelx.io/phonebook/search"
    try:
        resp = requests.post(
            search_url,
            json={"term": query, "maxresults": 10, "media": 0,
                  "target": 0, "terminate": []},
            headers={
                "x-key": api_key,
                "Content-Type": "application/json",
                "User-Agent": "sweden-osint-educational-tool",
            },
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            search_id = data.get("id", "")
            if not search_id:
                return results

            # Poll for results
            time.sleep(1)
            result_url = f"https://2.intelx.io/phonebook/search/result?id={search_id}&limit=10&offset=0"
            result_resp = requests.get(
                result_url,
                headers={"x-key": api_key,
                         "User-Agent": "sweden-osint-educational-tool"},
                timeout=10,
            )
            if result_resp.status_code == 200:
                result_data = result_resp.json()
                for sel in result_data.get("selectors", []):
                    val = sel.get("selectorvalue", "")
                    if val:
                        results.append({
                            "value": val,
                            "type": sel.get("selectortypeh", ""),
                            "source": "intelx.io",
                        })
    except Exception as e:
        console.print(f"  [dim]IntelX error: {e}[/dim]")

    return results


# ---- normalise phone for search ---------------------------------------------

def _normalize_for_search(target: str) -> list[str]:
    """Return multiple search variants for a phone number."""
    if "@" in target:
        return [target]
    digits = re.sub(r"[^0-9]", "", target.replace("+46", "0"))
    if not digits.startswith("0"):
        digits = "0" + digits
    international = "+46" + digits[1:]
    spaced = f"{digits[:3]} {digits[3:6]} {digits[6:]}"
    return [digits, international, spaced]


# ---- main run ---------------------------------------------------------------

def run(target: str) -> None:
    print_section("PASTE / DATA DUMP SEARCH")

    target = target.strip()
    is_email = "@" in target
    variants = _normalize_for_search(target)
    primary = variants[0]

    console.print(f"  [dim]Target:[/dim] [bold]{primary}[/bold]")
    if len(variants) > 1:
        console.print(f"  [dim]Variants:[/dim] {', '.join(variants[1:])}")
    console.print()

    all_results: list[dict] = []

    # psbdmp (Pastebin index)
    for variant in variants[:2]:
        console.print(f"  [dim]Searching psbdmp.ws (Pastebin) for '{variant}'...[/dim]")
        hits = search_psbdmp(variant)
        all_results += hits
        if hits:
            console.print(f"  [dim]  {len(hits)} paste(s) found[/dim]")
        time.sleep(0.5)

    # GitHub code
    console.print(f"  [dim]Searching GitHub code...[/dim]")
    gh_hits = search_github_code(primary)
    all_results += gh_hits
    if gh_hits:
        console.print(f"  [dim]  {len(gh_hits)} code result(s)[/dim]")

    # GitHub Gists
    gist_hits = search_github_gists(primary)
    all_results += gist_hits

    # IntelX
    console.print(f"  [dim]Searching IntelX (free tier)...[/dim]")
    ix_hits = search_intelx(primary)
    all_results += ix_hits
    if ix_hits:
        console.print(f"  [dim]  {len(ix_hits)} IntelX result(s)[/dim]")

    console.print()

    if not all_results:
        console.print("  [bold green]No paste/dump results found.[/bold green]")
        console.print("  [dim]This is a good sign -- target not found in known dumps.[/dim]")
        return

    # Deduplicate and display
    seen_urls: set[str] = set()
    displayed = 0
    for r in all_results:
        key = r.get("url") or r.get("gist_url") or r.get("value") or str(r)
        if key in seen_urls:
            continue
        seen_urls.add(key)
        displayed += 1

        source = r.get("source", "")
        console.print(f"  [bold red][!] HIT[/bold red]  [dim]{source}[/dim]")

        for field in ("url", "gist_url", "value", "repository",
                      "file", "date", "type"):
            val = r.get(field, "")
            if val:
                label = field.replace("_", " ").capitalize()
                if field in ("url", "gist_url") and val.startswith("http"):
                    console.print(f"    [dim]{label}:[/dim] [cyan]{val}[/cyan]")
                else:
                    console.print(f"    [dim]{label}:[/dim] {safe(str(val))}")

        preview = r.get("preview", "")
        if preview:
            console.print(f"    [dim]Preview:[/dim] {safe(preview[:120])}...")

        console.print()

        reporter.add("Paste / Data Dump Search", {
            **{k: v for k, v in r.items() if k != "preview"},
            "target": target,
        })

    console.print(f"  [dim]Total unique hits: {displayed}[/dim]")
    if any("Pastebin" in r.get("source", "") for r in all_results):
        console.print("  [dim]Note: Pastebin pastes may have been deleted since indexing.[/dim]")
