"""
Domain & IP Lookup Module
Sources: IIS.se WHOIS (.se domains), generic WHOIS, DNS records
"""
import socket
import re
import dns.resolver
import whois
from .utils import fetch, soup, console, print_section, print_result


def lookup_whois(domain: str) -> dict:
    """Standard WHOIS lookup."""
    result = {}
    try:
        w = whois.whois(domain)
        if w:
            result["registrar"] = str(w.registrar or "")
            result["creation_date"] = str(w.creation_date or "")
            result["expiration_date"] = str(w.expiration_date or "")
            result["updated_date"] = str(w.updated_date or "")
            result["name_servers"] = ", ".join(
                [str(ns) for ns in (w.name_servers or [])]
            )
            result["status"] = str(w.status or "")
            result["registrant"] = str(w.org or w.registrant or "")
    except Exception as e:
        result["error"] = str(e)
    return result


def lookup_dns(domain: str) -> dict:
    """Retrieve common DNS record types."""
    records = {}
    record_types = ["A", "AAAA", "MX", "TXT", "NS", "CNAME", "SOA"]

    resolver = dns.resolver.Resolver()
    resolver.timeout = 5
    resolver.lifetime = 5

    for rtype in record_types:
        try:
            answers = resolver.resolve(domain, rtype)
            records[rtype] = [str(r) for r in answers]
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN,
                dns.resolver.NoNameservers, dns.exception.Timeout):
            pass
        except Exception:
            pass
    return records


def reverse_dns(ip: str) -> str:
    """Reverse DNS lookup."""
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ""


def lookup_iis_se(domain: str) -> dict:
    """
    Lookup .se / .nu domain in IIS.se RDAP API.
    https://rdap.iis.se/domain/<domain>
    """
    result = {}
    if not (domain.endswith(".se") or domain.endswith(".nu")):
        return result

    url = f"https://rdap.iis.se/domain/{domain}"
    resp = fetch(url)
    if not resp:
        return result

    try:
        data = resp.json()
        result["handle"] = data.get("handle", "")
        result["status"] = ", ".join(data.get("status", []))
        result["registration"] = ""
        result["expiry"] = ""
        for ev in data.get("events", []):
            if ev.get("eventAction") == "registration":
                result["registration"] = ev.get("eventDate", "")
            if ev.get("eventAction") == "expiration":
                result["expiry"] = ev.get("eventDate", "")

        # Name servers
        ns_list = [ns.get("ldhName", "") for ns in data.get("nameservers", [])]
        result["nameservers"] = ", ".join(ns_list)

        # Registrant
        for entity in data.get("entities", []):
            roles = entity.get("roles", [])
            if "registrant" in roles:
                vcards = entity.get("vcardArray", [])
                if vcards and len(vcards) > 1:
                    for vcard_item in vcards[1]:
                        if vcard_item[0] == "fn":
                            result["registrant"] = vcard_item[3]
                            break
    except Exception as e:
        result["parse_error"] = str(e)

    return result


def ip_geolocation(ip: str) -> dict:
    """Free IP geolocation via ip-api.com."""
    result = {}
    resp = fetch(f"https://ip-api.com/json/{ip}?fields=country,regionName,city,isp,org,as,query")
    if resp:
        try:
            data = resp.json()
            if data.get("status") == "success":
                result["ip"] = data.get("query", ip)
                result["country"] = data.get("country", "")
                result["region"] = data.get("regionName", "")
                result["city"] = data.get("city", "")
                result["isp"] = data.get("isp", "")
                result["org"] = data.get("org", "")
                result["asn"] = data.get("as", "")
        except Exception:
            pass
    return result


def lookup_crt_sh(domain: str) -> list[str]:
    """
    Find subdomains via Certificate Transparency logs (crt.sh).
    Returns sorted list of unique subdomains.
    """
    import time
    subdomains = set()
    url = f"https://crt.sh/?q=%.{domain}&output=json"
    resp = fetch(url)
    if not resp:
        return []
    try:
        for cert in resp.json():
            for name in cert.get("name_value", "").split("\n"):
                name = name.strip().lstrip("*.")
                if name and name.endswith(domain) and name != domain:
                    subdomains.add(name.lower())
    except Exception:
        pass
    return sorted(subdomains)


def run(domain: str) -> None:
    print_section("DOMAIN / IP LOOKUP")
    console.print(f"  [dim]Target:[/dim] [bold]{domain}[/bold]\n")

    # Detect if it's an IP
    is_ip = bool(re.match(r"^\d{1,3}(\.\d{1,3}){3}$", domain))

    if is_ip:
        # IP info
        console.print("  [dim]Fetching geolocation...[/dim]")
        geo = ip_geolocation(domain)
        if geo:
            console.print("  [bold green]> IP Geolocation[/bold green]")
            for k, v in geo.items():
                if v:
                    print_result(f"    {k.capitalize()}", v)
            console.print()

        rdns = reverse_dns(domain)
        if rdns:
            print_result("  Reverse DNS", rdns)
        return

    # Domain lookups
    console.print("  [dim]Running WHOIS...[/dim]")
    w = lookup_whois(domain)
    if w and "error" not in w:
        console.print("  [bold green]> WHOIS[/bold green]")
        for k, v in w.items():
            if v and v != "None":
                print_result(f"    {k.replace('_', ' ').capitalize()}", v)
        console.print()

    # IIS.se RDAP for .se/.nu
    if domain.endswith(".se") or domain.endswith(".nu"):
        console.print("  [dim]Querying IIS.se RDAP...[/dim]")
        iis = lookup_iis_se(domain)
        if iis:
            console.print("  [bold green]> IIS.se RDAP[/bold green]")
            for k, v in iis.items():
                if v:
                    print_result(f"    {k.replace('_', ' ').capitalize()}", v)
            console.print()

    console.print("  [dim]Resolving DNS records...[/dim]")
    dns_records = lookup_dns(domain)
    if dns_records:
        console.print("  [bold green]> DNS Records[/bold green]")
        for rtype, values in dns_records.items():
            for v in values:
                print_result(f"    {rtype}", v)

        # Geolocate A records
        a_records = dns_records.get("A", [])
        for ip in a_records[:2]:
            console.print(f"\n  [dim]Geolocating {ip}...[/dim]")
            geo = ip_geolocation(ip)
            if geo:
                console.print(f"  [bold green]> IP Info ({ip})[/bold green]")
                for k, v in geo.items():
                    if v and k != "ip":
                        print_result(f"    {k.capitalize()}", v)
        console.print()
    else:
        console.print("  [yellow]No DNS records found.[/yellow]")

    # crt.sh subdomain enumeration
    if not is_ip:
        console.print("  [dim]Querying crt.sh certificate transparency...[/dim]")
        subdomains = lookup_crt_sh(domain)
        if subdomains:
            console.print(f"  [bold green]> Subdomains via crt.sh ({len(subdomains)} found)[/bold green]")
            for sub in subdomains[:50]:
                print_result("    subdomain", sub)
            if len(subdomains) > 50:
                console.print(f"  [dim]  ... and {len(subdomains) - 50} more[/dim]")
        else:
            console.print("  [dim]  No subdomains found in CT logs.[/dim]")
        console.print()
