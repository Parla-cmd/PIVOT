"""
SSL & Web Security Tools — ported/inspired by ClatScope Mini (Clats97)
Provides: SSL cert inspection, HTTP security headers, robots/sitemap,
          DNSBL blacklist check, favicon MMH3 hash, Wayback diff.
"""
from __future__ import annotations

import base64
import difflib
import hashlib
import socket
import ssl
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import dns.resolver
import requests

from .utils import console, fetch, print_section, print_result, get_headers

try:
    import mmh3
    _HAS_MMH3 = True
except ImportError:
    _HAS_MMH3 = False


# ── SSL Certificate ───────────────────────────────────────────────────────────

def check_ssl_cert(domain: str) -> dict:
    """Retrieve and parse the SSL certificate for a domain."""
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=15) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()

        subject   = dict(x[0] for x in cert.get("subject", []))
        issuer    = dict(x[0] for x in cert.get("issuer", []))
        san_list  = [v for t, v in cert.get("subjectAltName", []) if t == "DNS"]

        def parse_dt(s: str) -> str:
            try:
                return datetime.strptime(s, "%b %d %H:%M:%S %Y %Z").strftime("%Y-%m-%d")
            except Exception:
                return s

        not_before = parse_dt(cert.get("notBefore", ""))
        not_after  = parse_dt(cert.get("notAfter",  ""))

        # Days until expiry
        try:
            expiry_dt = datetime.strptime(cert.get("notAfter", ""), "%b %d %H:%M:%S %Y %Z")
            days_left = (expiry_dt - datetime.utcnow()).days
        except Exception:
            days_left = None

        return {
            "domain":     domain,
            "issued_to":  subject.get("commonName", ""),
            "issued_by":  issuer.get("commonName",  ""),
            "valid_from": not_before,
            "valid_to":   not_after,
            "days_left":  days_left,
            "san":        san_list,
        }
    except Exception as exc:
        return {"domain": domain, "error": str(exc)}


def run_ssl(domain: str) -> None:
    print_section("SSL CERTIFICATE")
    result = check_ssl_cert(domain)
    if "error" in result:
        console.print(f"  [red]Error:[/red] {result['error']}")
        return
    print_result("Issued To",  result["issued_to"])
    print_result("Issued By",  result["issued_by"])
    print_result("Valid From", result["valid_from"])
    print_result("Valid To",   result["valid_to"])
    days = result.get("days_left")
    if days is not None:
        colour = "green" if days > 30 else "red"
        console.print(f"  [bold cyan]Days Left:[/bold cyan] [{colour}]{days}[/{colour}]")
    if result["san"]:
        console.print(f"  [bold cyan]SAN ({len(result['san'])}):[/bold cyan] "
                      + ", ".join(result["san"][:10])
                      + ("…" if len(result["san"]) > 10 else ""))


# ── HTTP Security Headers ─────────────────────────────────────────────────────

_SEC_HEADERS = [
    "Strict-Transport-Security",
    "Content-Security-Policy",
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Referrer-Policy",
    "Permissions-Policy",
    "Cross-Origin-Resource-Policy",
    "Cross-Origin-Opener-Policy",
]


def check_security_headers(url: str) -> dict:
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    try:
        resp = requests.get(url, headers=get_headers(), timeout=12)
        hdrs = resp.headers
        present = {h: hdrs[h] for h in _SEC_HEADERS if h in hdrs}
        missing = [h for h in _SEC_HEADERS if h not in hdrs]
        return {"url": url, "present": present, "missing": missing,
                "score": len(present), "total": len(_SEC_HEADERS)}
    except Exception as exc:
        return {"url": url, "error": str(exc)}


def run_security_headers(url: str) -> None:
    print_section("HTTP SECURITY HEADERS")
    result = check_security_headers(url)
    if "error" in result:
        console.print(f"  [red]Error:[/red] {result['error']}")
        return
    console.print(f"  [dim]Score: {result['score']}/{result['total']}[/dim]\n")
    for h, v in result["present"].items():
        console.print(f"  [bold green]  [+] {h}:[/bold green] [dim]{v[:80]}[/dim]")
    for h in result["missing"]:
        console.print(f"  [red]  [-] {h} (missing)[/red]")


# ── Robots.txt / Sitemap ──────────────────────────────────────────────────────

def check_robots_sitemap(domain: str) -> dict:
    results = {}
    for path in ("robots.txt", "sitemap.xml"):
        url = f"https://{domain}/{path}"
        try:
            resp = requests.get(url, headers=get_headers(), timeout=10)
            results[path] = {
                "status": resp.status_code,
                "size":   len(resp.text),
                "snippet": resp.text[:500] if resp.ok else "",
            }
        except Exception as exc:
            results[path] = {"error": str(exc)}
    return results


def run_robots_sitemap(domain: str) -> None:
    print_section("ROBOTS.TXT / SITEMAP")
    data = check_robots_sitemap(domain)
    for fname, info in data.items():
        if "error" in info:
            console.print(f"  [yellow]{fname}:[/yellow] {info['error']}")
        else:
            status = info["status"]
            colour = "green" if status == 200 else "yellow"
            console.print(f"  [{colour}]{fname}[/{colour}]  HTTP {status}  {info['size']} bytes")
            if info.get("snippet"):
                console.print(f"  [dim]{info['snippet'][:300]}[/dim]\n")


# ── DNSBL Blacklist Check ─────────────────────────────────────────────────────

_DNSBL_ZONES = [
    "zen.spamhaus.org",
    "bl.spamcop.net",
    "dnsbl.sorbs.net",
    "b.barracudacentral.org",
    "dnsbl-1.uceprotect.net",
    "spam.dnsbl.sorbs.net",
]


def check_dnsbl(ip: str) -> list[dict]:
    """Check an IP against common DNSBL zones. Returns list of hits."""
    reversed_ip = ".".join(ip.strip().split(".")[::-1])
    hits = []

    def _check(zone: str) -> dict | None:
        query = f"{reversed_ip}.{zone}"
        try:
            ans = dns.resolver.resolve(query, "A", lifetime=5)
            return {"zone": zone, "result": str(ans[0])}
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=len(_DNSBL_ZONES)) as ex:
        futures = {ex.submit(_check, z): z for z in _DNSBL_ZONES}
        for future in as_completed(futures):
            r = future.result()
            if r:
                hits.append(r)
    return hits


def run_dnsbl(ip: str) -> None:
    print_section("DNSBL BLACKLIST CHECK")
    console.print(f"  [dim]Checking {ip} against {len(_DNSBL_ZONES)} zones...[/dim]\n")
    hits = check_dnsbl(ip)
    if hits:
        console.print(f"  [bold red]Listed on {len(hits)} blacklist(s):[/bold red]")
        for h in hits:
            console.print(f"  [red]  [!] {h['zone']}[/red]  → {h['result']}")
    else:
        console.print("  [bold green]  [✓] Not listed on any checked blacklists.[/bold green]")


# ── Favicon MMH3 Hash ─────────────────────────────────────────────────────────

def favicon_hash(site_url: str) -> dict:
    """
    Download /favicon.ico and compute MurmurHash3.
    Use in Shodan: http.favicon.hash:<hash>
    """
    if not site_url.lower().startswith(("http://", "https://")):
        site_url = "https://" + site_url
    favicon_url = site_url.rstrip("/") + "/favicon.ico"
    try:
        resp = requests.get(favicon_url, headers=get_headers(), timeout=10)
        resp.raise_for_status()
        b64 = base64.encodebytes(resp.content)
        if not _HAS_MMH3:
            return {"url": favicon_url, "error": "mmh3 not installed"}
        fav_hash = mmh3.hash(b64)
        return {
            "url":         favicon_url,
            "mmh3_hash":   fav_hash,
            "shodan_query": f"http.favicon.hash:{fav_hash}",
            "size_bytes":  len(resp.content),
        }
    except Exception as exc:
        return {"url": favicon_url, "error": str(exc)}


def run_favicon_hash(site_url: str) -> None:
    print_section("FAVICON MMH3 HASH")
    result = favicon_hash(site_url)
    if "error" in result:
        console.print(f"  [red]Error:[/red] {result['error']}")
        return
    print_result("Favicon URL",   result["url"])
    print_result("MMH3 Hash",     str(result["mmh3_hash"]))
    print_result("Shodan Query",  result["shodan_query"])
    print_result("Size",          f"{result['size_bytes']} bytes")


# ── Wayback Machine Diff ──────────────────────────────────────────────────────

def wayback_diff(target_url: str) -> dict:
    """Fetch two oldest/newest Wayback snapshots and diff their text."""
    api = "https://web.archive.org/cdx/search/cdx"
    params = {
        "url": target_url, "output": "json",
        "filter": "statuscode:200", "collapse": "digest",
        "limit": 2, "fl": "timestamp,original",
    }
    try:
        j = requests.get(api, params=params, timeout=20, headers=get_headers()).json()
    except Exception as exc:
        return {"error": str(exc)}

    if len(j) <= 1:
        return {"error": "Not enough unique snapshots for diff"}

    ts1, orig1 = j[-1]
    ts2, orig2 = j[0]
    url1 = f"https://web.archive.org/web/{ts1}/{orig1}"
    url2 = f"https://web.archive.org/web/{ts2}/{orig2}"

    def _get_text(u: str) -> str:
        try:
            r = requests.get(u, timeout=20, headers=get_headers())
            from bs4 import BeautifulSoup
            return BeautifulSoup(r.text, "lxml").get_text(separator="\n")
        except Exception:
            return ""

    text1 = _get_text(url1)
    text2 = _get_text(url2)

    diff = list(difflib.unified_diff(
        text1.splitlines()[:200],
        text2.splitlines()[:200],
        fromfile=f"oldest ({ts1})",
        tofile=f"newest ({ts2})",
        lineterm="",
    ))

    return {
        "oldest_url": url1, "newest_url": url2,
        "oldest_ts": ts1, "newest_ts": ts2,
        "diff_lines": diff[:80],
        "added":   sum(1 for l in diff if l.startswith("+")),
        "removed": sum(1 for l in diff if l.startswith("-")),
    }


def run_wayback_diff(target_url: str) -> None:
    print_section("WAYBACK DIFF")
    console.print(f"  [dim]Comparing oldest and newest snapshots for {target_url}...[/dim]\n")
    result = wayback_diff(target_url)
    if "error" in result:
        console.print(f"  [red]Error:[/red] {result['error']}")
        return
    print_result("Oldest", f"{result['oldest_ts']} → {result['oldest_url']}")
    print_result("Newest", f"{result['newest_ts']} → {result['newest_url']}")
    console.print(f"  [dim]+{result['added']} added lines, -{result['removed']} removed lines[/dim]\n")
    for line in result["diff_lines"]:
        if line.startswith("+"):
            console.print(f"  [green]{line}[/green]")
        elif line.startswith("-"):
            console.print(f"  [red]{line}[/red]")
        else:
            console.print(f"  [dim]{line}[/dim]")
