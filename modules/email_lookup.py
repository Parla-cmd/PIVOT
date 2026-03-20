"""
Email Lookup Module
- MX record validation
- Breach check via haveibeenpwned.com API (v3, no key for public checks)
- Username extraction and social profile hints
"""
import re
import hashlib
import requests
import dns.resolver
from .utils import fetch, console, print_section, print_result
from .config import get as cfg


def validate_email_format(email: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", email))


def check_mx(domain: str) -> list[str]:
    """Check if domain has MX records (mail can be delivered)."""
    try:
        answers = dns.resolver.resolve(domain, "MX")
        return sorted([str(r.exchange).rstrip(".") for r in answers],
                      key=lambda x: x)
    except Exception:
        return []


def check_hibp(email: str) -> list[dict]:
    """
    Check HaveIBeenPwned for breaches.
    Uses the free /breachedaccount endpoint (rate-limited).
    Note: Full breach data requires an API key; this returns breach names only.
    """
    results = []
    url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{requests.utils.quote(email)}"
    api_key = cfg("HIBP_API_KEY")
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": "sweden-osint-educational-tool",
                "hibp-api-key": api_key,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            for breach in resp.json():
                results.append({
                    "name": breach.get("Name", ""),
                    "domain": breach.get("Domain", ""),
                    "date": breach.get("BreachDate", ""),
                    "pwn_count": str(breach.get("PwnCount", "")),
                    "data_classes": ", ".join(breach.get("DataClasses", [])),
                })
        elif resp.status_code == 404:
            pass  # No breaches found
        elif resp.status_code == 401:
            results.append({"note": "HIBP API key required -- add HIBP_API_KEY to .env"})
        elif resp.status_code == 429:
            results.append({"note": "HIBP rate limit hit -- try again later"})
    except Exception as e:
        results.append({"note": f"HIBP check failed: {e}"})
    return results


def extract_username(email: str) -> str:
    return email.split("@")[0]


def social_hints(username: str) -> list[str]:
    """
    Generate likely social media profile URLs for a username.
    Returns URLs to manually verify -- does NOT confirm existence.
    """
    platforms = {
        "LinkedIn": f"https://www.linkedin.com/in/{username}",
        "GitHub": f"https://github.com/{username}",
        "Twitter/X": f"https://twitter.com/{username}",
        "Instagram": f"https://instagram.com/{username}",
        "Facebook": f"https://facebook.com/{username}",
        "Reddit": f"https://reddit.com/user/{username}",
    }
    return [f"{platform}: {url}" for platform, url in platforms.items()]


def check_gravatar(email: str) -> str:
    """Check if a Gravatar exists for the email."""
    email_hash = hashlib.md5(email.lower().strip().encode()).hexdigest()
    url = f"https://www.gravatar.com/avatar/{email_hash}?d=404"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return f"https://www.gravatar.com/avatar/{email_hash}"
    except Exception:
        pass
    return ""


def get_results(email: str) -> dict:
    """Return raw results without printing."""
    if not validate_email_format(email):
        return {}
    username, domain = email.split("@", 1)
    return {
        "username": username,
        "domain": domain,
        "mx": check_mx(domain),
        "gravatar": check_gravatar(email),
        "breaches": check_hibp(email),
    }


def run(email: str) -> None:
    print_section("EMAIL LOOKUP")

    if not validate_email_format(email):
        console.print("  [red]Invalid email format.[/red]")
        return

    username, domain = email.split("@", 1)
    console.print(f"  [dim]Email:[/dim] [bold]{email}[/bold]\n")

    # MX check
    console.print("  [dim]Checking MX records...[/dim]")
    mx = check_mx(domain)
    if mx:
        console.print("  [bold green]> Mail Servers (MX)[/bold green]")
        for server in mx:
            print_result("    MX", server)
        console.print()
    else:
        console.print("  [yellow]No MX records found -- domain may not receive mail.[/yellow]\n")

    # Gravatar
    console.print("  [dim]Checking Gravatar...[/dim]")
    gravatar = check_gravatar(email)
    if gravatar:
        console.print("  [bold green]> Gravatar Found[/bold green]")
        print_result("    URL", gravatar)
        console.print()
    else:
        console.print("  [dim]No Gravatar found.[/dim]\n")

    # HIBP
    console.print("  [dim]Checking HaveIBeenPwned...[/dim]")
    breaches = check_hibp(email)
    if breaches:
        if "note" in breaches[0]:
            console.print(f"  [yellow]{breaches[0]['note']}[/yellow]")
        else:
            console.print(f"  [bold red]> Found in {len(breaches)} breach(es)![/bold red]")
            for b in breaches:
                console.print(f"  [red]  • {b['name']}[/red] "
                               f"[dim]({b['date']}, {b['pwn_count']} accounts)[/dim]")
                if b.get("data_classes"):
                    print_result("    Data exposed", b["data_classes"])
    else:
        console.print("  [bold green]  Not found in any known breaches.[/bold green]")
    console.print()

    # Username hints
    console.print("  [bold green]> Username Social Profile Hints[/bold green] "
                  "[dim](verify manually)[/dim]")
    for hint in social_hints(username):
        console.print(f"    [cyan]{hint}[/cyan]")
    console.print()
