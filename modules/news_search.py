"""
Swedish News Search Module
Sources: Google News (se), Aftonbladet, Expressen, SVT, DN, SvD
"""
import urllib.parse
from .utils import fetch, soup, console, print_section, print_result, safe


def search_google_news_se(query: str) -> list[dict]:
    """Search Google News filtered to Swedish sources."""
    results = []
    q = urllib.parse.quote_plus(f"{query} site:aftonbladet.se OR site:dn.se OR "
                                f"site:svt.se OR site:expressen.se OR site:svd.se")
    url = f"https://news.google.com/rss/search?q={q}&hl=sv&gl=SE&ceid=SE:sv"

    resp = fetch(url)
    if not resp:
        return results

    bs = soup(resp)
    items = bs.select("item")[:10]

    for item in items:
        entry = {}
        title = item.find("title")
        link = item.find("link")
        pub_date = item.find("pubdate")
        source = item.find("source")

        if title:
            entry["title"] = title.get_text(strip=True)
        if link:
            # Google News wraps URLs
            entry["url"] = link.next_sibling or link.get_text(strip=True)
        if pub_date:
            entry["date"] = pub_date.get_text(strip=True)
        if source:
            entry["source"] = source.get_text(strip=True)

        if entry.get("title"):
            results.append(entry)

    return results


def search_svt(query: str) -> list[dict]:
    """Search SVT Nyheter."""
    results = []
    q = urllib.parse.quote_plus(query)
    url = f"https://www.svt.se/sok/?q={q}"

    resp = fetch(url)
    if not resp:
        return results

    bs = soup(resp)
    articles = bs.select("article, .search-result, [class*='article']")[:10]

    for art in articles:
        entry = {}
        title_el = art.select_one("h2, h3, [class*='title']")
        link_el = art.select_one("a[href]")
        date_el = art.select_one("time, [class*='date'], [class*='time']")
        desc_el = art.select_one("p, [class*='summary'], [class*='preamble']")

        if title_el:
            entry["title"] = title_el.get_text(strip=True)
        if link_el:
            href = link_el.get("href", "")
            entry["url"] = href if href.startswith("http") else f"https://www.svt.se{href}"
        if date_el:
            entry["date"] = date_el.get("datetime", "") or date_el.get_text(strip=True)
        if desc_el:
            entry["description"] = desc_el.get_text(strip=True)[:200]
        entry["source"] = "SVT Nyheter"

        if entry.get("title"):
            results.append(entry)

    return results


def search_dn(query: str) -> list[dict]:
    """Search Dagens Nyheter."""
    results = []
    q = urllib.parse.quote_plus(query)
    url = f"https://www.dn.se/sok/?q={q}"

    resp = fetch(url)
    if not resp:
        return results

    bs = soup(resp)
    articles = bs.select("article, [class*='teaser'], [class*='article-item']")[:10]

    for art in articles:
        entry = {}
        title_el = art.select_one("h2, h3, [class*='title'], [class*='headline']")
        link_el = art.select_one("a[href]")
        date_el = art.select_one("time, [class*='date']")

        if title_el:
            entry["title"] = title_el.get_text(strip=True)
        if link_el:
            href = link_el.get("href", "")
            entry["url"] = href if href.startswith("http") else f"https://www.dn.se{href}"
        if date_el:
            entry["date"] = date_el.get("datetime", "") or date_el.get_text(strip=True)
        entry["source"] = "Dagens Nyheter"

        if entry.get("title"):
            results.append(entry)

    return results


def run(query: str) -> None:
    print_section("SWEDISH NEWS SEARCH")
    console.print(f"  [dim]Query:[/dim] [bold]{query}[/bold]\n")

    all_results = []

    console.print("  [dim]Searching Google News (Swedish)...[/dim]")
    all_results += search_google_news_se(query)

    console.print("  [dim]Searching SVT Nyheter...[/dim]")
    all_results += search_svt(query)

    console.print("  [dim]Searching Dagens Nyheter...[/dim]")
    all_results += search_dn(query)

    if not all_results:
        console.print("  [yellow]No news articles found.[/yellow]")
        return

    console.print(f"\n  [bold green]> {len(all_results)} article(s) found:[/bold green]\n")
    seen_titles = set()
    for r in all_results:
        title = r.get("title", "")
        if title in seen_titles or not title:
            continue
        seen_titles.add(title)

        source_label = r.get("source", "")
        date_label = r.get("date", "")
        console.print(f"  [bold]{safe(title)}[/bold]")
        meta = " | ".join(filter(None, [source_label, date_label]))
        if meta:
            console.print(f"  [dim]{safe(meta)}[/dim]")
        if r.get("url"):
            console.print(f"  [cyan]{r['url']}[/cyan]")
        if r.get("description"):
            console.print(f"  {safe(r['description'][:180])}...")
        console.print()
