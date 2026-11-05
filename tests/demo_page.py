"""Render tests/demo.ipynb into one self-contained, phone-friendly HTML page.

Run from the repository root:
    python tests/demo_page.py tests/demo.ipynb notes.md page.html

notes.md is a short "latest changes" note shown above the contents. Relative links in the notebook
point at files next to it, which a page on its own cannot open, so they are rewritten to the same
file on GitHub.
"""
import datetime, html, os, re, subprocess, sys
import mistune, nbformat

NB, PROGRESS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
REPO = "https://github.com/figlerg/roadlogic/blob/feature/keep/"
NB_DIR = os.path.relpath(os.path.dirname(os.path.abspath(NB)))


def github_links(text):
    """Point relative hrefs at GitHub, resolved against the notebook's folder."""
    def rewrite(m):
        href = m.group(1)
        if re.match(r"[a-z]+:|#", href):
            return m.group(0)
        return f'href="{REPO}{os.path.normpath(os.path.join(NB_DIR, href))}"'
    return re.sub(r'href="([^"]*)"', rewrite, text)

md = mistune.create_markdown(plugins=["table"], escape=False)

nb = nbformat.read(NB, as_version=4)
commit = subprocess.run(["git", "log", "-1", "--format=%h %s"], capture_output=True, text=True).stdout.strip()
stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

toc, body = [], []

def render_markdown(text, first):
    if first:
        text = re.sub(r"^# .*\n", "", text)
    out = md(text)
    def heading(m):
        title = re.sub("<[^>]+>", "", m.group(1))
        num = re.match(r"(\d+[a-z]?)\.", title)
        anchor = f"s{num.group(1)}" if num else "continue"
        toc.append((anchor, title))
        return f'<h2 id="{anchor}">{m.group(1)}</h2>'
    return github_links(re.sub(r"<h2>(.*?)</h2>", heading, out))

def render_output(o):
    if o.output_type == "stream":
        return f'<pre class="stream">{html.escape(o.text)}</pre>'
    data = o.get("data", {})
    if "text/html" in data:
        h = re.sub(r"<style scoped>.*?</style>", "", data["text/html"], flags=re.S)
        cls = "frame" if "dataframe" in h else "media"
        return f'<div class="{cls}">{github_links(h)}</div>'
    if "image/png" in data:
        return f'<div class="media"><img alt="figure" src="data:image/png;base64,{data["image/png"]}"></div>'
    if "text/plain" in data:
        text = data["text/plain"]
        if text.startswith("<Figure"):
            return ""
        return f'<pre class="stream">{html.escape(text)}</pre>'
    return ""

first = True
for cell in nb.cells:
    if cell.cell_type == "markdown":
        body.append(f'<div class="prose">{render_markdown(cell.source, first)}</div>')
        first = False
    elif cell.cell_type == "code":
        outputs = "".join(render_output(o) for o in cell.get("outputs", []))
        body.append(f'<details class="code"><summary>Code</summary><pre><code>{html.escape(cell.source)}</code></pre></details>')
        if outputs:
            body.append(f'<div class="outputs">{outputs}</div>')

progress = md(open(PROGRESS).read())
toc_html = "".join(f'<li><a href="#{a}">{html.escape(t)}</a></li>' for a, t in toc)

page = f"""<title>RoadLogic Journal Demo</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+Condensed:wght@500;600&family=IBM+Plex+Sans:ital,wght@0,400;0,600;1,400&display=swap">
<style>
/* Layout: one reading column, code folded away, outputs and media given the full column width. */
:root {{
  --bg: #f5f6f7; --surface: #ffffff; --fg: #1c2228; --muted: #5a6570;
  --line: #d7dce1; --accent: #9a5b00; --lane: #e8a317; --code-bg: #eceff2;
  --good: #1f7a3d; --bad: #b3261e;
  --display: "IBM Plex Sans Condensed", "Arial Narrow", system-ui, sans-serif;
  --body: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #14181c; --surface: #1b2026; --fg: #e2e6ea; --muted: #9aa5af;
  --line: #2d343b; --accent: #f0b24a; --lane: #e8a317; --code-bg: #1f252b;
  --good: #6cc98a; --bad: #f08a80; color-scheme: dark; }} }}
:root[data-theme="dark"] {{
  --bg: #14181c; --surface: #1b2026; --fg: #e2e6ea; --muted: #9aa5af;
  --line: #2d343b; --accent: #f0b24a; --lane: #e8a317; --code-bg: #1f252b;
  --good: #6cc98a; --bad: #f08a80; color-scheme: dark; }}
body {{ background: var(--bg); color: var(--fg); font: 16px/1.55 var(--body); }}
.wrap {{ max-width: 880px; margin: 0 auto; padding-block: 24px 64px;
  padding-left: max(16px, env(safe-area-inset-left, 0px));
  padding-right: max(16px, env(safe-area-inset-right, 0px)); display: grid; gap: 18px; }}
.wrap > * {{ min-width: 0; }}
header .eyebrow {{ margin: 0; font: 500 12px/1.4 var(--mono); letter-spacing: .08em;
  text-transform: uppercase; color: var(--muted); }}
header h1 {{ margin: 6px 0 4px; font: 600 clamp(26px, 6vw, 36px)/1.15 var(--display);
  text-wrap: balance; padding-bottom: 10px;
  border-bottom: 4px dashed var(--lane); }}
header .meta {{ margin: 0; color: var(--muted); font: 13px/1.5 var(--mono); }}
.progress {{ background: var(--surface); border: 1px solid var(--line); border-left: 4px solid var(--lane);
  border-radius: 6px; padding: 14px 16px; }}
.progress h2 {{ margin: 0 0 6px; font: 600 18px/1.3 var(--display); }}
.progress p {{ margin: 6px 0; }}
nav.toc ol {{ margin: 0; padding-left: 22px; columns: 2 260px; column-gap: 28px; font-size: 14px; }}
nav.toc li {{ break-inside: avoid; margin: 2px 0; }}
a {{ color: var(--accent); }}
.prose h2 {{ font: 600 22px/1.25 var(--display); margin: 26px 0 8px; text-wrap: balance;
  padding-top: 14px; border-top: 1px solid var(--line); scroll-margin-top: 16px; }}
.prose h3 {{ font: 600 17px/1.3 var(--display); margin: 18px 0 6px; }}
.prose p, .prose li {{ max-width: 68ch; }}
.prose table {{ border-collapse: collapse; font-size: 14px; display: block; overflow-x: auto; }}
.prose th, .prose td {{ border: 1px solid var(--line); padding: 6px 10px; text-align: left; vertical-align: top; }}
code {{ font-family: var(--mono); font-size: .88em; background: var(--code-bg); padding: 1px 4px; border-radius: 3px; }}
pre {{ margin: 0; overflow-x: auto; background: var(--code-bg); border-radius: 6px; padding: 10px 12px;
  font: 12.5px/1.45 var(--mono); }}
pre code {{ background: none; padding: 0; font-size: inherit; }}
details.code summary {{ cursor: pointer; font: 500 12px/1.4 var(--mono); color: var(--muted);
  letter-spacing: .06em; text-transform: uppercase; padding: 2px 0; }}
details.code summary:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
details.code[open] summary {{ margin-bottom: 6px; }}
.outputs {{ display: grid; gap: 10px; }}
.outputs > * {{ min-width: 0; }}
pre.stream {{ background: var(--surface); border: 1px solid var(--line); }}
.frame {{ overflow-x: auto; }}
.frame table {{ border-collapse: collapse; font: 13px/1.4 var(--mono); font-variant-numeric: tabular-nums; }}
.frame th, .frame td {{ border: 1px solid var(--line); padding: 4px 8px; text-align: left; }}
.frame thead th {{ background: var(--code-bg); }}
.media img {{ max-width: 100%; height: auto; border-radius: 4px; border: 1px solid var(--line); background: #fff; }}
.media table {{ border-collapse: collapse; width: 100%; }}
.media td {{ padding: 0 8px 8px 0; vertical-align: top; color: var(--fg); }}
.media td b {{ font: 600 13px/1.4 var(--body); }}
.media details summary, .media .box-title {{ font: 500 13px/1.4 var(--mono); color: var(--muted); cursor: pointer; }}
.media .box pre {{ background: var(--surface); border: 1px solid var(--line); }}
@media (max-width: 720px) {{ .media td {{ display: block; padding-right: 0; }} }}
</style>
<div class="wrap">
<header>
  <p class="eyebrow">feature/keep · demo notebook</p>
  <h1>RoadLogic, journal version</h1>
  <p class="meta">Updated {stamp} · last commit {html.escape(commit)}</p>
</header>
<section class="progress" aria-label="Latest changes">
  <h2>Latest changes</h2>
  {progress}
</section>
<nav class="toc" aria-label="Sections"><ol>{toc_html}</ol></nav>
{"".join(body)}
</div>
"""
open(OUT, "w").write(page)
print(f"wrote {OUT}, {len(page)/1e6:.2f} MB, {len(toc)} sections")
