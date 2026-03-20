"""
API Helpers — adapts PIVOT CLI modules for use in the REST API.

Each helper function returns a dict (or list of dicts) of results,
capturing the data that the CLI modules normally print to stdout.
"""

from __future__ import annotations
import io
import sys
from typing import Any


def _silence() -> tuple[io.StringIO, io.StringIO]:
    """Redirect stdout/stderr to suppress rich console output."""
    buf_out = io.StringIO()
    buf_err = io.StringIO()
    return buf_out, buf_err


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------

def run_person(name: str, city: str = "", personnummer: str = "") -> dict[str, Any]:
    from modules.person_lookup import search_hitta, search_eniro, search_merinfo
    results = (
        search_hitta(name, city)
        + search_eniro(name, city)
        + search_merinfo(name)
    )
    return {"results": results, "count": len(results)}


def run_company(name: str = "", org_nr: str = "") -> dict[str, Any]:
    from modules.company_lookup import search_allabolag, search_hitta_foretag
    query = name or org_nr
    results = search_allabolag(query) + search_hitta_foretag(query)
    return {"results": results, "count": len(results)}


def run_phone(phone: str) -> dict[str, Any]:
    from modules.phone_lookup import get_results
    results = get_results(phone)
    return {"results": results, "count": len(results)}


def run_domain(domain: str) -> dict[str, Any]:
    from modules.domain_lookup import (
        lookup_whois, lookup_dns, lookup_iis_se, ip_geolocation, lookup_crt_sh
    )
    data: dict[str, Any] = {"domain": domain}

    whois_data = lookup_whois(domain)
    if whois_data and "error" not in whois_data:
        data["whois"] = whois_data

    data["dns"] = lookup_dns(domain)
    data["subdomains"] = lookup_crt_sh(domain)

    if domain.endswith(".se") or domain.endswith(".nu"):
        iis = lookup_iis_se(domain)
        if iis:
            data["iis_rdap"] = iis

    return data


def run_email(email: str) -> dict[str, Any]:
    from modules.email_lookup import get_results
    return get_results(email)


def run_social(username: str, threads: int = 10) -> dict[str, Any]:
    import concurrent.futures
    from modules.social_media import check_platform, PLATFORMS

    found = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as ex:
        futures = {ex.submit(check_platform, username, p): p for p in PLATFORMS}
        for future in concurrent.futures.as_completed(futures):
            r = future.result()
            if r.get("found"):
                found.append(r)
    return {"results": found, "count": len(found)}


def run_news(query: str) -> dict[str, Any]:
    from modules.news_search import search_google_news_se, search_svt, search_dn
    articles = search_google_news_se(query) + search_svt(query) + search_dn(query)
    seen: set[str] = set()
    unique = []
    for a in articles:
        t = a.get("title", "")
        if t and t not in seen:
            seen.add(t)
            unique.append(a)
    return {"results": unique, "count": len(unique)}


def run_geo(address: str = "", lat: str = "", lon: str = "") -> dict[str, Any]:
    from modules.geolocation import geocode_address, reverse_geocode
    if address:
        results = geocode_address(address)[:5]
        return {"results": results, "count": len(results)}
    elif lat and lon:
        result = reverse_geocode(lat, lon)
        return {"result": result}
    return {"error": "Provide address or lat+lon"}


def run_github(username: str = "", email: str = "", name: str = "") -> dict[str, Any]:
    # github_lookup.run() prints to console; we capture structured data via direct calls
    from modules.github_lookup import run as _run
    import json, contextlib

    captured: list[str] = []

    class _Capture:
        def print(self, *args, **kwargs):
            pass
        def log(self, *args, **kwargs):
            pass

    # run() prints rich output — just call it, results are printed
    # For API we return a simple status; advanced extraction would need refactoring
    _run(username=username, email=email, name=name)
    return {"status": "completed", "username": username, "email": email, "name": name}


def run_wayback(url: str, limit: int = 30) -> dict[str, Any]:
    from modules.wayback import run
    snapshots = run(url=url, limit=limit)
    return {"results": snapshots or [], "count": len(snapshots or [])}


def run_folkbok(name: str, city: str = "", personnummer: str = "") -> dict[str, Any]:
    from modules.folkbokforing import run_person
    run_person(name=name, city=city, personnummer=personnummer)
    return {"status": "completed", "name": name}


def run_vehicle(plate: str) -> dict[str, Any]:
    from modules.folkbokforing import run_vehicle
    run_vehicle(plate=plate)
    return {"status": "completed", "plate": plate}


def run_harvest(domain: str, deep: bool = False) -> dict[str, Any]:
    from modules.email_harvest import run
    run(domain=domain, deep=deep)
    return {"status": "completed", "domain": domain}


def run_paste(target: str) -> dict[str, Any]:
    from modules.paste_search import run
    run(target=target)
    return {"status": "completed", "target": target}


def run_correlate(target: str) -> dict[str, Any]:
    from modules.correlate import run
    run(target=target)
    return {"status": "completed", "target": target}
