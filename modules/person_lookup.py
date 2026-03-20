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
    """Search merinfo.se — uses Web Components, results limited without browser."""
    results = []
    query = urllib.parse.quote_plus(name)
    url = f"https://www.merinfo.se/search?who={query}&what=persons"

    resp = fetch(url)
    if not resp:
        return results

    bs = soup(resp)
    # Merinfo renders via Web Components — extract any embedded JSON
    for script in bs.find_all("script", type="application/json"):
        try:
            import json as _json
            data = _json.loads(script.string or "")
            if isinstance(data, list):
                for item in data[:10]:
                    if isinstance(item, dict) and item.get("name"):
                        item["source"] = "merinfo.se"
                        results.append(item)
        except Exception:
            pass

    return results


def search_ratsit(name: str) -> list[dict]:
    """
    Search ratsit.se for a person.
    Ratsit is one of Sweden's most comprehensive person registries,
    showing income, tax, address history and board memberships.
    Note: Site uses heavy JS rendering; scraping returns partial data.
    """
    results = []
    query = urllib.parse.quote_plus(name)
    url = f"https://www.ratsit.se/sok/person?vad={query}"

    resp = fetch(url)
    if not resp:
        return results

    bs = soup(resp)

    # Try multiple selectors as ratsit updates their markup
    cards = bs.select(
        ".hit, .person, .search-result, [class*='person'], "
        "[class*='hit'], article, .card"
    )

    for card in cards[:10]:
        entry = {}
        name_el = card.select_one(
            "h2, h3, h4, [class*='name'], [class*='Name']"
        )
        addr_el = card.select_one(
            "[class*='address'], [class*='Address'], [class*='ort'], address"
        )
        age_el = card.select_one(
            "[class*='age'], [class*='Age'], [class*='born'], [class*='ar']"
        )
        income_el = card.select_one(
            "[class*='income'], [class*='Income'], [class*='inkomst']"
        )
        link_el = card.select_one("a[href*='/person/'], a[href*='/foretagare/']")

        if name_el:
            entry["name"] = name_el.get_text(strip=True)
        if addr_el:
            entry["address"] = addr_el.get_text(separator=" ", strip=True)
        if age_el:
            entry["age"] = age_el.get_text(strip=True)
        if income_el:
            entry["income"] = income_el.get_text(strip=True)
        if link_el:
            href = link_el.get("href", "")
            entry["profile_url"] = (
                href if href.startswith("http")
                else f"https://www.ratsit.se{href}"
            )

        if entry.get("name"):
            entry["source"] = "ratsit.se"
            results.append(entry)

    return results


def run(name: str, city: str = "", personnummer: str = ""):
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

    console.print("  [dim]Searching merinfo.se (JS-site, partial)...[/dim]")
    all_results += search_merinfo(name)

    console.print("  [dim]Searching ratsit.se (Cloudflare protected, partial)...[/dim]")
    all_results += search_ratsit(name)

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
