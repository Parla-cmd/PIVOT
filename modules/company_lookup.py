"""
Company Lookup Module
Sources: Bolagsverket (official API), allabolag.se, hitta.se företag
"""
import urllib.parse
import requests
from .utils import (
    fetch, soup, console, print_section, print_result,
    validate_org_number, format_org_number
)


BOLAGSVERKET_API = "https://api.bolagsverket.se/foretagsinformation/v1"


def lookup_bolagsverket(org_nr: str) -> dict | None:
    """
    Query Bolagsverket's open REST API for company details.
    Endpoint: GET /foretagsinformation/v1/foretagsuppgifter/{orgNr}
    """
    cleaned = org_nr.replace("-", "").replace(" ", "")
    url = f"{BOLAGSVERKET_API}/foretagsuppgifter/{cleaned}"
    try:
        resp = requests.get(url, timeout=10,
                            headers={"Accept": "application/json"})
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def search_allabolag(query: str) -> list[dict]:
    """Search allabolag.se for companies."""
    results = []
    q = urllib.parse.quote_plus(query)
    url = f"https://www.allabolag.se/what/{q}/where/"

    resp = fetch(url)
    if not resp:
        return results

    bs = soup(resp)
    rows = bs.select(".company-row, .search-result, tr.result-row, [class*='company']")

    for row in rows[:15]:
        entry = {}
        name_el = row.select_one("h2, h3, .company-name, [class*='name']")
        org_el = row.select_one("[class*='org'], [class*='orgnr']")
        addr_el = row.select_one("[class*='address'], address")
        status_el = row.select_one("[class*='status']")
        turnover_el = row.select_one("[class*='turnover'], [class*='omsättning']")

        if name_el:
            entry["name"] = name_el.get_text(strip=True)
        if org_el:
            entry["org_nr"] = org_el.get_text(strip=True)
        if addr_el:
            entry["address"] = addr_el.get_text(separator=" ", strip=True)
        if status_el:
            entry["status"] = status_el.get_text(strip=True)
        if turnover_el:
            entry["turnover"] = turnover_el.get_text(strip=True)

        if entry:
            entry["source"] = "allabolag.se"
            results.append(entry)

    return results


def search_hitta_foretag(query: str) -> list[dict]:
    """Search hitta.se for companies."""
    results = []
    q = urllib.parse.quote_plus(query)
    url = f"https://www.hitta.se/sok?vad={q}&typ=foretag"

    resp = fetch(url)
    if not resp:
        return results

    bs = soup(resp)
    cards = bs.select("article.company-card, .company-hit, [class*='company']")

    for card in cards[:10]:
        entry = {}
        name_el = card.select_one("h2, h3, [class*='name']")
        addr_el = card.select_one("[class*='address'], address")
        phone_el = card.select_one("[class*='phone'], [class*='telefon']")
        cat_el = card.select_one("[class*='category'], [class*='kategori']")

        if name_el:
            entry["name"] = name_el.get_text(strip=True)
        if addr_el:
            entry["address"] = addr_el.get_text(separator=" ", strip=True)
        if phone_el:
            entry["phone"] = phone_el.get_text(strip=True)
        if cat_el:
            entry["category"] = cat_el.get_text(strip=True)

        if entry:
            entry["source"] = "hitta.se/företag"
            results.append(entry)

    return results


def run(query: str, org_nr: str = "") -> None:
    print_section("COMPANY LOOKUP")
    console.print(f"  [dim]Query:[/dim] [bold]{query or org_nr}[/bold]\n")

    # Try Bolagsverket API first if org_nr supplied
    if org_nr:
        if not validate_org_number(org_nr):
            console.print("  [red]Invalid organization number format.[/red]")
        else:
            fmt = format_org_number(org_nr)
            console.print(f"  [dim]Querying Bolagsverket API for {fmt}...[/dim]")
            data = lookup_bolagsverket(fmt)
            if data:
                console.print("  [bold green]> Bolagsverket Result[/bold green]")
                # Bolagsverket JSON structure varies; print key fields
                for k, v in data.items():
                    if isinstance(v, (str, int, float, bool)) and v:
                        print_result(f"    {k}", str(v))
                console.print()
            else:
                console.print("  [yellow]No Bolagsverket data found.[/yellow]\n")

    # Web searches
    search_query = query or org_nr
    all_results = []

    console.print("  [dim]Searching allabolag.se...[/dim]")
    all_results += search_allabolag(search_query)

    console.print("  [dim]Searching hitta.se/företag...[/dim]")
    all_results += search_hitta_foretag(search_query)

    if not all_results:
        console.print("  [yellow]No web results found.[/yellow]")
        return

    seen = set()
    for r in all_results:
        key = (r.get("name", ""), r.get("org_nr", ""))
        if key in seen:
            continue
        seen.add(key)
        console.print(f"  [bold green]> Result[/bold green] [dim]({r['source']})[/dim]")
        for field in ("name", "org_nr", "address", "phone", "category", "status", "turnover"):
            if r.get(field):
                print_result(f"    {field.replace('_', ' ').capitalize()}", r[field])
        console.print()

    console.print(f"  [dim]Total unique results: {len(seen)}[/dim]")
