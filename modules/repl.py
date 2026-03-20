"""
Interactive REPL
-----------------
Provides a persistent shell so you can run multiple lookups without
restarting the process.  Uses Python's cmd.Cmd for readline history.

Commands mirror the CLI exactly:
  pivot> person --name "Anna Svensson" --city Stockholm
  pivot> email  --email a@example.se
  pivot> phone  --phone 070-123 45 67
  pivot> correlate --target anna@example.se
  pivot> watch   --target anna@example.se
  pivot> wayback --url example.se
  pivot> graph   report.html
  pivot> proxy   socks5h://127.0.0.1:9050
  pivot> proxy   off
  pivot> help
  pivot> exit
"""
import cmd
import shlex
import sys

try:
    import readline        # Unix
except ImportError:
    try:
        import pyreadline3  # Windows  # noqa: F401
    except ImportError:
        pass

from .utils import console, set_proxy

BANNER = """
  [bold cyan]PIVOT — Interactive REPL[/bold cyan]
  [dim]Type [bold]help[/bold] for commands, [bold]exit[/bold] to quit.[/dim]
"""

HELP_TEXT = """
[bold]Available commands[/bold]

  person    --name "Name" [--city City] [--pnr PNR]
  company   --name "Name" [--orgnr ORG]
  phone     --phone 070XXXXXXX
  email     --email user@domain.se
  domain    --domain example.se
  social    --username handle
  news      --query "search term"
  geo       --address "Storgatan 1, Stockholm"
  github    --username handle [--email e] [--name n]
  harvest   --domain example.se [--deep]
  paste     --target email@example.se
  correlate --target email_or_phone
  folkbok   --name "Name" [--city City]       (folkbokföring)
  vehicle   --plate ABC123                    (fordonsregistret)
  wayback   --url example.se [--limit 30]
  watch     --target email_or_phone [--check]
  watch     --list
  proxy     socks5h://127.0.0.1:9050          (enable Tor/proxy)
  proxy     off                               (disable proxy)
  output    report.html                       (set output file)
  output    off                               (disable output)
  graph     graph.html                        (export graph now)
  clear                                       (clear screen)
  exit / quit                                 (leave REPL)

[dim]--no-disclaimer is implied inside the REPL.[/dim]
"""


class PivotRepl(cmd.Cmd):
    prompt = "  \x1b[36mpivot\x1b[0m> "
    intro  = ""

    def __init__(self):
        super().__init__()
        self._output_file: str = ""

    # ── helpers ───────────────────────────────────────────────────────────────

    def _run_with_args(self, line: str, module_name: str):
        """Build a fake argparse Namespace and call the appropriate module."""
        import argparse
        from main import build_parser, run_module
        from modules import reporter as _reporter

        try:
            parts = shlex.split(f"{module_name} {line}")
        except ValueError as e:
            console.print(f"  [red]Parse error:[/red] {e}")
            return

        parser = build_parser()
        # Inject --no-disclaimer so REPL never asks again
        try:
            args = parser.parse_args(["--no-disclaimer"] + parts)
        except SystemExit:
            return

        if self._output_file:
            args.output = self._output_file
            _reporter.init(target=getattr(args, "target", None)
                           or getattr(args, "name", None)
                           or getattr(args, "domain", None)
                           or "repl")

        try:
            run_module(args)
        except Exception as e:
            console.print(f"  [red]Error:[/red] {e}")
            return

        if self._output_file and _reporter.active():
            _reporter.save(self._output_file)
            console.print(f"  [dim]Report appended: {self._output_file}[/dim]")

    # ── module commands ───────────────────────────────────────────────────────

    def do_person(self, line):    self._run_with_args(line, "person")
    def do_company(self, line):   self._run_with_args(line, "company")
    def do_phone(self, line):     self._run_with_args(line, "phone")
    def do_email(self, line):     self._run_with_args(line, "email")
    def do_domain(self, line):    self._run_with_args(line, "domain")
    def do_social(self, line):    self._run_with_args(line, "social")
    def do_news(self, line):      self._run_with_args(line, "news")
    def do_geo(self, line):       self._run_with_args(line, "geo")
    def do_github(self, line):    self._run_with_args(line, "github")
    def do_harvest(self, line):   self._run_with_args(line, "harvest")
    def do_paste(self, line):     self._run_with_args(line, "paste")
    def do_correlate(self, line): self._run_with_args(line, "correlate")

    def do_folkbok(self, line):
        try:
            parts = shlex.split(line)
        except ValueError as e:
            console.print(f"  [red]Parse error:[/red] {e}")
            return
        import argparse
        p = argparse.ArgumentParser(prog="folkbok", add_help=False)
        p.add_argument("--name", default="")
        p.add_argument("--city", default="")
        try:
            a, _ = p.parse_known_args(parts)
        except SystemExit:
            return
        if not a.name:
            console.print("  [red]Provide --name[/red]")
            return
        from modules.folkbokforing import run_person
        run_person(name=a.name, city=a.city)

    def do_vehicle(self, line):
        try:
            parts = shlex.split(line)
        except ValueError as e:
            console.print(f"  [red]Parse error:[/red] {e}")
            return
        import argparse
        p = argparse.ArgumentParser(prog="vehicle", add_help=False)
        p.add_argument("--plate", default="")
        try:
            a, _ = p.parse_known_args(parts)
        except SystemExit:
            return
        if not a.plate:
            console.print("  [red]Provide --plate[/red]")
            return
        from modules.folkbokforing import run_vehicle
        run_vehicle(plate=a.plate)

    def do_wayback(self, line):
        try:
            parts = shlex.split(line)
        except ValueError as e:
            console.print(f"  [red]Parse error:[/red] {e}")
            return
        import argparse
        p = argparse.ArgumentParser(prog="wayback", add_help=False)
        p.add_argument("--url", default="")
        p.add_argument("--limit", type=int, default=30)
        try:
            a, rest = p.parse_known_args(parts)
        except SystemExit:
            return
        url = a.url or (rest[0] if rest else "")
        if not url:
            console.print("  [red]Provide --url <domain>[/red]")
            return
        from modules.wayback import run
        run(url=url, limit=a.limit)

    def do_watch(self, line):
        try:
            parts = shlex.split(line)
        except ValueError as e:
            console.print(f"  [red]Parse error:[/red] {e}")
            return
        import argparse
        p = argparse.ArgumentParser(prog="watch", add_help=False)
        p.add_argument("--target", default="")
        p.add_argument("--check", action="store_true")
        p.add_argument("--list",  action="store_true")
        try:
            a, _ = p.parse_known_args(parts)
        except SystemExit:
            return
        from modules.watcher import run, run_list
        if a.list:
            run_list()
        elif a.target:
            run(target=a.target, check=a.check)
        else:
            console.print("  [red]Provide --target or --list[/red]")

    # ── utility commands ──────────────────────────────────────────────────────

    def do_proxy(self, line):
        """proxy <url>  |  proxy off"""
        line = line.strip()
        if not line or line.lower() == "off":
            set_proxy("")
            console.print("  [dim]Proxy disabled.[/dim]")
        else:
            set_proxy(line)

    def do_output(self, line):
        """output <file.html|file.json>  |  output off"""
        line = line.strip()
        if not line or line.lower() == "off":
            self._output_file = ""
            console.print("  [dim]Output file disabled.[/dim]")
        else:
            self._output_file = line
            console.print(f"  [dim]Output file set: [bold]{line}[/bold][/dim]")

    def do_graph(self, line):
        """graph <output.html>  — export graph from current session's reporter data"""
        path = line.strip()
        if not path:
            path = "pivot_graph.html"
        from modules import reporter as _reporter
        from modules.graph import build_from_reporter
        findings = _reporter.get_all()
        if not findings:
            console.print("  [yellow][!][/yellow] No data collected yet — run some lookups first.")
            return
        build_from_reporter(findings, path, target="REPL session")

    def do_clear(self, _):
        """Clear the terminal screen."""
        import os
        os.system("cls" if sys.platform == "win32" else "clear")

    def do_help(self, _):
        console.print(HELP_TEXT)

    def do_exit(self, _):
        console.print("\n  [dim]Goodbye.[/dim]\n")
        return True

    def do_quit(self, line):
        return self.do_exit(line)

    def default(self, line):
        console.print(f"  [red]Unknown command:[/red] [bold]{line.split()[0]}[/bold]  "
                      f"(type [bold]help[/bold])")

    # ── prevent crash on Ctrl+D ────────────────────────────────────────────────
    def do_EOF(self, _):
        return self.do_exit(_)


def run():
    console.print(BANNER)
    try:
        PivotRepl().cmdloop()
    except KeyboardInterrupt:
        console.print("\n  [dim]Interrupted. Type [bold]exit[/bold] to quit cleanly.[/dim]\n")
