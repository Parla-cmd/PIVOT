"""
Email Harvesting Module
-----------------------
Given a domain, find all publicly exposed email addresses linked to it.

Sources:
  - Website crawl (depth-2 mailto: links + regex in source)
  - GitHub code search (requires GITHUB_TOKEN for best results)
  - crt.sh subdomain list -> crawl each subdomain contact page
  - Google-dork scrape (best-effort, may be blocked)
"""
import re
import time
import urllib.parse
import concurrent.futures
import requests
from bs4 import BeautifulSoup
from .utils import fetch, soup, console, print_section, safe
from .config import get as cfg
from . import reporter

EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]{1,64}@[a-zA-Z0-9.\-]{1,255}\.[a-zA-Z]{2,10}"
)

# ---- helpers ----------------------------------------------------------------

def _extract_emails_from_text(text: str, domain: str) -> set[str]:
    """Pull emails from raw text, optionally filter to a domain."""
    found = set()
    for m in EMAIL_RE.finditer(text):
        email = m.group(0).lower().strip(".,;:\"'")
        if domain and not email.endswith(f"@{domain}") and \
                not email.endswith(f".{domain}"):
            continue
        if len(email) < 6 or ".." in email:
            continue
        # Skip common false positives
        if email.split("@")[0] in ("example", "test", "noreply",
                                    "no-reply", "webmaster", "bounce"):
            continue
        found.add(email)
    return found


def _crawl_page(url: str, domain: str, timeout: int = 8) -> set[str]:
    """Fetch a single page and extract emails from it."""
    emails = set()
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; OsintBot/1.0)",
                "Accept": "text/html,*/*",
            },
            timeout=timeout,
            allow_redirects=True,
        )
        if resp.status_code == 200:
            # Raw source (catches obfuscated emails in JS)
            emails |= _extract_emails_from_text(resp.text, domain)

            # Also check mailto: hrefs
            bs = BeautifulSoup(resp.text, "lxml")
            for a in bs.select("a[href^='mailto:']"):
                href = a.get("href", "")[7:].split("?")[0].strip().lower()
                if href and "@" in href:
                    emails.add(href)
    except Exception:
        pass
    return emails


def _get_links(url: str, base_domain: str) -> list[str]:
    """Get internal links from a page for depth-2 crawl."""
    links = []
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; OsintBot/1.0)"},
            timeout=8,
            allow_redirects=True,
        )
        bs = BeautifulSoup(resp.text, "lxml")
        for a in bs.select("a[href]"):
            href = a.get("href", "")
            if href.startswith("/"):
                href = f"https://{base_domain}{href}"
            elif not href.startswith("http"):
                continue
            if base_domain in href:
                links.append(href.split("#")[0])
    except Exception:
        pass
    return list(dict.fromkeys(links))[:30]  # dedupe, cap at 30


# ---- source: website crawl --------------------------------------------------

def harvest_from_website(domain: str) -> set[str]:
    """Crawl the domain's website (depth 2) for email addresses."""
    emails = set()
    start_urls = [
        f"https://{domain}",
        f"https://{domain}/contact",
        f"https://{domain}/kontakt",
        f"https://{domain}/about",
        f"https://{domain}/om-oss",
        f"https://www.{domain}",
    ]

    visited = set()
    to_visit = list(dict.fromkeys(start_urls))

    for url in to_visit[:6]:
        if url in visited:
            continue
        visited.add(url)
        found = _crawl_page(url, domain)
        emails |= found
        time.sleep(0.3)

        # Depth 2: follow internal links from homepage only
        if url in start_urls[:2] and not found:
            links = _get_links(url, domain)
            for link in links[:15]:
                if link not in visited:
                    visited.add(link)
                    emails |= _crawl_page(link, domain)
                    time.sleep(0.2)

    return emails


# ---- source: GitHub code search ---------------------------------------------

def harvest_from_github(domain: str) -> set[str]:
    """Search GitHub code for email addresses on this domain."""
    emails = set()
    token = cfg("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "sweden-osint-educational-tool",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    query = urllib.parse.quote(f'"@{domain}"')
    url = f"https://api.github.com/search/code?q={query}&per_page=10"

    try:
        resp = requests.get(url, headers=headers, timeout=12)
        if resp.status_code == 200:
            for item in resp.json().get("items", []):
                # fetch the raw file content
                raw_url = item.get("html_url", "").replace(
                    "github.com", "raw.githubusercontent.com"
                ).replace("/blob/", "/")
                if raw_url:
                    raw_resp = requests.get(
                        raw_url,
                        headers={"User-Agent": "sweden-osint-educational-tool"},
                        timeout=8,
                    )
                    if raw_resp.status_code == 200:
                        emails |= _extract_emails_from_text(
                            raw_resp.text, domain
                        )
                time.sleep(0.3)
        elif resp.status_code == 403:
            console.print("  [dim]GitHub: rate limit hit for code search.[/dim]")
    except Exception as e:
        console.print(f"  [dim]GitHub harvest error: {e}[/dim]")

    return emails


# ---- source: Google dork scrape (best-effort) -------------------------------

def harvest_from_google(domain: str) -> set[str]:
    """Best-effort Google dork scrape for '@domain.com' emails."""
    emails = set()
    query = urllib.parse.quote(f'"{domain}" email OR "kontakt" OR "contact"')
    url = f"https://www.google.com/search?q={query}&num=20&hl=sv"

    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
                "Accept-Language": "sv-SE,sv;q=0.9",
            },
            timeout=10,
        )
        if resp.status_code == 200:
            emails |= _extract_emails_from_text(resp.text, domain)
    except Exception:
        pass
    return emails


# ---- source: crt.sh subdomains -> contact pages -----------------------------

def harvest_from_subdomains(domain: str) -> set[str]:
    """Grab crt.sh subdomains and crawl their contact pages."""
    from .domain_lookup import lookup_crt_sh
    emails = set()
    subdomains = lookup_crt_sh(domain)[:10]  # cap at 10

    def _check_sub(sub: str) -> set[str]:
        found = set()
        for path in ("", "/contact", "/kontakt"):
            found |= _crawl_page(f"https://{sub}{path}", domain)
        return found

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        for result in ex.map(_check_sub, subdomains):
            emails |= result

    return emails


# ---- main run ---------------------------------------------------------------

def run(domain: str, deep: bool = False):
    print_section("EMAIL HARVEST")
    domain = domain.lower().lstrip("www.").strip()
    console.print(f"  [dim]Domain:[/dim] [bold]{domain}[/bold]"
                  + ("  [dim](deep mode)[/dim]" if deep else "") + "\n")

    all_emails: set[str] = set()

    # Website crawl
    console.print("  [dim]Crawling website for email addresses...[/dim]")
    web_emails = harvest_from_website(domain)
    all_emails |= web_emails
    if web_emails:
        console.print(f"  [dim]  Website: {len(web_emails)} found[/dim]")

    # GitHub
    console.print("  [dim]Searching GitHub code...[/dim]")
    gh_emails = harvest_from_github(domain)
    all_emails |= gh_emails
    if gh_emails:
        console.print(f"  [dim]  GitHub: {len(gh_emails)} found[/dim]")

    # Google
    console.print("  [dim]Google dork scrape...[/dim]")
    g_emails = harvest_from_google(domain)
    all_emails |= g_emails
    if g_emails:
        console.print(f"  [dim]  Google: {len(g_emails)} found[/dim]")

    # Subdomains (deep mode or if few results so far)
    if deep or len(all_emails) < 3:
        console.print("  [dim]Crawling subdomains (crt.sh)...[/dim]")
        sub_emails = harvest_from_subdomains(domain)
        all_emails |= sub_emails
        if sub_emails:
            console.print(f"  [dim]  Subdomains: {len(sub_emails)} found[/dim]")

    console.print()

    if not all_emails:
        console.print("  [yellow]No email addresses found.[/yellow]")
        return

    # Sort: domain emails first, then others
    domain_emails = sorted(
        [e for e in all_emails if e.endswith(f"@{domain}")]
    )
    other_emails = sorted(
        [e for e in all_emails if not e.endswith(f"@{domain}")]
    )
    ordered = domain_emails + other_emails

    console.print(f"  [bold green]> {len(ordered)} unique email(s) found:[/bold green]\n")
    for email in ordered:
        tag = "[bold cyan]@domain[/bold cyan]" if email.endswith(f"@{domain}") \
              else "[dim]other[/dim]"
        console.print(f"    {tag}  {email}")
        reporter.add("Email Harvest", {
            "email": email,
            "domain": domain,
            "on_domain": str(email.endswith(f"@{domain}")),
            "source": "email-harvest",
        })

    console.print(f"\n  [dim]Total: {len(domain_emails)} on-domain, "
                  f"{len(other_emails)} other[/dim]")
