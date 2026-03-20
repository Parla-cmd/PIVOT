"""
Report Collector + Exporter
---------------------------
Any module calls report.add(section, data_dict) to register a finding.
At the end of a run, main.py calls report.save(path) to write JSON or HTML.
"""
import json
import html as html_lib
from datetime import datetime
from typing import Any

# ---- global singleton -------------------------------------------------------

_instance: "Report | None" = None


def init(target: str = ""):
    global _instance
    _instance = Report(target)


def add(section: str, data: dict):
    if _instance:
        _instance.add(section, data)


def save(path: str):
    if _instance:
        _instance.save(path)


def active() -> bool:
    return _instance is not None


def get_all() -> list[dict]:
    """Return all findings as a flat list with _section key injected."""
    if not _instance:
        return []
    rows = []
    for section, entries in _instance._sections.items():
        for entry in entries:
            rows.append({**entry, "_section": section})
    return rows


# ---- Report class -----------------------------------------------------------

class Report:
    def __init__(self, target: str):
        self.target = target
        self.timestamp = datetime.now().isoformat(timespec="seconds")
        self._sections: dict[str, list[dict]] = {}

    def add(self, section: str, data: dict):
        self._sections.setdefault(section, []).append(data)

    def to_dict(self) -> dict:
        return {
            "tool": "Sweden OSINT Tool",
            "target": self.target,
            "generated": self.timestamp,
            "sections": self._sections,
        }

    def save(self, path: str):
        if path.endswith(".json"):
            self._save_json(path)
        elif path.endswith(".html"):
            self._save_html(path)
        else:
            # default to JSON
            self._save_json(path + ".json")

    # ---- JSON ---------------------------------------------------------------

    def _save_json(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2, default=str)
        print(f"\n  [Report] Saved JSON -> {path}")

    # ---- HTML ---------------------------------------------------------------

    def _save_html(self, path: str):
        body_parts = []
        for section, findings in self._sections.items():
            rows = ""
            for entry in findings:
                rows += _render_entry(entry)
            body_parts.append(f"""
        <section>
          <h2>{html_lib.escape(section)}</h2>
          <div class="findings">
            {rows}
          </div>
        </section>""")

    # count totals
        total_findings = sum(len(v) for v in self._sections.values())
        sections_count = len(self._sections)
        target_safe = html_lib.escape(self.target)
        ts_safe = html_lib.escape(self.timestamp)
        body_html = "\n".join(body_parts)

        page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>OSINT Report -- {target_safe}</title>
  <style>
    :root {{
      --bg: #0d1117;
      --surface: #161b22;
      --surface2: #21262d;
      --border: #30363d;
      --accent: #58a6ff;
      --accent2: #3fb950;
      --warn: #d29922;
      --danger: #f85149;
      --text: #c9d1d9;
      --muted: #8b949e;
      --radius: 8px;
      --font: 'Segoe UI', system-ui, sans-serif;
      --mono: 'Cascadia Code', 'Consolas', monospace;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: var(--font);
      font-size: 14px;
      line-height: 1.6;
    }}
    header {{
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 24px 40px;
      display: flex;
      align-items: center;
      gap: 24px;
    }}
    .logo {{
      font-size: 22px;
      font-weight: 700;
      color: var(--accent);
      letter-spacing: 1px;
      white-space: nowrap;
    }}
    .logo span {{ color: var(--accent2); }}
    .header-meta {{ flex: 1; }}
    .header-meta h1 {{
      font-size: 16px;
      color: var(--text);
      font-weight: 600;
      margin-bottom: 4px;
    }}
    .header-meta p {{ color: var(--muted); font-size: 12px; }}
    .badge {{
      background: var(--surface2);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 4px 14px;
      font-size: 12px;
      color: var(--muted);
      white-space: nowrap;
    }}
    .badge b {{ color: var(--accent); }}
    main {{
      max-width: 1000px;
      margin: 32px auto;
      padding: 0 24px;
    }}
    .summary-cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
      margin-bottom: 32px;
    }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 16px 20px;
    }}
    .card .num {{
      font-size: 28px;
      font-weight: 700;
      color: var(--accent);
      display: block;
    }}
    .card .lbl {{
      font-size: 12px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    section {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      margin-bottom: 20px;
      overflow: hidden;
    }}
    section h2 {{
      font-size: 13px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: var(--accent);
      padding: 14px 20px;
      background: var(--surface2);
      border-bottom: 1px solid var(--border);
      cursor: pointer;
      user-select: none;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    section h2::after {{
      content: attr(data-count);
      font-size: 11px;
      background: var(--bg);
      color: var(--muted);
      border-radius: 10px;
      padding: 2px 8px;
      font-weight: 400;
      letter-spacing: 0;
    }}
    .findings {{ padding: 4px 0; }}
    .entry {{
      border-bottom: 1px solid var(--border);
      padding: 12px 20px;
      display: grid;
      gap: 4px;
    }}
    .entry:last-child {{ border-bottom: none; }}
    .entry-row {{
      display: flex;
      gap: 12px;
      align-items: baseline;
    }}
    .entry-key {{
      color: var(--muted);
      font-size: 12px;
      min-width: 120px;
      flex-shrink: 0;
    }}
    .entry-val {{
      color: var(--text);
      word-break: break-all;
    }}
    .entry-val a {{
      color: var(--accent);
      text-decoration: none;
    }}
    .entry-val a:hover {{ text-decoration: underline; }}
    .tag {{
      display: inline-block;
      font-size: 11px;
      padding: 1px 8px;
      border-radius: 4px;
      font-family: var(--mono);
    }}
    .tag-source {{
      background: #1f2d3d;
      color: var(--accent);
      border: 1px solid #2d4a6a;
    }}
    .tag-breach {{
      background: #2d1b1b;
      color: var(--danger);
      border: 1px solid #5a2424;
    }}
    .tag-found {{
      background: #1a2d1e;
      color: var(--accent2);
      border: 1px solid #2d5a34;
    }}
    footer {{
      text-align: center;
      color: var(--muted);
      font-size: 12px;
      padding: 32px 0 48px;
    }}
    footer a {{ color: var(--accent); text-decoration: none; }}
  </style>
</head>
<body>
  <header>
    <div class="logo">SWEDEN<span>OSINT</span></div>
    <div class="header-meta">
      <h1>Report: {target_safe}</h1>
      <p>Generated {ts_safe} &nbsp;|&nbsp; Educational use only</p>
    </div>
    <div class="badge"><b>{total_findings}</b> findings &nbsp; <b>{sections_count}</b> modules</div>
  </header>

  <main>
    <div class="summary-cards">
      <div class="card">
        <span class="num">{total_findings}</span>
        <span class="lbl">Total Findings</span>
      </div>
      <div class="card">
        <span class="num">{sections_count}</span>
        <span class="lbl">Modules Run</span>
      </div>
      <div class="card">
        <span class="num" style="font-size:16px;padding-top:6px">{target_safe}</span>
        <span class="lbl">Target</span>
      </div>
    </div>

    {body_html}
  </main>

  <footer>
    Sweden OSINT Tool &mdash; For authorized, lawful use only &mdash;
    <a href="https://github.com">Educational Project</a>
  </footer>

  <script>
    document.querySelectorAll('section h2').forEach(h2 => {{
      const findings = h2.nextElementSibling;
      const count = findings.querySelectorAll('.entry').length;
      h2.dataset.count = count + ' result' + (count !== 1 ? 's' : '');
      h2.addEventListener('click', () => {{
        const hidden = findings.style.display === 'none';
        findings.style.display = hidden ? '' : 'none';
      }});
    }});
  </script>
</body>
</html>"""

        with open(path, "w", encoding="utf-8") as f:
            f.write(page)
        print(f"\n  [Report] Saved HTML -> {path}")


# ---- HTML rendering helpers -------------------------------------------------

def _render_entry(entry: dict) -> str:
    rows = ""
    source = entry.get("source", "")
    for key, val in entry.items():
        if key == "source" or not val:
            continue
        val_str = str(val)
        # linkify URLs
        if val_str.startswith("http"):
            rendered = f'<a href="{html_lib.escape(val_str)}" target="_blank">{html_lib.escape(val_str)}</a>'
        elif key in ("breach", "name") and "breach" in entry.get("_type", ""):
            rendered = f'<span class="tag tag-breach">{html_lib.escape(val_str)}</span>'
        else:
            rendered = html_lib.escape(val_str)

        rows += f"""
          <div class="entry-row">
            <span class="entry-key">{html_lib.escape(key.replace("_", " ").title())}</span>
            <span class="entry-val">{rendered}</span>
          </div>"""

    if source:
        rows += f"""
          <div class="entry-row">
            <span class="entry-key">Source</span>
            <span class="entry-val"><span class="tag tag-source">{html_lib.escape(source)}</span></span>
          </div>"""

    return f'<div class="entry">{rows}</div>'
