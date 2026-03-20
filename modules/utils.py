"""
Shared utilities for Sweden OSINT Tool
"""
import re
import time
import random
import warnings
import requests
import cloudscraper
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console(force_terminal=True, highlight=False, legacy_windows=False)

# ── proxy / Tor support ────────────────────────────────────────────────────────
_PROXY: dict | None = None


def set_proxy(proxy_url: str):
    """
    Set a global proxy for all fetch() calls.
    Examples:
      set_proxy("socks5h://127.0.0.1:9050")   # Tor
      set_proxy("http://127.0.0.1:8080")       # Burp / HTTP proxy
      set_proxy("")                             # disable
    """
    global _PROXY
    if proxy_url:
        _PROXY = {"http": proxy_url, "https": proxy_url}
        console.print(f"  [dim]Proxy active:[/dim] [bold]{proxy_url}[/bold]")
    else:
        _PROXY = None


def get_proxy() -> dict | None:
    return _PROXY


def safe(text: str) -> str:
    """Replace characters that can't be printed in cp1252 terminals."""
    try:
        text.encode("cp1252")
        return text
    except (UnicodeEncodeError, AttributeError):
        return text.encode("cp1252", errors="replace").decode("cp1252")

HEADERS_LIST = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) "
                      "Gecko/20100101 Firefox/123.0",
        "Accept-Language": "sv-SE,sv;q=0.8,en-US;q=0.5",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
]


def get_headers():
    return random.choice(HEADERS_LIST)


# Shared cloudscraper session — bypasses TLS fingerprinting & Cloudflare challenges
_scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)


def fetch(url: str, timeout: int = 12, retries: int = 2) -> requests.Response | None:
    """GET request with cloudscraper (bot-bypass), retry logic and optional proxy."""
    for attempt in range(retries):
        try:
            time.sleep(random.uniform(0.8, 2.0))
            resp = _scraper.get(
                url,
                headers=get_headers(),
                timeout=timeout,
                proxies=_PROXY,
            )
            resp.raise_for_status()
            return resp
        except Exception as e:
            if attempt == retries - 1:
                console.print(f"  [yellow]Warning:[/yellow] Could not reach {url} -- {e}")
    return None


def soup(response: requests.Response) -> BeautifulSoup:
    return BeautifulSoup(response.text, "lxml")


def print_banner():
    banner = "  Sweden OSINT Tool\n  ==================\n  Educational Use Only\n"
    console.print(Panel(banner, border_style="cyan", style="bold cyan"))


def print_section(title: str):
    console.print(f"\n[bold magenta]--- {title} ---[/bold magenta]")


def print_result(key: str, value: str, indent: int = 2):
    pad = " " * indent
    console.print(f"{pad}[bold cyan]{key}:[/bold cyan] {value}")


def validate_personnummer(pnr: str) -> bool:
    """
    Basic Swedish personnummer validation.
    Accepts: YYYYMMDD-XXXX or YYYYMMDDXXXX or YYMMDD-XXXX
    """
    cleaned = re.sub(r"[^0-9]", "", pnr)
    return len(cleaned) in (10, 12)


def format_personnummer(pnr: str) -> str:
    """Normalize personnummer to YYYYMMDDXXXX."""
    cleaned = re.sub(r"[^0-9]", "", pnr)
    if len(cleaned) == 10:
        year_prefix = "20" if int(cleaned[:2]) <= 25 else "19"
        cleaned = year_prefix + cleaned
    return cleaned


def validate_org_number(org_nr: str) -> bool:
    """Swedish organization number: 6 digits - 4 digits."""
    cleaned = re.sub(r"[^0-9]", "", org_nr)
    return len(cleaned) == 10


def format_org_number(org_nr: str) -> str:
    cleaned = re.sub(r"[^0-9]", "", org_nr)
    if len(cleaned) == 10:
        return f"{cleaned[:6]}-{cleaned[6:]}"
    return org_nr
