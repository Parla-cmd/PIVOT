"""
Folkbokföring / Swedish Public Registry
-----------------------------------------
Aggregates publicly available Swedish registry data:
  - Folkbokföringsadress (registered address) via Ratsit + Merinfo
  - Taxerad inkomst (declared income is public in Sweden)
  - Betalningsanmärkningar (payment defaults) via Kronofogden
  - Styrelseuppdrag (board positions) via Allabolag
  - Fordonsregistret via Transportstyrelsen (plate lookup)

All sources are public records under Swedish offentlighetsprincipen.
"""
import re
from .utils import fetch, soup, console, print_section, print_result, safe
from . import reporter as _reporter


# ── helpers ────────────────────────────────────────────────────────────────────

def _ok(msg: str):
    console.print(f"    [green][+][/green] {safe(msg)}")

def _warn(msg: str):
    console.print(f"    [yellow][!][/yellow] {safe(msg)}")

def _info(key: str, val: str):
    if val:
        console.print(f"    [dim]{key}:[/dim] {safe(val)}")

def _divider(label: str):
    console.print(f"\n  [bold cyan][ {label} ][/bold cyan]")


# ── Ratsit ─────────────────────────────────────────────────────────────────────

def _ratsit_search(name: str, city: str = "") -> list[dict]:
    """Search Ratsit.se for a person and return profile cards."""
    q = name.replace(" ", "+")
    url = f"https://www.ratsit.se/hitta-person?query={q}"
    if city:
        url += f"&location={city.replace(' ', '+')}"
    resp = fetch(url, timeout=12)
    if not resp:
        return []
    bs = soup(resp)
    results = []
    # Each result card
    for card in bs.select("div.person-result, article.person-card, div[class*='personCard'], div[class*='person-card']"):
        name_el  = card.select_one("h2, h3, .name, [class*='name']")
        addr_el  = card.select_one(".address, [class*='address'], [class*='ort']")
        age_el   = card.select_one(".age, [class*='age'], [class*='alder']")
        link_el  = card.select_one("a[href*='/person/'], a[href*='/hitta-person/']")

        name_val = name_el.get_text(strip=True) if name_el else ""
        addr_val = addr_el.get_text(strip=True) if addr_el else ""
        age_val  = age_el.get_text(strip=True)  if age_el  else ""
        link_val = link_el["href"] if link_el and link_el.get("href") else ""
        if link_val and link_val.startswith("/"):
            link_val = "https://www.ratsit.se" + link_val

        if name_val:
            results.append({
                "name":    name_val,
                "address": addr_val,
                "age":     age_val,
                "profile": link_val,
                "source":  "ratsit.se",
            })
    return results


def _ratsit_profile(profile_url: str) -> dict:
    """Scrape a Ratsit person profile page for income and details."""
    if not profile_url:
        return {}
    resp = fetch(profile_url, timeout=12)
    if not resp:
        return {}
    bs = soup(resp)
    data: dict = {}

    # Income row (taxerad inkomst is public)
    for row in bs.select("tr, .info-row, div[class*='income'], div[class*='inkomst']"):
        text = row.get_text(" ", strip=True)
        if "inkomst" in text.lower() or "kr" in text.lower():
            # Extract number
            m = re.search(r"([\d\s]+)\s*kr", text, re.IGNORECASE)
            if m:
                data["income"] = m.group(0).strip()
                break

    # Board positions
    board_links = bs.select("a[href*='/foretag/'], a[href*='/bolag/'], [class*='company'] a")
    data["board_positions"] = [
        {"name": a.get_text(strip=True), "url": a["href"]}
        for a in board_links[:10]
        if a.get_text(strip=True)
    ]

    # Phone numbers on profile
    phones = re.findall(r"0\d[\d\s\-]{6,10}", resp.text)
    data["phones"] = list(set(phones))[:5]

    # Email
    emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", resp.text)
    data["emails"] = [e for e in set(emails) if not e.endswith(".png")][:5]

    return data


# ── Kronofogden ────────────────────────────────────────────────────────────────

def check_kronofogden(name: str) -> list[dict]:
    """
    Check Kronofogden's public register for payment defaults.
    Kronofogden has a public search at kronofogden.se.
    Returns list of found records.
    """
    results = []
    # Kronofogden's online search
    url = f"https://www.kronofogden.se/kontroll-av-skulder?sokning={name.replace(' ', '+')}"
    resp = fetch(url, timeout=12)
    if not resp:
        return []

    bs = soup(resp)
    # Look for result tables or "found" indicators
    hits = bs.select("table tr, .result-row, .skuld-row, [class*='result']")
    for row in hits:
        text = row.get_text(" ", strip=True)
        if name.split()[0].lower() in text.lower() and len(text) > 10:
            results.append({"record": text[:200], "source": "kronofogden.se"})

    # Also check for "inga skulder" (no debts) message
    page_text = bs.get_text()
    if "inga" in page_text.lower() and ("skuld" in page_text.lower() or "anmärk" in page_text.lower()):
        results.append({"record": "No payment defaults found", "source": "kronofogden.se"})

    return results


# ── Transportstyrelsen / Fordonsregistret ──────────────────────────────────────

def lookup_vehicle(reg_plate: str) -> dict:
    """
    Look up a Swedish vehicle registration plate.
    Uses the public check at Transportstyrelsen.
    """
    plate = reg_plate.upper().replace(" ", "").replace("-", "")
    url   = f"https://fu-regnr.transportstyrelsen.se/extweb/reg/{plate}"
    resp  = fetch(url, timeout=12)
    if not resp:
        # Try alternative public source
        alt = f"https://www.biluppgifter.se/fordon/{plate}"
        resp = fetch(alt, timeout=12)
        if not resp:
            return {}

    bs = soup(resp)
    data: dict = {"plate": reg_plate, "source": resp.url}

    label_map = {
        "märke":         "make",
        "modell":        "model",
        "årsmodell":     "year",
        "färg":          "color",
        "bränsle":       "fuel",
        "karosseri":     "body",
        "status":        "status",
        "besiktning":    "inspection_due",
        "ägare":         "owner",
        "registrering":  "registered",
    }

    for row in bs.select("tr, .info-row, dl dt"):
        label = row.get_text(strip=True).lower()
        for swe, eng in label_map.items():
            if swe in label:
                val_el = row.find_next_sibling() or row.find_next("td") or row.find_next("dd")
                if val_el:
                    data[eng] = val_el.get_text(strip=True)
                break

    return data


# ── Main run ───────────────────────────────────────────────────────────────────

def run_person(name: str, city: str = "", personnummer: str = ""):
    """Full folkbokföring lookup for a person."""
    print_section("FOLKBOKFÖRING / SWEDISH PUBLIC REGISTRY")
    console.print(f"  [dim]Name:[/dim] [bold]{name}[/bold]"
                  + (f"  [dim]City:[/dim] {city}" if city else "")
                  + (f"  [dim]PNR:[/dim] {personnummer}" if personnummer else ""))

    # ── Ratsit search ──────────────────────────────────────────────────────────
    _divider("REGISTERED ADDRESS & IDENTITY — Ratsit.se")
    console.print("  [dim]Searching ratsit.se...[/dim]")
    persons = _ratsit_search(name, city)

    if not persons:
        _warn("No results from Ratsit.se")
    else:
        for p in persons[:5]:
            _ok(f"{p['name']}"
                + (f"  |  {p['address']}" if p.get("address") else "")
                + (f"  |  Age {p['age']}" if p.get("age") else ""))
            if p.get("profile"):
                console.print(f"      [cyan]{p['profile']}[/cyan]")
            _reporter.add("Folkbokföring / Identity", {
                "name":    p["name"],
                "address": p.get("address", ""),
                "age":     p.get("age", ""),
                "source":  "ratsit.se",
                "profile": p.get("profile", ""),
            })

    # ── Deep profile for first match ───────────────────────────────────────────
    if persons and persons[0].get("profile"):
        _divider("INCOME & BOARD POSITIONS — Ratsit.se profile")
        profile = _ratsit_profile(persons[0]["profile"])

        if profile.get("income"):
            _info("Taxerad inkomst", profile["income"])
            _reporter.add("Folkbokföring / Income", {
                "name":   name,
                "income": profile["income"],
                "source": "ratsit.se",
            })

        boards = profile.get("board_positions", [])
        if boards:
            console.print(f"    Board positions ({len(boards)}):")
            for b in boards[:8]:
                console.print(f"      [green][+][/green] {safe(b['name'])}")
                _reporter.add("Folkbokföring / Board Position", {
                    "name":    name,
                    "company": b["name"],
                    "source":  "ratsit.se",
                })

        if profile.get("phones"):
            _info("Related phones", ", ".join(profile["phones"]))
        if profile.get("emails"):
            _info("Related emails", ", ".join(profile["emails"]))

    # ── Kronofogden ────────────────────────────────────────────────────────────
    _divider("PAYMENT DEFAULTS — Kronofogden")
    console.print("  [dim]Checking kronofogden.se...[/dim]")
    kf_results = check_kronofogden(name)
    if kf_results:
        for r in kf_results:
            rec = r.get("record", "")
            if "No payment" in rec:
                _ok(rec)
            else:
                _warn(rec)
            _reporter.add("Folkbokföring / Kronofogden", {
                "name":   name,
                "record": rec,
                "source": "kronofogden.se",
            })
    else:
        console.print("  [dim]  No data returned from Kronofogden.[/dim]")


def run_vehicle(plate: str):
    """Vehicle registration plate lookup."""
    print_section(f"FORDONSREGISTRET — {plate}")
    console.print("  [dim]Looking up via Transportstyrelsen / Biluppgifter...[/dim]")

    data = lookup_vehicle(plate)
    if not data or len(data) <= 2:
        _warn("No vehicle data found.")
        return

    _ok(f"Plate: {plate}")
    for key in ("make", "model", "year", "color", "fuel", "body", "status", "inspection_due"):
        if data.get(key):
            _info(key.replace("_", " ").title(), data[key])
    if data.get("source"):
        console.print(f"    [dim]Source:[/dim] [cyan]{data['source']}[/cyan]")

    _reporter.add("Fordonsregistret", {**data})
