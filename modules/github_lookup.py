"""
GitHub OSINT Module
-------------------
Search GitHub for a username, email, or name.
Uses the public GitHub REST API v3.
Set GITHUB_TOKEN env var for higher rate limits (5000 req/hr vs 60/hr).

Searches:
  - User profile
  - Repositories owned
  - Commit history by email (exposes real email even if hidden)
  - Code containing the query (email/phone leaks in source code)
  - Issues/PRs authored
  - Gists
"""
import time
import requests
from .utils import console, print_section, print_result, safe
from . import reporter
from .config import get as cfg

GITHUB_API = "https://api.github.com"

_TOKEN = cfg("GITHUB_TOKEN")

_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "sweden-osint-educational-tool",
}
if _TOKEN:
    _HEADERS["Authorization"] = f"Bearer {_TOKEN}"


def _get(endpoint: str, params: dict | None = None) -> dict | list | None:
    url = f"{GITHUB_API}{endpoint}"
    try:
        resp = requests.get(url, headers=_HEADERS, params=params, timeout=12)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 403:
            remaining = resp.headers.get("X-RateLimit-Remaining", "?")
            if remaining == "0":
                reset = resp.headers.get("X-RateLimit-Reset", "")
                console.print(f"  [yellow]GitHub rate limit hit. "
                               f"Set GITHUB_TOKEN for higher limits.[/yellow]")
            return None
        if resp.status_code == 422:
            return None  # Unprocessable - query too short etc.
    except requests.RequestException as e:
        console.print(f"  [yellow]GitHub API error: {e}[/yellow]")
    return None


def _search(endpoint: str, q: str, per_page: int = 10,
            extra_params: dict | None = None) -> list[dict]:
    params = {"q": q, "per_page": per_page, **(extra_params or {})}
    data = _get(endpoint, params)
    if data and isinstance(data, dict):
        return data.get("items", [])
    return []


# ---- individual searches ----------------------------------------------------

def get_user_profile(username: str) -> dict | None:
    return _get(f"/users/{username}")


def search_users(query: str) -> list[dict]:
    return _search("/search/users", query)


def get_user_repos(username: str, limit: int = 10) -> list[dict]:
    data = _get(f"/users/{username}/repos",
                {"sort": "updated", "per_page": limit})
    return data if isinstance(data, list) else []


def get_user_gists(username: str) -> list[dict]:
    data = _get(f"/users/{username}/gists", {"per_page": 5})
    return data if isinstance(data, list) else []


def search_commits_by_email(email: str) -> list[dict]:
    """
    Search commits authored by a specific email.
    This can reveal GitHub accounts behind any email address.
    """
    items = _search(
        "/search/commits", f"author-email:{email}",
        extra_params={"Accept": "application/vnd.github.cloak-preview+json"},
    )
    time.sleep(0.5)  # search API secondary rate limit
    return items


def search_commits_by_name(name: str) -> list[dict]:
    items = _search("/search/commits", f"author-name:{name}")
    time.sleep(0.5)
    return items


def search_code(query: str) -> list[dict]:
    """Search code for an email address, phone number, or other string."""
    items = _search("/search/code", query, per_page=5)
    time.sleep(0.5)
    return items


def search_issues(query: str) -> list[dict]:
    return _search("/search/issues", f"{query} type:issue", per_page=5)


def search_repos(query: str) -> list[dict]:
    return _search("/search/repositories", query, per_page=5)


# ---- rendering helpers ------------------------------------------------------

def _divider(label: str) -> None:
    console.print(f"\n  [bold cyan][ {label} ][/bold cyan]")


def _ok(msg: str) -> None:
    console.print(f"    [bold green][+][/bold green] {safe(msg)}")


def _info(key: str, val: str) -> None:
    console.print(f"    [dim]{key}:[/dim] {safe(str(val))}")


def _muted(msg: str) -> None:
    console.print(f"  [dim]  {msg}[/dim]")


# ---- main run ---------------------------------------------------------------

def run(username: str = "", email: str = "", name: str = "") -> None:
    print_section("GITHUB OSINT")

    if not any([username, email, name]):
        console.print("  [red]Provide --username, --email, or --name.[/red]")
        return

    rate_note = "[dim](Set GITHUB_TOKEN env var for higher rate limits)[/dim]"
    console.print(f"  {rate_note}")
    if _TOKEN:
        console.print("  [dim green]GitHub token detected -- authenticated mode.[/dim green]")

    # ---- 1. Direct user profile ---------------------------------------------
    if username:
        _divider(f"User Profile: {username}")
        console.print(f"  [dim]Fetching github.com/{username}...[/dim]")
        profile = get_user_profile(username)

        if profile:
            fields = [
                ("Login",      profile.get("login", "")),
                ("Name",       profile.get("name", "")),
                ("Email",      profile.get("email", "")),
                ("Bio",        profile.get("bio", "")),
                ("Company",    profile.get("company", "")),
                ("Location",   profile.get("location", "")),
                ("Blog",       profile.get("blog", "")),
                ("Twitter",    profile.get("twitter_username", "")),
                ("Followers",  profile.get("followers", "")),
                ("Following",  profile.get("following", "")),
                ("Public repos", profile.get("public_repos", "")),
                ("Public gists", profile.get("public_gists", "")),
                ("Created",    profile.get("created_at", "")[:10]),
                ("Updated",    profile.get("updated_at", "")[:10]),
                ("Profile URL", profile.get("html_url", "")),
                ("Avatar",     profile.get("avatar_url", "")),
            ]
            for k, v in fields:
                if v:
                    _info(k, str(v))

            if reporter.active():
                reporter.add("GitHub / User Profile", {
                    k: str(v) for k, v in fields if v
                })
        else:
            _muted(f"No GitHub user found for '{username}'.")

        # Repositories
        _divider(f"Repositories: {username}")
        repos = get_user_repos(username)
        if repos:
            for r in repos:
                stars = r.get("stargazers_count", 0)
                lang = r.get("language") or ""
                desc = r.get("description") or ""
                pushed = (r.get("pushed_at") or "")[:10]
                _ok(f"{r['name']}  "
                    + (f"[{lang}]  " if lang else "")
                    + (f"* {stars}  " if stars else "")
                    + (f"{pushed}  " if pushed else "")
                    + (f"-- {desc[:60]}" if desc else ""))
                if reporter.active():
                    reporter.add("GitHub / Repositories", {
                        "name": r["name"],
                        "url": r.get("html_url", ""),
                        "language": lang,
                        "stars": str(stars),
                        "description": desc[:80],
                        "last_push": pushed,
                        "source": "github.com",
                    })
        else:
            _muted("No public repositories found.")

        # Gists
        gists = get_user_gists(username)
        if gists:
            _divider(f"Gists: {username}")
            for g in gists:
                desc = g.get("description") or "(no description)"
                url = g.get("html_url", "")
                updated = (g.get("updated_at") or "")[:10]
                _ok(f"{safe(desc[:70])}  {updated}")
                console.print(f"      [cyan]{url}[/cyan]")
                if reporter.active():
                    reporter.add("GitHub / Gists", {
                        "description": desc[:80],
                        "url": url,
                        "updated": updated,
                        "source": "github.com",
                    })

    # ---- 2. Search by email -------------------------------------------------
    if email:
        _divider(f"Commits by email: {email}")
        console.print(f"  [dim]Searching commit history for {email}...[/dim]")
        commits = search_commits_by_email(email)
        if commits:
            seen_authors = set()
            for c in commits[:8]:
                author = c.get("author") or {}
                commit_data = c.get("commit", {})
                author_info = commit_data.get("author", {})
                login = (author.get("login") or "")
                a_name = author_info.get("name", "")
                a_email = author_info.get("email", "")
                repo_name = (c.get("repository") or {}).get("full_name", "")
                sha = c.get("sha", "")[:7]
                url = c.get("html_url", "")
                msg = commit_data.get("message", "").split("\n")[0][:60]

                key = login or a_email
                if key not in seen_authors:
                    seen_authors.add(key)
                    if login:
                        _ok(f"GitHub account: [bold]{login}[/bold]  "
                            f"(name: {a_name})")
                _info(f"  {sha}", f"{safe(msg)}  [{repo_name}]")
                console.print(f"      [cyan]{url}[/cyan]")

                if reporter.active():
                    reporter.add("GitHub / Commits by Email", {
                        "github_login": login,
                        "author_name": a_name,
                        "author_email": a_email,
                        "repository": repo_name,
                        "commit": sha,
                        "message": msg,
                        "url": url,
                        "source": "github.com",
                    })
        else:
            _muted("No commits found for this email.")

        # Also search code for email leaks
        _divider(f"Code containing: {email}")
        console.print(f"  [dim]Searching code for '{email}'...[/dim]")
        code_results = search_code(f'"{email}"')
        if code_results:
            for item in code_results[:5]:
                repo = item.get("repository", {}).get("full_name", "")
                file_path = item.get("path", "")
                url = item.get("html_url", "")
                _ok(f"{repo} / {file_path}")
                console.print(f"      [cyan]{url}[/cyan]")
                if reporter.active():
                    reporter.add("GitHub / Code Containing Email", {
                        "repository": repo,
                        "file": file_path,
                        "url": url,
                        "source": "github.com",
                    })
        else:
            _muted("No code results found.")

    # ---- 3. Search by name --------------------------------------------------
    if name:
        _divider(f"User search: {name}")
        console.print(f"  [dim]Searching GitHub users for '{name}'...[/dim]")
        users = search_users(name)
        if users:
            for u in users[:8]:
                login = u.get("login", "")
                url = u.get("html_url", "")
                _ok(f"{login}  --  {url}")
                if reporter.active():
                    reporter.add("GitHub / User Search", {
                        "login": login,
                        "url": url,
                        "source": "github.com",
                    })

                # fetch full profile for top result
                if users.index(u) == 0:
                    profile = get_user_profile(login)
                    if profile:
                        for field in ("name", "email", "company",
                                      "location", "bio", "twitter_username"):
                            val = profile.get(field, "")
                            if val:
                                _info(f"  {field.capitalize()}", str(val))
        else:
            _muted(f"No users found for '{name}'.")

        # Commits by name
        _divider(f"Commits by name: {name}")
        console.print(f"  [dim]Searching commits authored by '{name}'...[/dim]")
        commits = search_commits_by_name(name)
        if commits:
            seen_emails = set()
            for c in commits[:8]:
                commit_data = c.get("commit", {})
                author_info = commit_data.get("author", {})
                a_email = author_info.get("email", "")
                a_name = author_info.get("name", "")
                repo = (c.get("repository") or {}).get("full_name", "")
                sha = c.get("sha", "")[:7]
                url = c.get("html_url", "")
                msg = commit_data.get("message", "").split("\n")[0][:60]

                if a_email and a_email not in seen_emails:
                    seen_emails.add(a_email)
                    _ok(f"Email exposed: [bold]{a_email}[/bold]  (name: {a_name})")

                _info(f"  {sha}", f"{safe(msg)}  [{repo}]")
                console.print(f"      [cyan]{url}[/cyan]")

                if reporter.active():
                    reporter.add("GitHub / Commits by Name", {
                        "author_name": a_name,
                        "author_email": a_email,
                        "repository": repo,
                        "commit": sha,
                        "message": msg,
                        "url": url,
                        "source": "github.com",
                    })
        else:
            _muted("No commits found.")

        # Issues/PRs
        _divider(f"Issues/PRs: {name}")
        console.print(f"  [dim]Searching issues/PRs mentioning '{name}'...[/dim]")
        issues = search_issues(name)
        if issues:
            for issue in issues[:5]:
                title = issue.get("title", "")
                url = issue.get("html_url", "")
                author = (issue.get("user") or {}).get("login", "")
                state = issue.get("state", "")
                _ok(f"[{state}] {safe(title[:60])}  by {author}")
                console.print(f"      [cyan]{url}[/cyan]")
                if reporter.active():
                    reporter.add("GitHub / Issues & PRs", {
                        "title": title[:80],
                        "author": author,
                        "state": state,
                        "url": url,
                        "source": "github.com",
                    })
        else:
            _muted("No issues/PRs found.")
