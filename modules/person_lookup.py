"""
Person Lookup Module -- Swedish public directories
Sources: hitta.se, eniro.se, merinfo.se, ratsit.se
"""
import json
import urllib.parse
from .utils import (
    fetch, soup, console, print_section, print_result, validate_personnummer
)


def search_hitta(name: str = "", city: str = "") -> list[dict]:
    """Search hitta.se — reads structured JSON from Next.js __NEXT_DATA__."""
    results = []
    query = urllib.parse.quote_plus(name)
    city_q = urllib.parse.quote_plus(city) if city else ""
    url = (f"https://www.hitta.se/sok?vad={query}&geo_area={city_q}&typ=personer"
           if city_q else f"https://www.hitta.se/sok?vad={query}&typ=personer")

    resp = fetch(url)
    if not resp:
        return results

    bs = soup(resp)
    script = bs.find("script", id="__NEXT_DATA__")
    if not script:
        return results

    try:
        data = json.loads(script.string)
        persons = (data.get("props", {})
                       .get("pageProps", {})
                       .get("result", {})
                       .get("persons", []))
    except (json.JSONDecodeError, AttributeError):
        return results

    for p in persons[:15]:
        # Phone may be a list of dicts like [{"displayAs": "070-..."}, ...]
        raw_phone = p.get("phone", "")
        if isinstance(raw_phone, list):
            phone_str = ", ".join(
                ph.get("displayAs", "") for ph in raw_phone if ph.get("displayAs")
            )
        else:
            phone_str = str(raw_phone) if raw_phone else ""

        entry = {
            "name":    p.get("displayName") or p.get("name", ""),
            "address": p.get("addressLine") or p.get("address", ""),
            "city":    p.get("zipCity", ""),
            "age":     str(p.get("age", "")) if p.get("age") else "",
            "phone":   phone_str,
            "source":  "hitta.se",
        }
        entry = {k: v for k, v in entry.items() if v}
        if entry.get("name"):
            results.append(entry)

    return results


def search_eniro(name: str, city: str = "") -> list[dict]:
    """Search eniro.se — JS-rendered, results limited without browser."""
    results = []
    query = urllib.parse.quote_plus(name)
    city_q = urllib.parse.quote_plus(city) if city else ""
    url = (f"https://www.eniro.se/query?search_word={query}&what=wp&geo_area={city_q}"
           if city_q else f"https://www.eniro.se/query?search_word={query}&what=wp")

    resp = fetch(url)
    if not resp:
        return results

    bs = soup(resp)
    # Eniro renders results via JS — try any visible name links in static HTML
    for a in bs.select("a[href*='/person/'], a[href*='/wp/']")[:10]:
        text = a.get_text(strip=True)
        if text and len(text) > 3:
            results.append({"name": text, "url": a.get("href", ""), "source": "eniro.se"})

    return results


def search_merinfo(name: str) -> list[dict]:
    """
    Search merinfo.se via Playwright — intercepts the HMAC-signed JSON API
    response that the Vue app fires on page load.
    """
    results = []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return results

    import json as _json
    import re as _re

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                locale="sv-SE",
                viewport={"width": 1280, "height": 900},
            )
            page = ctx.new_page()

            api_result: list = []

            def on_response(resp):
                if "merinfo.se/api/v1/search/results" in resp.url:
                    try:
                        data = resp.json()
                        api_result.append(data)
                    except Exception:
                        pass

            page.on("response", on_response)

            query = urllib.parse.quote_plus(name)
            page.goto(
                f"https://www.merinfo.se/search?who={query}&what=persons",
                timeout=25000,
            )
            page.wait_for_timeout(5000)
            browser.close()

        if not api_result:
            return results

        data = api_result[0]
        for section in data.get("results", []):
            for item in section.get("items", [])[:15]:
                if item.get("type") != "person":
                    continue
                # Strip HTML tags from name
                raw_name = item.get("name", "")
                clean_name = _re.sub(r"<[^>]+>", "", raw_name)
                pnr = item.get("personalNumber", "")
                pnr_clean = _re.sub(r"<[^>]+>", "", pnr)

                # Address may be a list of dicts
                raw_addr = item.get("address", "")
                if isinstance(raw_addr, list) and raw_addr:
                    a = raw_addr[0]
                    addr_str = f"{a.get('street','')} {a.get('zip_code','')} {a.get('city','')}".strip()
                else:
                    addr_str = str(raw_addr) if raw_addr else ""

                entry = {
                    "name":    clean_name.strip(),
                    "pnr":     pnr_clean.strip() if pnr_clean.strip() else "",
                    "address": addr_str,
                    "phone":   item.get("phoneNumber", "") or item.get("phone", ""),
                    "source":  "merinfo.se",
                }
                entry = {k: v for k, v in entry.items() if v}
                if entry.get("name"):
                    results.append(entry)

    except Exception:
        pass

    return results


def search_ratsit(name: str) -> list[dict]:
    """
    Ratsit.se requires login for all searches (Cloudflare Turnstile + account wall).
    Returns an empty list — included as a placeholder for future authenticated access.
    """
    return []


def run(name: str, city: str = "", personnummer: str = "") -> None:
    print_section("PERSON LOOKUP")

    if personnummer and not validate_personnummer(personnummer):
        console.print("  [red]Invalid personnummer format.[/red]")
        return

    console.print(f"  [dim]Target:[/dim] [bold]{name}[/bold]"
                  + (f"  [dim]City:[/dim] {city}" if city else "")
                  + (f"  [dim]PNR:[/dim] {personnummer}" if personnummer else ""))
    console.print()

    all_results = []

    console.print("  [dim]Searching hitta.se...[/dim]")
    hitta = search_hitta(name, city)
    all_results += hitta
    console.print(f"  [dim]  → {len(hitta)} results[/dim]")

    console.print("  [dim]Searching eniro.se (JS-site, partial)...[/dim]")
    all_results += search_eniro(name, city)

    console.print("  [dim]Searching merinfo.se (Playwright)...[/dim]")
    merinfo = search_merinfo(name)
    all_results += merinfo
    console.print(f"  [dim]  -> {len(merinfo)} results[/dim]")

    console.print("  [dim]Ratsit.se requires login — skipped.[/dim]")

    if not all_results:
        console.print("  [yellow]No results found.[/yellow]")
        return

    seen = set()
    for r in all_results:
        key = (r.get("name", ""), r.get("address", ""))
        if key in seen:
            continue
        seen.add(key)
        console.print(f"  [bold green]> Result[/bold green] [dim]({r['source']})[/dim]")
        for field in ("name", "address", "age", "phone", "income", "profile_url"):
            if r.get(field):
                print_result(f"    {field.capitalize()}", r[field])
        console.print()

    console.print(f"  [dim]Total unique results: {len(seen)}[/dim]")
