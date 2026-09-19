"""Structural probe for section 6.5 of webapp-big-prep-panel.

Reads the served index page and asserts the panel markup landed where the task
requires, without needing a browser:

  1. GET / is 200 and /api/schema is 200 (the backend was not touched);
  2. ``id="drawer-resizer"`` appears BEFORE ``</aside>``;
  3. every direct child of a ``<div class="grid">`` is ``<div class="field">``
     (no bare <label>/<input>/<select>), and there are 15 of them;
  4. ``id="drawer-scrim"``, ``id="dp-loaded-hint"`` and ``#designer-left-col``
     exist (the last one is the dedicated slot container from P0-0).
"""
import json
import sys
import urllib.request
from html.parser import HTMLParser

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8349"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}

failures = []


def check(label, condition, detail=""):
    print(("PASS " if condition else "FAIL ") + label
          + (("  -> " + detail) if detail and not condition else ""))
    if not condition:
        failures.append(label)


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as response:
        return response.status, response.read()


class GridParser(HTMLParser):
    """Record the direct children of every element carrying class ``grid``."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.grids = {}

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if "grid" in classes:
            self.grids[id(self)] = self.grids.get(id(self), [])
            self.stack.append({"tag": tag, "fields": [], "grid": True})
            return
        if self.stack:
            self.stack[-1]["fields"].append((tag, classes))
        if tag not in VOID:
            self.stack.append({"tag": tag, "fields": [], "grid": False})

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1]["tag"] == tag:
            node = self.stack.pop()
            if node["grid"]:
                self.grids.setdefault("grids", []).append(node["fields"])


status, body = get("/")
html_text = body.decode("utf-8")
print("GET / -> HTTP %d (%d bytes)" % (status, len(body)))
check("GET / is 200", status == 200)
check("GET / has the resizer", 'id="drawer-resizer"' in html_text)
check("GET / has the scrim", 'id="drawer-scrim"' in html_text)
check("GET / has the panel hint", 'id="dp-loaded-hint"' in html_text)
check("GET / has the left slot container", 'id="designer-left-col"' in html_text)
check("resizer sits before </aside>",
      html_text.index('id="drawer-resizer"') < html_text.index("</aside>"))

parser = GridParser()
parser.feed(html_text)
grids = parser.grids.get("grids", [])
print("grid blocks found: %d" % len(grids))
bare = []
fields = 0
for children in grids:
    for tag, classes in children:
        if tag == "div" and "field" in classes:
            fields += 1
        elif tag in ("label", "input", "select"):
            bare.append(tag)
print("direct .field children: %d | bare label/input/select: %d"
      % (fields, len(bare)))
check("no bare control directly under .grid", not bare)
check("15 field wrappers in the four grid blocks", fields == 15,
      "found %d" % fields)

status, schema_body = get("/api/schema")
schema = json.loads(schema_body.decode("utf-8"))
print("GET /api/schema -> HTTP %d (%d bytes, %d keys)"
      % (status, len(schema_body), len(schema)))
check("GET /api/schema is 200", status == 200)

print("")
print("probe_panel_structure.py: " + ("all checks passed" if not failures
                                       else "%d check(s) FAILED" % len(failures)))
sys.exit(1 if failures else 0)