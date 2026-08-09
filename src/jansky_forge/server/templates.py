"""Page templates as plain Python strings.

Jinja2 would be the obvious choice and is deliberately not used: there are four pages, the
markup is static apart from a handful of substitutions, and a template engine plus a
templates directory plus package-data configuration is a lot of machinery for that. If the
UI grows past a dozen pages this is the first thing to replace.

The CSS is inline and theme-aware through ``prefers-color-scheme``, so the page follows the
reader's system setting without a toggle or a second stylesheet. The JavaScript is about
thirty lines and fetches a partial when an input changes — no library, no CDN, so the tool
works on a laptop in a field with no signal, which is where antennas get built.
"""

from __future__ import annotations

_CSS = """
:root { color-scheme: light dark; --bg:#fff; --fg:#111; --muted:#666; --line:#ddd;
        --accent:#2563eb; --warn:#92400e; --warn-bg:#fef3c7; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#111418; --fg:#e8e8e8; --muted:#9aa0a6; --line:#2a2f36;
          --accent:#60a5fa; --warn:#fbbf24; --warn-bg:#2a2313; }
}
* { box-sizing: border-box; }
body { margin:0; font-family: system-ui, -apple-system, sans-serif; background:var(--bg);
       color:var(--fg); line-height:1.55; }
header { border-bottom:1px solid var(--line); padding:0.75rem 1.25rem;
         display:flex; gap:1.25rem; align-items:baseline; flex-wrap:wrap; }
header .brand { font-weight:700; letter-spacing:-0.01em; }
header a { color:var(--fg); text-decoration:none; opacity:0.75; }
header a:hover { opacity:1; text-decoration:underline; }
main { max-width: 62rem; margin:0 auto; padding:1.5rem 1.25rem 4rem; }
h1 { font-size:1.5rem; margin:0 0 0.25rem; letter-spacing:-0.02em; }
h2 { font-size:1.05rem; margin:1.75rem 0 0.5rem; }
h3 { font-size:0.9rem; margin:0 0 0.4rem; }
.lede { color:var(--muted); margin:0 0 1rem; }
.provenance { font-size:0.85rem; color:var(--muted); }
table { border-collapse:collapse; width:100%; font-size:0.9rem; }
th, td { text-align:left; padding:0.35rem 0.6rem; border-bottom:1px solid var(--line);
         vertical-align:top; }
th { font-weight:600; color:var(--muted); width:16rem; }
table.list th { width:auto; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size:0.88em; }
a { color:var(--accent); }
.controls { display:flex; gap:1.25rem; flex-wrap:wrap; align-items:end;
            padding:1rem; border:1px solid var(--line); border-radius:8px; margin-bottom:1.25rem; }
.controls label { display:flex; flex-direction:column; gap:0.25rem; font-size:0.85rem;
                  color:var(--muted); }
.controls input[type=range] { width:16rem; }
.controls select, .controls input[type=number] { padding:0.3rem; background:var(--bg);
    color:var(--fg); border:1px solid var(--line); border-radius:4px; }
.value { font-variant-numeric: tabular-nums; font-weight:600; color:var(--fg); font-size:1rem; }
.notes { margin-top:1.25rem; padding:0.75rem 1rem; background:var(--warn-bg);
         border-left:3px solid var(--warn); border-radius:0 6px 6px 0; }
.notes h3 { color:var(--warn); text-transform:uppercase; letter-spacing:0.04em;
            font-size:0.7rem; }
.notes ul { margin:0; padding-left:1.1rem; font-size:0.85rem; }
.notes li { margin-bottom:0.4rem; }
.error { color:var(--warn); font-weight:600; }
svg { max-width:100%; height:auto; margin:1rem 0; }
footer { color:var(--muted); font-size:0.8rem; border-top:1px solid var(--line);
         padding:1rem 1.25rem; }
"""

_SHELL = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — jansky-forge</title><style>{css}</style></head>
<body>
<header>
  <span class="brand">jansky-forge</span>
  <a href="/">Catalog</a>
  <a href="/design">Design</a>
  <a href="/feed">Feed matching</a>
  <a href="/api-docs">API</a>
</header>
<main>{body}</main>
<footer>
  Predicted values are model output. Measure the antenna you build — see the
  <code>measure</code> and <code>onsky</code> modules — and never let a prediction and a
  measurement wear the same label.
</footer>
</body></html>
"""


def page(title: str, body: str) -> str:
    """Wrap a body in the site shell."""
    return _SHELL.format(title=title, css=_CSS, body=body)


CATALOG_PAGE = """
<h1>Known builds</h1>
<p class="lede">Nobody should start from a blank sheet. Every entry states where its geometry
came from, and what is uncertain about it.</p>
<table class="list">
<thead><tr><th>Slug</th><th>Name</th><th>Kind</th><th>Gain</th><th>Beamwidth</th><th></th></tr></thead>
<tbody>{rows}</tbody></table>
"""

DESIGN_PAGE = """
<h1>Design a horn</h1>
<p class="lede">Drag the gain and watch the metal change. Synthesis takes about a tenth of a
millisecond, so this is genuinely live — the delay you feel is the network, not the physics.</p>
<form class="controls" id="controls" onsubmit="return false">
  <label>Target gain
    <input type="range" name="gain_dbi" id="gain" min="8" max="26" step="0.1" value="18">
    <span class="value" id="gain-value">18.0 dBi</span>
  </label>
  <label>Band <select name="band" id="band">{bands}</select></label>
  <label>Shape <select name="shape" id="shape">
    <option value="pyramidal" selected>Pyramidal</option>
    <option value="conical">Conical</option>
  </select></label>
  <label>Waveguide <select name="waveguide" id="waveguide">{waveguides}</select></label>
</form>
<div id="result">{initial}</div>
<script>
(function () {{
  const out = document.getElementById('result');
  const gain = document.getElementById('gain');
  const label = document.getElementById('gain-value');
  let pending = null;
  async function refresh() {{
    label.textContent = Number(gain.value).toFixed(1) + ' dBi';
    const params = new URLSearchParams({{
      gain_dbi: gain.value,
      band: document.getElementById('band').value,
      shape: document.getElementById('shape').value,
      waveguide: document.getElementById('waveguide').value,
    }});
    try {{
      const response = await fetch('/design/compute?' + params);
      out.innerHTML = await response.text();
    }} catch (error) {{
      out.innerHTML = '<p class="error">Could not reach the server.</p>';
    }}
  }}
  function schedule() {{
    // Coalesce rapid slider movement into one request per frame's worth of dragging.
    clearTimeout(pending);
    pending = setTimeout(refresh, 60);
  }}
  document.getElementById('controls').addEventListener('input', schedule);
  document.getElementById('controls').addEventListener('change', schedule);
}})();
</script>
"""

DESIGN_RESULT = """
<h2>{summary}</h2>
<table>{table}</table>
{plot}
{notes}
"""
