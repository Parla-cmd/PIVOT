"""
Social Media / Username OSINT Module
Checks username existence across Swedish and global platforms.
Uses HEAD/GET requests -- does NOT scrape private content.
"""
import requests
import concurrent.futures
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from .utils import console, print_section, get_headers


# Platforms with their profile URL templates
# Format: (name, url_template, expected_status, not_found_indicator)
PLATFORMS = [
    # Swedish platforms
    ("Flashback",     "https://www.flashback.org/member/{u}",    200, "Ingen användare"),
    ("Bilddagboken",  "https://www.bilddagboken.se/{u}",          200, "finns inte"),
    ("Familjeliv",    "https://www.familjeliv.se/profil/{u}",     200, "Hittades inte"),
    # Global
    ("GitHub",        "https://github.com/{u}",                   200, "Not Found"),
    ("Twitter/X",     "https://twitter.com/{u}",                  200, "This account"),
    ("Instagram",     "https://www.instagram.com/{u}/",           200, "Sorry, this page"),
    ("TikTok",        "https://www.tiktok.com/@{u}",              200, "Couldn't find"),
    ("Reddit",        "https://www.reddit.com/user/{u}",          200, "page not found"),
    ("LinkedIn",      "https://www.linkedin.com/in/{u}",          200, "This page"),
    ("Pinterest",     "https://www.pinterest.com/{u}/",           200, "hmm"),
    ("Tumblr",        "https://{u}.tumblr.com",                   200, "There's nothing"),
    ("Twitch",        "https://www.twitch.tv/{u}",                200, "Sorry"),
    ("YouTube",       "https://www.youtube.com/@{u}",             200, "This page"),
    ("Steam",         "https://steamcommunity.com/id/{u}",        200, "The specified profile"),
    ("SoundCloud",    "https://soundcloud.com/{u}",               200, "We can't find"),
    ("Spotify",       "https://open.spotify.com/user/{u}",        200, "Page not found"),
    ("Vimeo",         "https://vimeo.com/{u}",                    200, "Sorry"),
    ("Medium",        "https://medium.com/@{u}",                  200, "Page not found"),
    ("Keybase",       "https://keybase.io/{u}",                   200, "Not a Keybase user"),
    ("GitLab",        "https://gitlab.com/{u}",                   200, "404"),
    ("Mastodon",      "https://mastodon.social/@{u}",             200, "The page you"),
    ("HackerNews",    "https://news.ycombinator.com/user?id={u}", 200, "No such user"),
    ("DockerHub",     "https://hub.docker.com/u/{u}",             200, "Page Not Found"),
]


def check_platform(username: str, platform_info: tuple) -> dict:
    name, url_template, expected_status, not_found_text = platform_info
    url = url_template.format(u=username)

    try:
        resp = requests.get(
            url,
            headers=get_headers(),
            timeout=8,
            allow_redirects=True,
        )
        status = resp.status_code
        body = resp.text

        if status == 404:
            return {"platform": name, "url": url, "found": False}

        if status == expected_status:
            if not_found_text and not_found_text.lower() in body.lower():
                return {"platform": name, "url": url, "found": False}
            return {"platform": name, "url": url, "found": True}

        return {"platform": name, "url": url, "found": False, "status": status}

    except requests.Timeout:
        return {"platform": name, "url": url, "found": None, "note": "timeout"}
    except Exception as e:
        return {"platform": name, "url": url, "found": None, "note": str(e)[:60]}


def check_username_with_progress(username: str, threads: int = 10,
                                  label: str = "") -> tuple[list, list, list]:
    """
    Check all platforms with a live progress bar.
    Returns (found, not_found, errors).
    """
    total = len(PLATFORMS)
    found, not_found, errors = [], [], []

    with Progress(
        SpinnerColumn("line"),
        TextColumn(f"  [bold cyan]{label or username}[/bold cyan]"),
        BarColumn(bar_width=28),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("[dim]{task.completed}/{task.total}[/dim]"),
        TextColumn("[bold green]{task.fields[found]} found[/bold green]"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("checking", total=total, found=0)

        with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {
                executor.submit(check_platform, username, p): p[0]
                for p in PLATFORMS
            }
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result["found"] is True:
                    found.append(result)
                elif result["found"] is False:
                    not_found.append(result)
                else:
                    errors.append(result)
                progress.update(task, advance=1, found=len(found))

    return found, not_found, errors


def run(username: str, threads: int = 10) -> None:
    print_section("USERNAME / SOCIAL MEDIA SEARCH")
    console.print(f"  [dim]Username:[/dim] [bold]{username}[/bold]  "
                  f"[dim]Checking {len(PLATFORMS)} platforms...[/dim]\n")

    found, not_found, errors = check_username_with_progress(username, threads)

    found.sort(key=lambda x: x["platform"])
    errors.sort(key=lambda x: x["platform"])

    console.print()
    if found:
        console.print(f"  [bold green]> Found on {len(found)} platform(s):[/bold green]")
        for r in found:
            console.print(f"  [green]  [+] {r['platform']:20s}[/green] {r['url']}")
    else:
        console.print("  [yellow]Not found on any checked platforms.[/yellow]")

    if errors:
        console.print(f"\n  [dim]Could not check {len(errors)} platform(s):[/dim]")
        for r in errors:
            console.print(f"  [dim]  ? {r['platform']:20s} -- {r.get('note', '')}[/dim]")

    console.print(f"\n  [dim]Summary: {len(found)} found, "
                  f"{len(not_found)} not found, {len(errors)} errors[/dim]")
