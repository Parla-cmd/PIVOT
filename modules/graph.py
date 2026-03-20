"""
Graph Visualisation
--------------------
Builds an interactive entity-relationship graph from reporter data.
Uses pyvis (wraps vis.js) → exports a self-contained HTML file.

Node types and colours:
  person   → #4da6ff  (blue)
  email    → #ff9944  (orange)
  phone    → #44cc77  (green)
  company  → #ff4444  (red)
  domain   → #aa44ff  (purple)
  social   → #ffdd00  (yellow)
  address  → #aaaaaa  (grey)
  breach   → #ff6688  (pink)
"""

try:
    from pyvis.network import Network
    _HAS_PYVIS = True
except ImportError:
    _HAS_PYVIS = False

from .utils import console

# ── visual config ──────────────────────────────────────────────────────────────

_COLORS = {
    "person":  "#4da6ff",
    "email":   "#ff9944",
    "phone":   "#44cc77",
    "company": "#ff4444",
    "domain":  "#aa44ff",
    "social":  "#ffdd00",
    "address": "#aaaaaa",
    "breach":  "#ff6688",
    "default": "#cccccc",
}

_SHAPES = {
    "person":  "ellipse",
    "company": "box",
    "domain":  "diamond",
    "breach":  "triangle",
    "default": "dot",
}


def _node_style(kind: str) -> dict[str, object]:
    color = _COLORS.get(kind, _COLORS["default"])
    shape = _SHAPES.get(kind, _SHAPES["default"])
    return {"color": color, "shape": shape, "font": {"color": "#ffffff", "size": 14}}


# ── graph builder ──────────────────────────────────────────────────────────────

class OsintGraph:
    """Accumulates OSINT findings and exports to pyvis HTML."""

    def __init__(self):
        self._nodes: dict[str, dict] = {}   # id → {label, kind, title}
        self._edges: list[tuple]     = []   # (src_id, dst_id, label)

    def _node_id(self, kind: str, value: str) -> str:
        return f"{kind}::{value.lower().strip()}"

    def add_node(self, kind: str, value: str, tooltip: str = "") -> str:
        nid = self._node_id(kind, value)
        if nid not in self._nodes:
            self._nodes[nid] = {"label": value, "kind": kind, "title": tooltip or value}
        return nid

    def add_edge(self, src_id: str, dst_id: str, label: str = "") -> None:
        edge = (src_id, dst_id, label)
        if edge not in self._edges:
            self._edges.append(edge)

    def link(self, kind_a: str, val_a: str, kind_b: str, val_b: str, label: str = "") -> None:
        if not val_a or not val_b:
            return
        a = self.add_node(kind_a, val_a)
        b = self.add_node(kind_b, val_b)
        self.add_edge(a, b, label)

    # ── feed from reporter data ────────────────────────────────────────────────

    def ingest_reporter(self, findings: list[dict]) -> None:
        """
        Walk through all reporter findings and build graph edges.
        The reporter stores rows like: {"_section": "...", "key": "value", ...}
        """
        for row in findings:
            section = row.get("_section", "")

            name    = row.get("name", "") or row.get("person", "")
            email   = row.get("email", "")
            phone   = row.get("phone", "")
            company = row.get("company", "")
            address = row.get("address", "") or row.get("alt_address", "")
            domain  = row.get("domain", "")
            breach  = row.get("breach", "")
            platform = row.get("platform", "")
            url     = row.get("url", "")
            username = row.get("username", "")
            subdomain = row.get("subdomain", "")

            # Build edges based on what fields co-occur
            if name and email:
                self.link("person", name, "email", email, "uses")
            if name and phone:
                self.link("person", name, "phone", phone, "uses")
            if name and company:
                self.link("person", name, "company", company, "works at")
            if name and address:
                self.link("person", name, "address", address, "lives at")
            if email and breach:
                self.link("email", email, "breach", breach, "found in")
            if email and domain:
                self.link("email", email, "domain", domain, "hosted at")
            if subdomain and domain:
                self.link("domain", domain, "domain", subdomain, "subdomain")
            if name and platform and url:
                label = f"@{username}" if username else platform
                self.link("person", name, "social", f"{platform}: {label}", "profile at")
            if email and platform and url:
                self.link("email", email, "social", f"{platform}: {username}", "linked to")
            if phone and name and "correlate" in section.lower():
                self.link("phone", phone, "person", name, "belongs to")
            if email and name and "correlate" in section.lower():
                self.link("email", email, "person", name, "belongs to")

    # ── export ─────────────────────────────────────────────────────────────────

    def save(self, path: str, title: str = "PIVOT — OSINT Graph") -> bool:
        if not _HAS_PYVIS:
            console.print(
                "  [yellow][!][/yellow] pyvis not installed — "
                "run [bold]pip install pyvis[/bold] to enable graph export."
            )
            return False

        if not self._nodes:
            console.print("  [yellow][!][/yellow] No graph nodes — nothing to visualize.")
            return False

        net = Network(
            height="900px",
            width="100%",
            bgcolor="#1a1a2e",
            font_color="#ffffff",
            directed=True,
            notebook=False,
        )
        net.set_options("""
        {
          "physics": {
            "barnesHut": {
              "gravitationalConstant": -8000,
              "centralGravity": 0.3,
              "springLength": 180
            },
            "minVelocity": 0.75
          },
          "edges": {
            "arrows": { "to": { "enabled": true, "scaleFactor": 0.6 } },
            "color": { "color": "#555577", "highlight": "#aaaaff" },
            "smooth": { "type": "curvedCW", "roundness": 0.2 }
          },
          "interaction": { "hover": true, "navigationButtons": true }
        }
        """)

        for nid, props in self._nodes.items():
            kind  = props["kind"]
            style = _node_style(kind)
            net.add_node(
                nid,
                label=props["label"],
                title=f"[{kind}] {props['title']}",
                color=style["color"],
                shape=style["shape"],
                font=style["font"],
                size=20,
            )

        for src, dst, label in self._edges:
            if src in self._nodes and dst in self._nodes:
                net.add_edge(src, dst, title=label, label=label)

        # Inject a small legend into the HTML
        legend_html = _legend_html()

        net.save_graph(path)

        # Patch the saved HTML to inject legend + dark title bar
        try:
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()
            html = html.replace(
                "<body>",
                f"<body>\n{legend_html}\n"
            ).replace(
                "<title>",
                f"<title>{title} — "
            )
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
        except Exception:
            pass  # graph still works without the legend patch

        console.print(f"  [bold green][+][/bold green] Graph saved: [cyan]{path}[/cyan]")
        console.print(f"      {len(self._nodes)} nodes, {len(self._edges)} edges")
        return True


def _legend_html() -> str:
    items = [
        ("person",  "Person"),
        ("email",   "Email"),
        ("phone",   "Phone"),
        ("company", "Company"),
        ("domain",  "Domain"),
        ("social",  "Social"),
        ("address", "Address"),
        ("breach",  "Data Breach"),
    ]
    swatches = "".join(
        f'<span style="display:inline-block;width:14px;height:14px;'
        f'background:{_COLORS[k]};border-radius:3px;margin:0 4px 0 12px;'
        f'vertical-align:middle"></span><span style="color:#eee;font-size:12px">{label}</span>'
        for k, label in items
    )
    return (
        f'<div style="position:fixed;top:0;left:0;right:0;z-index:9999;'
        f'background:#0f0f1a;padding:8px 16px;font-family:monospace;'
        f'border-bottom:1px solid #333">'
        f'<span style="color:#4da6ff;font-weight:bold;margin-right:16px">'
        f'PIVOT OSINT Graph</span>{swatches}</div>'
        f'<div style="height:36px"></div>'
    )


# ── convenience builder from reporter ─────────────────────────────────────────

def build_from_reporter(findings: list[dict], output_path: str, target: str = "") -> bool:
    g = OsintGraph()
    g.ingest_reporter(findings)
    return g.save(output_path, title=f"PIVOT — {target}" if target else "PIVOT OSINT Graph")
