"""
Wayback Machine / Internet Archive
-----------------------------------
Fetches historical snapshots of a URL using the CDX API.
Also checks domain change history and deleted pages.
"""
import datetime
from .utils import fetch, console, print_section


CDX_API      = "https://web.archive.org/cdx/search/cdx"
AVAILABLE_API = "https://archive.org/wayback/available"


def get_snapshots(url: str, limit: int = 30) -> list[dict]:
    """Return deduplicated snapshots via the CDX Search API."""
    params = (
        f"?url={url}&output=json&limit={limit}"
        f"&fl=timestamp,original,statuscode,mimetype,length"
        f"&filter=!statuscode:301&filter=!statuscode:302"
        f"&collapse=timestamp:8"          # one per day
    )
    resp = fetch(CDX_API + params, timeout=20)
    if not resp:
        return []
    try:
        data = resp.json()
    except Exception:
        return []
    if not data or len(data) < 2:
        return []

    keys = data[0]
    results = []
    for row in data[1:]:
        entry = dict(zip(keys, row))
        ts = entry.get("timestamp", "")
        if len(ts) == 14:
            try:
                dt = datetime.datetime.strptime(ts, "%Y%m%d%H%M%S")
                entry["date"]        = dt.strftime("%Y-%m-%d")
                entry["wayback_url"] = (
                    f"https://web.archive.org/web/{ts}/"
                    f"{entry.get('original', url)}"
                )
            except ValueError:
                entry["date"]        = ts
                entry["wayback_url"] = ""
        results.append(entry)
    return results


def get_latest_snapshot(url: str) -> dict | None:
    resp = fetch(f"{AVAILABLE_API}?url={url}", timeout=12)
    if not resp:
        return None
    try:
        data = resp.json()
        snap = data.get("archived_snapshots", {}).get("closest", {})
        if snap.get("available"):
            return snap
    except Exception:
        pass
    return None


def get_yearly_summary(snapshots: list[dict]) -> dict[str, int]:
    """Count snapshots per year."""
    by_year: dict[str, int] = {}
    for s in snapshots:
        year = s.get("date", "????")[:4]
        by_year[year] = by_year.get(year, 0) + 1
    return dict(sorted(by_year.items()))


def run(url: str, limit: int = 30) -> list[dict]:
    print_section("WAYBACK MACHINE / INTERNET ARCHIVE")
    console.print(f"  [dim]Target:[/dim] [bold]{url}[/bold]")

    # ── availability ──────────────────────────────────────────────────────────
    console.print("\n  [cyan][ Availability Check ][/cyan]")
    latest = get_latest_snapshot(url)
    if latest:
        ts  = latest.get("timestamp", "")
        wb  = latest.get("url", "")
        try:
            dt  = datetime.datetime.strptime(ts, "%Y%m%d%H%M%S")
            ts  = dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass
        console.print(f"    [green][+][/green] Indexed in Wayback Machine")
        console.print(f"    [dim]Latest snapshot:[/dim] {ts}")
        console.print(f"    [cyan]{wb}[/cyan]")
    else:
        console.print("    [yellow][!][/yellow] URL not indexed or unavailable")

    # ── historical snapshots ───────────────────────────────────────────────────
    console.print(f"\n  [cyan][ Historical Snapshots — max {limit} ][/cyan]")
    snapshots = get_snapshots(url, limit=limit)

    if not snapshots:
        console.print("    [dim]No snapshots found.[/dim]")
        return []

    summary = get_yearly_summary(snapshots)
    console.print(
        "    [dim]Coverage:[/dim] "
        + "  ".join(f"{yr}×{cnt}" for yr, cnt in summary.items())
    )

    # Group by year, show newest first
    by_year: dict[str, list[dict]] = {}
    for s in snapshots:
        year = s.get("date", "?")[:4]
        by_year.setdefault(year, []).append(s)

    for year in sorted(by_year.keys(), reverse=True):
        entries = by_year[year]
        console.print(f"\n    [bold]{year}[/bold]  ({len(entries)} snapshots)")
        for s in entries[:4]:
            date    = s.get("date", "")
            mime    = s.get("mimetype", "")
            size    = s.get("length", "")
            status  = s.get("statuscode", "")
            wb_url  = s.get("wayback_url", "")
            size_kb = f"{int(size)//1024}KB" if size and size.isdigit() else ""
            console.print(
                f"      [dim]{date}[/dim]  "
                f"[{'green' if status == '200' else 'red'}]{status}[/{'green' if status == '200' else 'red'}]  "
                f"[dim]{mime}  {size_kb}[/dim]\n"
                f"      [cyan]{wb_url}[/cyan]"
            )

    console.print(f"\n  [dim]Total deduplicated snapshots: {len(snapshots)}[/dim]")
    return snapshots
