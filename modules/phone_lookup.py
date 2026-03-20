"""
Phone Lookup Module
Sources: hitta.se reverse phone, eniro.se reverse phone
"""
import re
import urllib.parse
from .utils import fetch, soup, console, print_section, print_result


def normalize_phone(phone: str) -> tuple[str, str]:
    """Return (digits_only, formatted_se). Swedish numbers start with 0 or +46."""
    digits = re.sub(r"[^0-9]", "", phone.replace("+46", "0"))
    if not digits.startswith("0"):
        digits = "0" + digits
    return digits, digits


def search_hitta_phone(phone: str) -> list[dict]:
    results = []
    digits, _ = normalize_phone(phone)
    url = f"https://www.hitta.se/sok?vad={urllib.parse.quote_plus(digits)}&typ=alla"

    resp = fetch(url)
    if not resp:
        return results

    bs = soup(resp)
    cards = bs.select("article, .search-result-item, [class*='result']")

    for card in cards[:10]:
        entry = {}
        name_el = card.select_one("h2, h3, [class*='name']")
        addr_el = card.select_one("[class*='address'], address")
        phone_el = card.select_one("[class*='phone'], [class*='telefon']")

        if name_el:
            entry["name"] = name_el.get_text(strip=True)
        if addr_el:
            entry["address"] = addr_el.get_text(separator=" ", strip=True)
        if phone_el:
            entry["phone"] = phone_el.get_text(strip=True)

        if entry.get("name"):
            entry["source"] = "hitta.se"
            results.append(entry)

    return results


def search_eniro_phone(phone: str) -> list[dict]:
    results = []
    digits, _ = normalize_phone(phone)
    url = f"https://www.eniro.se/query?search_word={urllib.parse.quote_plus(digits)}&what=wp"

    resp = fetch(url)
    if not resp:
        return results

    bs = soup(resp)
    cards = bs.select(".hit, [class*='result']")

    for card in cards[:10]:
        entry = {}
        name_el = card.select_one("h2, h3, .name")
        addr_el = card.select_one(".address, [class*='address']")
        phone_el = card.select_one(".phone, [class*='phone']")

        if name_el:
            entry["name"] = name_el.get_text(strip=True)
        if addr_el:
            entry["address"] = addr_el.get_text(separator=" ", strip=True)
        if phone_el:
            entry["phone"] = phone_el.get_text(strip=True)

        if entry.get("name"):
            entry["source"] = "eniro.se"
            results.append(entry)

    return results


def classify_phone(phone: str) -> str:
    """Classify Swedish phone number type."""
    digits, _ = normalize_phone(phone)
    prefixes = {
        "010": "Virtual/VoIP",
        "0200": "Free",
        "020": "Toll-free",
        "070": "Mobile (Telia)",
        "072": "Mobile (Tre)",
        "073": "Mobile (Tele2/Comviq)",
        "076": "Mobile (Tele2)",
        "079": "Mobile",
        "074": "Mobile (Telenor)",
        "0700": "Mobile",
        "08": "Stockholm",
        "031": "Göteborg",
        "040": "Malmö",
        "011": "Norrköping",
        "013": "Linköping",
        "018": "Uppsala",
        "019": "Örebro",
        "021": "Västerås",
        "023": "Falun",
        "026": "Gävle",
        "033": "Borås",
        "036": "Jönköping",
        "042": "Helsingborg",
        "044": "Kristianstad",
        "046": "Lund",
        "054": "Karlstad",
        "060": "Sundsvall",
        "063": "Östersund",
        "090": "Umeå",
    }
    for prefix, label in sorted(prefixes.items(), key=lambda x: -len(x[0])):
        if digits.startswith(prefix):
            return label
    return "Unknown"


def get_results(phone: str) -> list[dict]:
    """Return raw results without printing."""
    all_results = search_hitta_phone(phone) + search_eniro_phone(phone)
    seen, unique = set(), []
    for r in all_results:
        key = r.get("name", "")
        if key and key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def run(phone: str):
    print_section("PHONE LOOKUP")
    digits, _ = normalize_phone(phone)
    phone_type = classify_phone(phone)
    console.print(f"  [dim]Number:[/dim] [bold]{digits}[/bold]  "
                  f"[dim]Type:[/dim] [bold]{phone_type}[/bold]\n")

    all_results = []

    console.print("  [dim]Searching hitta.se...[/dim]")
    all_results += search_hitta_phone(phone)

    console.print("  [dim]Searching eniro.se...[/dim]")
    all_results += search_eniro_phone(phone)

    if not all_results:
        console.print("  [yellow]No results found for this number.[/yellow]")
        return

    seen = set()
    for r in all_results:
        key = r.get("name", "")
        if key in seen:
            continue
        seen.add(key)
        console.print(f"  [bold green]> Result[/bold green] [dim]({r['source']})[/dim]")
        for field in ("name", "address", "phone"):
            if r.get(field):
                print_result(f"    {field.capitalize()}", r[field])
        console.print()
