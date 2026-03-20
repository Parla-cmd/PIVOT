#!/usr/bin/env python3
"""
Sweden OSINT Tool
-----------------
An educational open-source intelligence aggregator for Swedish targets.
Uses only publicly accessible sources and APIs.

Usage:
  python main.py person    --name "Anna Svensson" [--city Stockholm]
  python main.py company   --name "Volvo" [--orgnr 556012-5790]
  python main.py phone     --phone "070-123 45 67"
  python main.py domain    --domain "example.se"
  python main.py email     --email "user@example.se"
  python main.py social    --username "annasvens"
  python main.py news      --query "Anna Svensson Stockholm"
  python main.py geo       --address "Storgatan 1, Stockholm"
  python main.py github    --username "johndoe" [--email x] [--name x]
  python main.py correlate --target "070-123 45 67"
  python main.py all       --name "Anna Svensson" --email "a@b.se" ...

Add --output report.html or --output report.json to any command to save results.
"""

import argparse
import sys
from rich.panel import Panel
from modules.config import load as _load_config
from modules.utils import print_banner, console
from modules import reporter as _reporter

_load_config()  # load .env before anything else

DISCLAIMER = """[bold yellow]DISCLAIMER[/bold yellow]
This tool is for [bold]educational and authorized research purposes only[/bold].
Only query information about yourself or with explicit permission.
Respect Swedish GDPR/Dataskyddslagen and GDPR regulations.
Unauthorized use may violate Swedish law (Brottsbalken, PUL/GDPR).
"""


def confirm_usage() -> bool:
    console.print(Panel(DISCLAIMER, border_style="yellow", padding=(1, 2)))
    answer = console.input(
        "[bold yellow]Do you confirm this is for lawful, authorized use? (yes/no): [/bold yellow]"
    ).strip().lower()
    return answer in ("yes", "y", "ja")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sweden OSINT Tool -- Educational Use Only",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--no-disclaimer", action="store_true",
        help="Skip the disclaimer prompt"
    )
    parser.add_argument(
        "--output", metavar="FILE",
        help="Save results to file. Use .json or .html extension. "
             "Example: --output report.html"
    )

    subparsers = parser.add_subparsers(dest="module", required=True)

    # Person
    p_person = subparsers.add_parser("person", help="Search for a person")
    p_person.add_argument("--name", required=True)
    p_person.add_argument("--city", default="")
    p_person.add_argument("--pnr", default="", help="Personnummer")

    # Company
    p_company = subparsers.add_parser("company", help="Search for a company")
    p_company.add_argument("--name", default="")
    p_company.add_argument("--orgnr", default="")

    # Phone
    p_phone = subparsers.add_parser("phone", help="Reverse phone lookup")
    p_phone.add_argument("--phone", required=True)

    # Domain
    p_domain = subparsers.add_parser("domain", help="Domain/IP OSINT")
    p_domain.add_argument("--domain", required=True)

    # Email
    p_email = subparsers.add_parser("email", help="Email OSINT")
    p_email.add_argument("--email", required=True)

    # Social media
    p_social = subparsers.add_parser("social", help="Username search")
    p_social.add_argument("--username", required=True)
    p_social.add_argument("--threads", type=int, default=10)

    # News
    p_news = subparsers.add_parser("news", help="Swedish news search")
    p_news.add_argument("--query", required=True)

    # Geolocation
    p_geo = subparsers.add_parser("geo", help="Address / coordinate lookup")
    p_geo.add_argument("--address", default="")
    p_geo.add_argument("--lat", default="")
    p_geo.add_argument("--lon", default="")

    # GitHub
    p_github = subparsers.add_parser("github", help="GitHub OSINT")
    p_github.add_argument("--username", default="", help="GitHub username")
    p_github.add_argument("--email", default="", help="Search commits by email")
    p_github.add_argument("--name", default="", help="Search users/commits by name")

    # Email harvest
    p_harvest = subparsers.add_parser(
        "harvest", help="Find all email addresses for a domain"
    )
    p_harvest.add_argument("--domain", required=True, help="Target domain, e.g. volvo.com")
    p_harvest.add_argument("--deep", action="store_true",
                           help="Also crawl crt.sh subdomains (slower)")

    # Paste search
    p_paste = subparsers.add_parser(
        "paste", help="Search paste sites and data dumps for an email or phone"
    )
    p_paste.add_argument("--target", required=True,
                         help='Email or phone number, e.g. "user@domain.se" or "070-123 45 67"')

    # Correlate
    p_correlate = subparsers.add_parser(
        "correlate", help="Full profile from phone or email"
    )
    p_correlate.add_argument("--target", required=True)

    # All-in-one
    p_all = subparsers.add_parser("all", help="Run all applicable modules")
    p_all.add_argument("--name", default="")
    p_all.add_argument("--email", default="")
    p_all.add_argument("--phone", default="")
    p_all.add_argument("--domain", default="")
    p_all.add_argument("--username", default="")
    p_all.add_argument("--query", default="")
    p_all.add_argument("--address", default="")

    return parser


def _target_label(args) -> str:
    """Best human-readable label for the current target."""
    for attr in ("target", "name", "email", "phone", "domain", "username", "query"):
        val = getattr(args, attr, "")
        if val:
            return val
    return "unknown"


# ---- module wiring with report collection -----------------------------------

def run_module(args):
    mod = args.module

    if mod == "harvest":
        from modules.email_harvest import run
        run(domain=args.domain, deep=args.deep)

    elif mod == "paste":
        from modules.paste_search import run
        run(target=args.target)

    elif mod == "correlate":
        from modules.correlate import run
        run(target=args.target)

    elif mod == "person":
        from modules.person_lookup import search_hitta, search_eniro, search_merinfo, run
        run(name=args.name, city=args.city, personnummer=args.pnr)
        if _reporter.active():
            results = (search_hitta(args.name, args.city) +
                       search_eniro(args.name, args.city) +
                       search_merinfo(args.name))
            for r in results:
                _reporter.add("Person Lookup", r)

    elif mod == "company":
        if not args.name and not args.orgnr:
            console.print("[red]Provide --name or --orgnr.[/red]")
            sys.exit(1)
        from modules.company_lookup import search_allabolag, search_hitta_foretag, run
        run(query=args.name, org_nr=args.orgnr)
        if _reporter.active():
            results = (search_allabolag(args.name or args.orgnr) +
                       search_hitta_foretag(args.name or args.orgnr))
            for r in results:
                _reporter.add("Company Lookup", r)

    elif mod == "phone":
        from modules.phone_lookup import get_results, run
        run(phone=args.phone)
        if _reporter.active():
            for r in get_results(args.phone):
                _reporter.add("Phone Lookup", r)

    elif mod == "domain":
        from modules.domain_lookup import (
            lookup_whois, lookup_dns, lookup_iis_se, ip_geolocation,
            lookup_crt_sh, run
        )
        run(domain=args.domain)
        if _reporter.active():
            whois_data = lookup_whois(args.domain)
            if whois_data and "error" not in whois_data:
                _reporter.add("Domain / WHOIS", {**whois_data, "domain": args.domain})
            dns_data = lookup_dns(args.domain)
            for rtype, vals in dns_data.items():
                for v in vals:
                    _reporter.add("Domain / DNS", {"type": rtype, "value": v,
                                                    "domain": args.domain})
            for sub in lookup_crt_sh(args.domain):
                _reporter.add("Domain / Subdomains (crt.sh)",
                              {"subdomain": sub, "domain": args.domain})
            if args.domain.endswith(".se") or args.domain.endswith(".nu"):
                iis = lookup_iis_se(args.domain)
                if iis:
                    _reporter.add("Domain / IIS.se RDAP", {**iis, "domain": args.domain})

    elif mod == "email":
        from modules.email_lookup import get_results, run
        run(email=args.email)
        if _reporter.active():
            data = get_results(args.email)
            _reporter.add("Email / MX & Metadata", {
                "email": args.email,
                "domain": data.get("domain", ""),
                "mail_servers": ", ".join(data.get("mx", [])),
                "gravatar": data.get("gravatar", ""),
            })
            for b in data.get("breaches", []):
                if "note" not in b:
                    _reporter.add("Email / Breaches", {**b, "_type": "breach",
                                                        "email": args.email})

    elif mod == "social":
        from modules.social_media import run, check_platform, PLATFORMS
        import concurrent.futures
        run(username=args.username, threads=args.threads)
        if _reporter.active():
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
                futures = {ex.submit(check_platform, args.username, p): p
                           for p in PLATFORMS}
                for future in concurrent.futures.as_completed(futures):
                    r = future.result()
                    if r.get("found"):
                        _reporter.add("Social Media", {
                            "platform": r["platform"],
                            "url": r["url"],
                            "username": args.username,
                            "source": "username-check",
                        })

    elif mod == "news":
        from modules.news_search import search_google_news_se, search_svt, search_dn, run
        run(query=args.query)
        if _reporter.active():
            articles = (search_google_news_se(args.query) +
                        search_svt(args.query) +
                        search_dn(args.query))
            seen = set()
            for a in articles:
                t = a.get("title", "")
                if t and t not in seen:
                    seen.add(t)
                    _reporter.add("News", a)

    elif mod == "geo":
        if not args.address and not (args.lat and args.lon):
            console.print("[red]Provide --address or both --lat and --lon.[/red]")
            sys.exit(1)
        from modules.geolocation import geocode_address, reverse_geocode, run
        run(address=args.address, lat=args.lat, lon=args.lon)
        if _reporter.active():
            if args.address:
                for g in geocode_address(args.address)[:3]:
                    _reporter.add("Geolocation", g)
            elif args.lat and args.lon:
                result = reverse_geocode(args.lat, args.lon)
                if result:
                    _reporter.add("Geolocation", {
                        "display_name": result.get("display_name", ""),
                        **result.get("address", {}),
                    })

    elif mod == "github":
        if not any([args.username, args.email, args.name]):
            console.print("[red]Provide --username, --email, or --name.[/red]")
            sys.exit(1)
        from modules.github_lookup import run
        run(username=args.username, email=args.email, name=args.name)

    elif mod == "all":
        query = args.query or args.name

        if args.name:
            from modules.person_lookup import run as person_run
            person_run(name=args.name)
            from modules.company_lookup import run as company_run
            company_run(query=args.name)

        if args.email:
            from modules.email_lookup import run as email_run
            email_run(email=args.email)
            from modules.github_lookup import run as github_run
            github_run(email=args.email, name=args.name)

        if args.phone:
            from modules.phone_lookup import run as phone_run
            phone_run(phone=args.phone)

        if args.domain:
            from modules.domain_lookup import run as domain_run
            domain_run(domain=args.domain)

        if args.username:
            from modules.social_media import run as social_run
            social_run(username=args.username)
            from modules.github_lookup import run as github_run
            github_run(username=args.username)

        if query:
            from modules.news_search import run as news_run
            news_run(query=query)

        if args.address:
            from modules.geolocation import run as geo_run
            geo_run(address=args.address)


# ---- entry point ------------------------------------------------------------

def main():
    print_banner()

    parser = build_parser()
    args = parser.parse_args()

    if not getattr(args, "no_disclaimer", False):
        if not confirm_usage():
            console.print("[red]Aborted.[/red]")
            sys.exit(0)
        console.print()

    # Initialize report if --output requested
    if args.output:
        _reporter.init(target=_target_label(args))
        console.print(f"  [dim]Report output: {args.output}[/dim]\n")

    run_module(args)

    console.print("\n[dim]--- Scan complete ---[/dim]\n")

    # Save report
    if args.output:
        _reporter.save(args.output)
        console.print(f"  [bold green]Report saved:[/bold green] {args.output}\n")


if __name__ == "__main__":
    main()
