"""
Correlation Module
------------------
Given a phone number or email, builds a full connected profile by chaining
all available modules: identity -> address -> companies -> social -> news.
"""
import re
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
import concurrent.futures
from .utils import console, print_section, safe
from .phone_lookup import get_results as phone_get, classify_phone, normalize_phone
from .email_lookup import get_results as email_get, validate_email_format
from .person_lookup import search_hitta, search_eniro, search_merinfo
from .company_lookup import search_allabolag
from .social_media import check_platform, PLATFORMS
from .news_search import search_google_news_se, search_svt
from .geolocation import geocode_address
from . import reporter


# --- helpers ------------------------------------------------------------------

def _divider(label: str) -> None:
    console.print(f"\n  [bold cyan][ {label} ][/bold cyan]")


def _info(key: str, value: str) -> None:
    console.print(f"    [dim]{key}:[/dim] {value}")


def _ok(msg: str) -> None:
    console.print(f"    [bold green][+][/bold green] {msg}")


def _warn(msg: str) -> None:
    console.print(f"    [yellow][!][/yellow] {msg}")


def _hit(label: str, url: str = "") -> None:
    if url:
        console.print(f"    [green][+] {label}[/green]  [cyan]{url}[/cyan]")
    else:
        console.print(f"    [green][+] {label}[/green]")


# --- social username check with progress bar ----------------------------------

def _check_username(username: str, threads: int = 12, label: str = "") -> list[dict]:
    found = []
    total = len(PLATFORMS)

    with Progress(
        SpinnerColumn("line"),
        TextColumn(f"  [cyan]{label or username}[/cyan]"),
        BarColumn(bar_width=24),
        TextColumn("[dim]{task.completed}/{task.total}[/dim]"),
        TextColumn("[bold green]{task.fields[found]} found[/bold green]"),
        TimeElapsedColumn(),
        console=console,
        transient=True,  # clears line when done
    ) as progress:
        task = progress.add_task("", total=total, found=0)
        with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as ex:
            futures = {ex.submit(check_platform, username, p): p for p in PLATFORMS}
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result.get("state") in ("confirmed", "possible"):
                    found.append(result)
                progress.update(task, advance=1, found=len(found))

    found.sort(key=lambda x: x["platform"])
    return found


# --- name -> username guesses -------------------------------------------------

def _name_to_usernames(full_name: str) -> list[str]:
    parts = full_name.lower().split()
    if len(parts) < 2:
        return [parts[0]] if parts else []
    first, last = parts[0], parts[-1]
    mid = parts[1] if len(parts) > 2 else ""
    candidates = [
        f"{first}{last}",
        f"{first}.{last}",
        f"{first}_{last}",
        f"{first[0]}{last}",
        f"{first}{last[0]}",
        f"{first}",
        f"{last}",
    ]
    if mid:
        candidates += [f"{first}{mid[0]}{last}", f"{first}.{mid[0]}.{last}"]
    return list(dict.fromkeys(candidates))


# --- phone correlation --------------------------------------------------------

def correlate_phone(phone: str) -> None:
    print_section("PHONE CORRELATION PROFILE")

    digits, _ = normalize_phone(phone)
    carrier = classify_phone(phone)
    console.print(f"  [dim]Input:[/dim] [bold]{digits}[/bold]  "
                  f"[dim]Carrier/Type:[/dim] [bold]{carrier}[/bold]")

    # Step 1: Identity lookup
    _divider("STEP 1 -- Identity lookup")
    console.print("  [dim]Searching hitta.se + eniro.se...[/dim]")
    raw = phone_get(phone)

    if not raw:
        _warn("No identity found for this number. Nothing to correlate.")
        return

    persons = []
    seen_names: set = set()
    for r in raw:
        name = r.get("name", "").strip()
        if name and name not in seen_names:
            seen_names.add(name)
            persons.append(r)
            _ok(f"{name}  |  {r.get('address', 'address unknown')}")
            reporter.add("Correlate / Identity", {
                "name": name,
                "address": r.get("address", ""),
                "phone": digits,
                "carrier": carrier,
                "source": r.get("source", ""),
            })

    # Step 2-6: Deep profile per person
    for person in persons:
        name = person.get("name", "")
        address = person.get("address", "")

        # Step 2: Deep person details
        _divider(f"STEP 2 -- Deep profile: {name}")
        console.print(f"  [dim]Searching merinfo.se for '{name}'...[/dim]")
        extras = search_merinfo(name)
        for e in extras[:3]:
            age = e.get("age", "")
            alt_addr = e.get("address", "")
            if age:
                _info("Age (merinfo)", age)
            if alt_addr and alt_addr != address:
                _info("Alt address", alt_addr)
            if age or alt_addr:
                reporter.add("Correlate / Person Details", {
                    "name": name, "age": age,
                    "alt_address": alt_addr, "source": "merinfo.se",
                })

        # Step 3: Geolocation
        if address:
            _divider(f"STEP 3 -- Address: {address}")
            console.print("  [dim]Geocoding...[/dim]")
            geo_results = geocode_address(address + " Sweden")
            for g in geo_results[:1]:
                _info("Coordinates", f"{g['lat']}, {g['lon']}")
                if g.get("municipality"):
                    _info("Municipality", g["municipality"])
                if g.get("county"):
                    _info("County", g["county"])
                _info("Map", g["maps_url"])
                reporter.add("Correlate / Geolocation", {
                    "name": name,
                    "address": address,
                    "lat": g["lat"],
                    "lon": g["lon"],
                    "municipality": g.get("municipality", ""),
                    "county": g.get("county", ""),
                    "maps_url": g["maps_url"],
                })

        # Step 4: Company affiliations
        _divider(f"STEP 4 -- Company affiliations: {name}")
        console.print(f"  [dim]Searching allabolag.se for '{name}'...[/dim]")
        companies = search_allabolag(name)
        if companies:
            for c in companies[:5]:
                cname = c.get("name", "")
                orgnr = c.get("org_nr", "")
                status = c.get("status", "")
                _ok(f"{cname}" + (f"  [{orgnr}]" if orgnr else "")
                    + (f"  {status}" if status else ""))
                reporter.add("Correlate / Company Affiliations", {
                    "person": name,
                    "company": cname,
                    "org_nr": orgnr,
                    "status": status,
                    "source": "allabolag.se",
                })
        else:
            console.print("  [dim]  No company results.[/dim]")

        # Step 5: Social media
        _divider(f"STEP 5 -- Social media: {name}")
        usernames = _name_to_usernames(name)
        console.print(f"  [dim]Testing {len(usernames)} username variants: "
                      f"{', '.join(usernames[:4])}"
                      f"{'...' if len(usernames) > 4 else ''}[/dim]")

        all_social_hits = []
        seen_platforms: set = set()
        for uname in usernames[:5]:
            hits = _check_username(uname, label=uname)
            for h in hits:
                key = (h["platform"], h["url"])
                if key not in seen_platforms:
                    seen_platforms.add(key)
                    h["tried_username"] = uname
                    all_social_hits.append(h)
                    _hit(f"{h['platform']:20s} ({uname})", h["url"])
                    reporter.add("Correlate / Social Media", {
                        "person": name,
                        "platform": h["platform"],
                        "username": uname,
                        "url": h["url"],
                        "source": "username-check",
                    })

        if not all_social_hits:
            console.print("  [dim]  No social profiles found.[/dim]")

        # Step 6: News mentions
        _divider(f"STEP 6 -- News mentions: {name}")
        console.print(f"  [dim]Searching Swedish news for '{name}'...[/dim]")
        articles = search_google_news_se(name) + search_svt(name)
        seen_titles: set = set()
        count = 0
        for a in articles:
            title = a.get("title", "")
            if title and title not in seen_titles:
                seen_titles.add(title)
                source = a.get("source", "")
                date = a.get("date", "")
                console.print(f"    [bold]{safe(title)}[/bold]")
                console.print(f"    [dim]{safe(source)}  {date}[/dim]")
                if a.get("url"):
                    console.print(f"    [cyan]{a['url']}[/cyan]")
                reporter.add("Correlate / News", {
                    "person": name,
                    "title": title,
                    "source": source,
                    "date": date,
                    "url": a.get("url", ""),
                })
                count += 1
                if count >= 5:
                    break
        if count == 0:
            console.print("  [dim]  No news articles found.[/dim]")

    console.print()
    _divider("SUMMARY")
    console.print(f"  Persons identified:  [bold]{len(persons)}[/bold]")
    console.print(f"  Source number:       [bold]{digits}[/bold] ({carrier})")
    console.print()


# --- email correlation --------------------------------------------------------

def correlate_email(email: str) -> None:
    print_section("EMAIL CORRELATION PROFILE")

    if not validate_email_format(email):
        console.print("  [red]Invalid email format.[/red]")
        return

    console.print(f"  [dim]Input:[/dim] [bold]{email}[/bold]")

    # Step 1: Email intelligence
    _divider("STEP 1 -- Email intelligence")
    console.print("  [dim]Running MX, Gravatar, HIBP checks...[/dim]")
    base = email_get(email)
    username = base.get("username", "")
    domain = base.get("domain", "")

    _info("Username part", username)
    _info("Domain", domain)

    mx = base.get("mx", [])
    if mx:
        _info("Mail server", mx[0])

    gravatar = base.get("gravatar", "")
    if gravatar:
        _ok(f"Gravatar found: {gravatar}")
    else:
        console.print("  [dim]  No Gravatar.[/dim]")

    reporter.add("Correlate / Email Intel", {
        "email": email,
        "username": username,
        "domain": domain,
        "mail_server": mx[0] if mx else "",
        "gravatar": gravatar,
    })

    breaches = base.get("breaches", [])
    if breaches:
        if "note" in breaches[0]:
            _warn(breaches[0]["note"])
        else:
            _warn(f"Found in {len(breaches)} data breach(es):")
            for b in breaches[:10]:
                console.print(f"    [red]  - {b.get('name','')}[/red]  "
                               f"[dim]{b.get('date','')} | {b.get('data_classes','')}[/dim]")
                reporter.add("Correlate / Breaches", {
                    "email": email,
                    "breach": b.get("name", ""),
                    "date": b.get("date", ""),
                    "data_classes": b.get("data_classes", ""),
                    "pwn_count": b.get("pwn_count", ""),
                    "_type": "breach",
                    "source": "haveibeenpwned.com",
                })
    else:
        _ok("Not found in any known breaches (HIBP)")

    # Step 2: Person search by username
    _divider("STEP 2 -- Person search by username")
    console.print(f"  [dim]Searching directories for '{username}'...[/dim]")
    person_results = (
        search_hitta(username) +
        search_eniro(username) +
        search_merinfo(username)
    )
    found_names: list[str] = []
    seen_names: set = set()
    for r in person_results[:5]:
        name = r.get("name", "")
        if name and name not in seen_names:
            seen_names.add(name)
            found_names.append(name)
            addr = r.get("address", "")
            _ok(f"{name}" + (f"  |  {addr}" if addr else ""))
            reporter.add("Correlate / Person Search", {
                "email": email,
                "username_query": username,
                "name": name,
                "address": addr,
                "source": r.get("source", ""),
            })

    if not found_names:
        console.print("  [dim]  No person matches via username.[/dim]")

    # Step 3: Social media (username)
    _divider(f"STEP 3 -- Social media for username '{username}'")
    console.print(f"  [dim]Checking {len(PLATFORMS)} platforms...[/dim]")
    social_hits = _check_username(username, label=username)
    if social_hits:
        for h in social_hits:
            _hit(f"{h['platform']:20s}", h["url"])
            reporter.add("Correlate / Social Media", {
                "email": email,
                "platform": h["platform"],
                "username": username,
                "url": h["url"],
                "source": "username-check",
            })
    else:
        console.print("  [dim]  Not found on checked platforms.[/dim]")

    # Step 3b: Name-derived username variants
    extra_usernames: list[str] = []
    for name in found_names[:2]:
        extra_usernames += _name_to_usernames(name)
    extra_usernames = [u for u in extra_usernames if u != username][:6]

    if extra_usernames:
        _divider("STEP 3b -- Social media (name-derived usernames)")
        console.print(f"  [dim]Testing variants: {', '.join(extra_usernames)}[/dim]")
        for uname in extra_usernames[:4]:
            hits = _check_username(uname, label=uname)
            for h in hits:
                _hit(f"{h['platform']:20s} ({uname})", h["url"])
                reporter.add("Correlate / Social Media", {
                    "email": email,
                    "platform": h["platform"],
                    "username": uname,
                    "url": h["url"],
                    "source": "username-check (name variant)",
                })

    # Step 4: Company affiliations
    if found_names:
        _divider("STEP 4 -- Company affiliations")
        for name in found_names[:2]:
            console.print(f"  [dim]allabolag.se: '{name}'...[/dim]")
            companies = search_allabolag(name)
            for c in companies[:5]:
                cname = c.get("name", "")
                orgnr = c.get("org_nr", "")
                _ok(f"{cname}" + (f"  [{orgnr}]" if orgnr else ""))
                reporter.add("Correlate / Company Affiliations", {
                    "email": email,
                    "person": name,
                    "company": cname,
                    "org_nr": orgnr,
                    "source": "allabolag.se",
                })
            if not companies:
                console.print("  [dim]  No results.[/dim]")

    # Step 5: News mentions
    _divider("STEP 5 -- News mentions")
    search_terms = [email] + found_names[:2]
    seen_titles: set = set()
    count = 0
    for term in search_terms:
        console.print(f"  [dim]Searching news for '{term}'...[/dim]")
        articles = search_google_news_se(term) + search_svt(term)
        for a in articles:
            title = a.get("title", "")
            if title and title not in seen_titles:
                seen_titles.add(title)
                src = a.get("source", "")
                date = a.get("date", "")
                console.print(f"    [bold]{safe(title)}[/bold]")
                console.print(f"    [dim]{safe(src)}  {date}[/dim]")
                if a.get("url"):
                    console.print(f"    [cyan]{a['url']}[/cyan]")
                reporter.add("Correlate / News", {
                    "query": term,
                    "title": title,
                    "source": src,
                    "date": date,
                    "url": a.get("url", ""),
                })
                count += 1
                if count >= 6:
                    break
        if count >= 6:
            break
    if count == 0:
        console.print("  [dim]  No news articles found.[/dim]")

    console.print()
    _divider("SUMMARY")
    console.print(f"  Email:           [bold]{email}[/bold]")
    console.print(f"  Username:        [bold]{username}[/bold]")
    console.print(f"  Persons found:   [bold]{len(found_names)}[/bold]")
    console.print(f"  Social hits:     [bold]{len(social_hits)}[/bold]")
    breach_status = "yes" if breaches and "note" not in breaches[0] else "no/unknown"
    console.print(f"  Breach records:  [bold]{breach_status}[/bold]")
    console.print()


# --- auto-detect input type ---------------------------------------------------

def run(target: str) -> None:
    target = target.strip()
    if re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", target):
        correlate_email(target)
    elif re.match(r"^[\d\s\+\-\(\)]+$", target) and len(re.sub(r"\D", "", target)) >= 7:
        correlate_phone(target)
    else:
        console.print(f"  [red]Cannot detect type for '{target}'. "
                      f"Provide a valid email or Swedish phone number.[/red]")
