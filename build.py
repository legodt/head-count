"""Produce both shippable builds.

    python build.py  ->  docs/                  the folder to deploy
                         dist/head-count.html   one file, opened from disk

`docs/` holds exactly the served build and nothing else - no source notes, no
tests, no build script - because everything in it becomes a public URL. It is
named `docs` rather than `site` because a GitHub Pages branch deploy will only
serve the repository root or `/docs`, and the root would expose this script and
the spec. Any drag-and-drop host takes the same folder under any name.

The single file is the other path: no server and no network. Service workers
cannot register on file://, so the manifest and worker are dropped from it
rather than left to fail.
"""

import base64
import pathlib
import re
import shutil
import sys

HERE = pathlib.Path(__file__).parent
OUT = HERE / "dist" / "head-count.html"
SITE = HERE / "docs"

# Exactly what the service worker caches, plus the worker itself.
SHIPPED = ["index.html", "styles.css", "app.js", "sw.js", "manifest.webmanifest"]


def read(name):
    return (HERE / name).read_text(encoding="utf-8")


def data_uri(name):
    raw = (HERE / name).read_bytes()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def build():
    html = read("index.html")
    css = read("styles.css")
    js = read("app.js")

    if "</script" in js or "</style" in css:
        sys.exit("refusing to inline: asset contains a closing tag that would break the document")

    html = html.replace(
        '<link rel="stylesheet" href="styles.css">',
        "<style>\n" + css.strip() + "\n</style>",
    )
    html = html.replace(
        '<script src="app.js"></script>',
        "<script>\n" + js.strip() + "\n</script>",
    )
    html = html.replace('<link rel="icon" href="icons/icon-192.png">',
                        '<link rel="icon" href="%s">' % data_uri("icons/icon-192.png"))

    # No server, so no worker and no installable manifest.
    html = re.sub(r'\s*<link rel="manifest"[^>]*>', "", html)
    html = re.sub(r'\s*<link rel="apple-touch-icon"[^>]*>', "", html)

    for leftover in ('href="styles.css"', 'src="app.js"', 'href="icons/'):
        if leftover in html:
            sys.exit("refusing to ship: %s was not inlined" % leftover)

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print("%s  (%.0f KB)" % (OUT, OUT.stat().st_size / 1024))


def site():
    """Assemble the deployable folder, then prune anything that is not part of
    this build - a renamed or deleted source file must not linger in docs/ and
    reappear on a public URL. Pruning rather than deleting the folder because
    rmtree is not reliable inside a synced directory like OneDrive."""
    (SITE / "icons").mkdir(parents=True, exist_ok=True)

    wanted = set()
    for name in SHIPPED:
        shutil.copy(HERE / name, SITE / name)
        wanted.add(SITE / name)
    for icon in sorted((HERE / "icons").glob("*.png")):
        shutil.copy(icon, SITE / "icons" / icon.name)
        wanted.add(SITE / "icons" / icon.name)

    # Serve the folder verbatim instead of running it through Jekyll.
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    wanted.add(SITE / ".nojekyll")

    for stale in SITE.rglob("*"):
        if stale.is_file() and stale not in wanted:
            stale.unlink()

    missing = [f for f in re.findall(r"'\./([^']+)'", read("sw.js")) if not (SITE / f).exists()]
    if missing:
        sys.exit("refusing to ship: sw.js caches %s, missing from docs/" % ", ".join(sorted(set(missing))))

    total = sum(f.stat().st_size for f in wanted)
    print("%s  (%d files, %.0f KB)" % (SITE, len(wanted), total / 1024))


if __name__ == "__main__":
    build()
    site()
