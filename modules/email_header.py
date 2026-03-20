"""
Email Header Analyzer — ported/inspired by ClatScope Mini (Clats97)
Parses raw email headers, extracts IPs from Received lines,
and geolocates originating servers.
"""
from __future__ import annotations

import re
from email.parser import Parser

import requests

from .utils import console, print_section, print_result, get_headers


_IP_RE = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")

# IPs that are internal / loopback — skip geolocation
_PRIVATE_PREFIXES = ("10.", "172.16.", "172.17.", "172.18.", "172.19.",
                     "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
                     "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
                     "172.30.", "172.31.", "192.168.", "127.", "0.", "::1")


def _is_private(ip: str) -> bool:
    return any(ip.startswith(p) for p in _PRIVATE_PREFIXES)


def _geolocate(ip: str) -> dict:
    try:
        r = requests.get(
            f"https://ip-api.com/json/{ip}?fields=status,country,regionName,city,isp,org,as",
            timeout=8,
            headers=get_headers(),
        )
        data = r.json()
        if data.get("status") == "success":
            return {
                "country": data.get("country", ""),
                "region":  data.get("regionName", ""),
                "city":    data.get("city", ""),
                "isp":     data.get("isp", ""),
                "org":     data.get("org", ""),
                "asn":     data.get("as", ""),
            }
    except Exception:
        pass
    return {}


def analyze_email_header(raw_headers: str) -> dict:
    """
    Parse raw email headers and return structured intelligence.
    Accepts the full raw text (paste from 'Show original' in Gmail etc.)
    """
    parser = Parser()
    msg = parser.parsestr(raw_headers)

    result: dict = {
        "from":    msg.get("From", ""),
        "to":      msg.get("To", ""),
        "subject": msg.get("Subject", ""),
        "date":    msg.get("Date", ""),
        "message_id": msg.get("Message-ID", ""),
        "reply_to":   msg.get("Reply-To", ""),
        "x_mailer":   msg.get("X-Mailer", "") or msg.get("User-Agent", ""),
        "spf":    msg.get("Received-SPF", ""),
        "dkim":   msg.get("DKIM-Signature", ""),
        "dmarc":  msg.get("Authentication-Results", ""),
    }

    # Extract IPs from Received: chain
    received_lines = msg.get_all("Received", [])
    seen_ips: list[str] = []
    for line in received_lines:
        for ip in _IP_RE.findall(line):
            if ip not in seen_ips:
                seen_ips.append(ip)

    result["received_ips"] = seen_ips

    # Geolocate public IPs
    geo_results = []
    for ip in seen_ips:
        if _is_private(ip):
            geo_results.append({"ip": ip, "note": "private/internal"})
        else:
            geo = _geolocate(ip)
            geo_results.append({"ip": ip, **geo})

    result["ip_geo"] = geo_results
    return result


def run(raw_headers: str) -> None:
    print_section("EMAIL HEADER ANALYSIS")

    result = analyze_email_header(raw_headers)

    for field in ("from", "to", "subject", "date", "message_id", "reply_to", "x_mailer"):
        if result.get(field):
            print_result(field.replace("_", " ").title(), result[field])

    console.print()
    console.print("  [bold cyan]Authentication:[/bold cyan]")
    for field in ("spf", "dkim", "dmarc"):
        val = result.get(field, "")
        if val:
            colour = "green" if "pass" in val.lower() else "yellow"
            console.print(f"    [{colour}]{field.upper()}:[/{colour}] {val[:120]}")

    console.print()
    ips = result.get("received_ips", [])
    if ips:
        console.print(f"  [bold cyan]IPs in Received chain ({len(ips)}):[/bold cyan]")
        for geo in result.get("ip_geo", []):
            ip = geo["ip"]
            if geo.get("note"):
                console.print(f"    [dim]{ip}  ({geo['note']})[/dim]")
            else:
                loc = ", ".join(filter(None, [geo.get("city"), geo.get("country")]))
                isp = geo.get("isp", "")
                console.print(f"    [bold]{ip}[/bold]  {loc}  [dim]{isp}[/dim]")
    else:
        console.print("  [dim]No IPs found in Received headers.[/dim]")
