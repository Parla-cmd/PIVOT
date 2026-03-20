"""
Person Lookup Module -- Swedish public directories
Sources: hitta.se, eniro.se, merinfo.se
"""
import urllib.parse
from .utils import (
    fetch, soup, console, print_section, print_result, validate_personnummer
)


def search_hitta(name: str = "", city: str = "") -> list[dict]:
    """Search hitta.se for a person by name and optional city."""
    results = []
    query = urllib.parse.quote_plus(name)
    city_q = urllib.parse.quote_plus(city) if city else ""
    url = f"https://www.hitta.se/person/{query}/{city_q}" if city_q else \
          f"https://www.hitta.se/sok?vad={query}&typ=personer"

    resp = fetch(url)
    if not resp:
        return results

    bs = soup(resp)
    # Person cards on hitta.se
    cards = bs.select("article.person-card, div.search-result-item, li.person")
    if not cards:
        # Try generic result blocks
        cards = bs.select("[class*='person']")

    for card in cards[:10]:
        entry = {}
        name_el = card.select_one("h2, h3, [class*='name']")
        addr_el = card.select_one("[class*='address'], [class*='addr'], address")
        age_el = card.select_one("[class*='age'], [class*='ålder']")
        phone_el = card.select_one("[class*='phone'], [class*='telefon']")

        if name_el:
            entry["name"] = name_el.get_text(strip=True)
        if addr_el:
            entry["address"] = addr_el.get_text(separator=" ", strip=True)
        if age_el:
            entry["age"] = age_el.get_text(strip=True)
        if phone_el:
            entry["phone"] = phone_el.get_text(strip=True)

        if entry:
            entry["source"] = "hitta.se"
            results.append(entry)

    return results


def search_eniro(name: str, city: str = "") -> list[dict]:
    """Search eniro.se for a person."""
    results = []
    query = urllib.parse.quote_plus(name)
    city_q = urllib.parse.quote_plus(city) if city else ""
    url = f"https://www.eniro.se/query?search_word={query}&what=wp" + \
          (f"&geo_area={city_q}" if city_q else "")

    resp = fetch(url)
    if not resp:
        return results

    bs = soup(resp)
    cards = bs.select(".hit, .person-hit, [class*='person-result']")

    for card in cards[:10]:
        entry = {}
        name_el = card.select_one("h2, h3, .name, [class*='name']")
        addr_el = card.select_one(".address, [class*='address']")
        phone_el = card.select_one(".phone, [class*='phone']")

        if name_el:
            entry["name"] = name_el.get_text(strip=True)
        if addr_el:
            entry["address"] = addr_el.get_text(separator=" ", strip=True)
        if phone_el:
            entry["phone"] = phone_el.get_text(strip=True)

        if entry:
            entry["source"] = "eniro.se"
            results.append(entry)

    return results


def search_merinfo(name: str) -> list[dict]:
    """Search merinfo.se for a person."""
    results = []
    query = urllib.parse.quote_plus(name)
    url = f"https://www.merinfo.se/search?who={query}&what=persons"

    resp = fetch(url)
    if not resp:
        return results

    bs = soup(resp)
    cards = bs.select(".person-card, .result-item, [class*='person']")

    for card in cards[:10]:
        entry = {}
        name_el = card.select_one("h2, h3, [class*='name']")
        addr_el = card.select_one("[class*='address'], address")
        age_el = card.select_one("[class*='age']")

        if name_el:
            entry["name"] = name_el.get_text(strip=True)
        if addr_el:
            entry["address"] = addr_el.get_text(separator=" ", strip=True)
        if age_el:
            entry["age"] = age_el.get_text(strip=True)

        if entry:
            entry["source"] = "merinfo.se"
            results.append(entry)

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
    all_results += search_hitta(name, city)

    console.print("  [dim]Searching eniro.se...[/dim]")
    all_results += search_eniro(name, city)

    console.print("  [dim]Searching merinfo.se...[/dim]")
    all_results += search_merinfo(name)

    console.print("  [dim]Searching ratsit.se...[/dim]")
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
