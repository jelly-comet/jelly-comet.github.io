#!/usr/bin/python3
"""Generates the site from the public <Name>-release repositories on GitHub.

Every public repository of OWNER named <Name>-release with a published release becomes a plugin:
a card on index.html and a page in plugins/<name>/ with its README, release notes, images and a
PDF of its manual, which is also a page of its own in plugins/<name>/manual/. Beside the pages it
writes what a crawler reads: sitemap.xml, robots.txt, 404.html and plugins/index.html. There is
nothing to configure: run it after a release and commit the result. A release repository's optional
site.toml gives its page a search title, a tagline and a meta description.

    ./build.py                      from the release repositories as they are on GitHub
    ./build.py --local ../releases  from the checkouts in that folder, to look before they are pushed

A plugin whose README has a Discontinued notice right under its title (discontinue-plugin.md in
FrameworkBtw), or whose repository is archived, is left off: no card and no page (owner,
2026-11-13).
"""

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
from datetime import datetime
from pathlib import Path

import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

OWNER = "jelly-comet"
SITE_URL = f"https://{OWNER}.github.io"
ROOT = Path(__file__).resolve().parent
CACHE = ROOT / ".cache"
PLUGINS = ROOT / "plugins"
HASHES = ROOT / ".manual-hashes.json"
# --local: a folder of <Name>-release checkouts read in place of the clones from GitHub.
LOCAL = None
# What a release repository's site.toml may set, all optional: the search title after the name
# ("JellyPitchBtw – <title>"), the line under the name in the page's heading, the meta description.
SITE_FIELDS = ("title", "tagline", "description")
# The share picture of the pages that have no screenshot of their own.
SHARE = {
    "url": f"{SITE_URL}/assets/share.png",
    "width": 1200,
    "height": 630,
    "alt": "The JellyComet logo, a jellyfish with a comet's tail, and the words: Audio plugins for Linux",
}
ORGANIZATION = {
    "@type": "Organization",
    "@id": f"{SITE_URL}/#organization",
    "name": "JellyComet",
    "url": f"{SITE_URL}/",
    "logo": f"{SITE_URL}/assets/logo-mark.svg",
    "sameAs": [f"https://github.com/{OWNER}"],
}

# Source repositories are private: nothing on the site may link one (release-repo.md in FrameworkBtw).
PRIVATE_LINK = re.compile(rf"{OWNER}/[A-Za-z]+Btw([^-\w]|$)|FrameworkBtw", re.M)
# The README's formats line, "CLAP and VST3 for Linux." before 2026-11-06, "CLAP for Linux." since.
# A README wraps its lines where it likes, so any whitespace separates the words.
FORMATS_LINE = re.compile(r"\s*(CLAP(?:\s+and\s+VST3)?)\s+for\s+Linux\.\s*$")
# The account's earlier name in a link, with or without a path after it.
OLD_ACCOUNT = re.compile(r"github\.com/rmnhofma(?![\w-])")
IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
LINK_ATTR = re.compile(r'(href|src)="([^"]*)"')
TAG = re.compile(r"<[^>]+>")
DISCONTINUED = re.compile(r"^> \*\*Discontinued\b")

env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]))
# The stylesheet's and the lightbox script's links carry a hash of the file, so a browser fetches the new one when it changes
# instead of laying out new pages with the cached old one (GitHub Pages lets it keep it 10 minutes).
env.globals["css_version"] = hashlib.sha256((ROOT / "assets" / "site.css").read_bytes()).hexdigest()[:10]
env.globals["js_version"] = hashlib.sha256((ROOT / "assets" / "lightbox.js").read_bytes()).hexdigest()[:10]


def github_token():
    if token := os.environ.get("GITHUB_TOKEN"):
        return token
    if shutil.which("gh"):
        done = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
        return done.stdout.strip() if done.returncode == 0 else None
    return None


TOKEN = github_token()


def api(path):
    """A GET on the GitHub API; the token only lifts the rate limit, everything read is public."""
    request = urllib.request.Request(f"https://api.github.com/{path}")
    request.add_header("Accept", "application/vnd.github+json")
    if TOKEN:
        request.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def checkout(repo):
    """The repository's default branch as it is on GitHub, in a shallow clone under .cache/;
    with --local, the checkout of that name as it lies there."""
    if LOCAL and (LOCAL / repo["name"]).is_dir():
        print(f"  {repo['name']}: from {LOCAL / repo['name']}")
        return LOCAL / repo["name"]
    path = CACHE / repo["name"]
    branch = repo["default_branch"]
    if path.exists():
        subprocess.run(["git", "-C", path, "fetch", "-q", "--depth", "1", "origin", branch], check=True)
        subprocess.run(["git", "-C", path, "reset", "-q", "--hard", "FETCH_HEAD"], check=True)
    else:
        CACHE.mkdir(exist_ok=True)
        subprocess.run(
            ["git", "clone", "-q", "--depth", "1", "--branch", branch, repo["clone_url"], path], check=True
        )
    return path


def render_markdown(text):
    # The account was rmnhofma until 2026-11-13; archived release repositories and old release
    # notes still say so, and rmnhofma.github.io no longer exists.
    text = OLD_ACCOUNT.sub(f"github.com/{OWNER}", text.replace("rmnhofma.github.io", "jelly-comet.github.io"))
    md = markdown.Markdown(
        extensions=["fenced_code", "tables", "sane_lists", "toc"], extension_configs={"toc": {"toc_depth": "2-2"}}
    )
    return md.convert(text), md.toc


def rewrite_links(rendered, rewrite):
    """Applies rewrite(target) to every relative link and image in rendered HTML."""

    def replace(match):
        attr, target = match.group(1), html.unescape(match.group(2))
        if re.match(r"[a-z]+:|#", target):
            return match.group(0)
        return f'{attr}="{html.escape(rewrite(target))}"'

    return LINK_ATTR.sub(replace, rendered)


def repo_link(repo, target):
    return f"{repo['html_url']}/blob/{repo['default_branch']}/{target}"


def page_link(repo, name, target):
    """A README's relative link, seen from the plugin's page."""
    if target.startswith("manual.md"):
        return "manual/" + target.removeprefix("manual.md")
    if target.startswith("README.md"):
        return target.removeprefix("README.md") or "./"
    if target.startswith("images/"):
        return target
    return repo_link(repo, target)


def manual_link(repo, name, target):
    """A manual's relative link, seen from the PDF: images stay files, the rest must work anywhere."""
    if target.startswith("images/"):
        return target
    if target.startswith("README.md"):
        return f"{SITE_URL}/plugins/{name.lower()}/" + target.removeprefix("README.md")
    return repo_link(repo, target)


def web_manual_link(repo, target):
    """A manual's relative link, seen from its page, one folder below the plugin's."""
    if target.startswith("images/"):
        return f"../{target}"
    if target.startswith("README.md"):
        return "../" + target.removeprefix("README.md")
    if target.startswith("manual.md"):
        return target.removeprefix("manual.md") or "./"
    return repo_link(repo, target)


def one_line(text):
    return " ".join(text.split())


def lower_first(text):
    """A tagline inside a sentence: "Vocal pitch" to "vocal pitch", "MIDI scales" as it is."""
    return text[:1].lower() + text[1:] if text[1:2].islower() else text


def json_ld(*things):
    """Structured data for a page's head, one thing or several."""
    data = {"@context": "https://schema.org", **things[0]} if len(things) == 1 else {
        "@context": "https://schema.org",
        "@graph": list(things),
    }
    return Markup(json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/"))


def read_site(source, name):
    """A release repository's site.toml: the page's search title, tagline and meta description."""
    path = source / "site.toml"
    if not path.exists():
        return {}
    site = tomllib.loads(path.read_text())
    if unknown := sorted(set(site) - set(SITE_FIELDS)):
        sys.exit(f"{name}: site.toml has {', '.join(unknown)}; it knows {', '.join(SITE_FIELDS)}")
    for field, value in site.items():
        if not isinstance(value, str) or not value.strip():
            sys.exit(f"{name}: site.toml's {field} must be a line of text")
    site = {field: one_line(value) for field, value in site.items()}
    if len(site.get("description", "")) > 160:
        print(f"  warning: {name}'s site.toml description is {len(site['description'])} characters, a search result shows about 160")
    return site


def image_size(path):
    with open(path, "rb") as file:
        header = file.read(24)
    return struct.unpack(">II", header[16:24]) if header[:4] == b"\x89PNG" else (None, None)


def parse_readme(text, name):
    """Splits a README into what the page's top shows (summary, main image) and the rest."""
    lines = text.split("\n")
    if not lines[0].startswith("# "):
        sys.exit(f"{name}: the README doesn't start with '# {name}'")
    rest = "\n".join(lines[1:]).strip()
    notice = None
    if DISCONTINUED.match(rest):
        quote, _, rest = rest.partition("\n\n")
        notice, _ = render_markdown(re.sub(r"^> ?", "", quote, flags=re.M))
        notice = re.sub(r"^<p>|</p>$", "", notice)
        notice = re.sub(r"^<strong>Discontinued</strong>[:.]?\s*", "", notice)
    first, _, rest = rest.partition("\n\n")
    formats = FORMATS_LINE.search(first)
    summary_html, _ = render_markdown(FORMATS_LINE.sub("", first))
    summary_html = re.sub(r"^<p>|</p>$", "", summary_html)
    image = IMAGE.search(rest)
    if not image:
        sys.exit(f"{name}: the README has no screenshot")
    body = rest[: image.start()] + rest[image.end() :]
    return {
        "summary": summary_html,
        "formats": one_line(formats.group(1)) if formats else "CLAP",
        "notice": notice,
        "alt": image.group(1),
        "image": image.group(2),
        "body": body.strip(),
    }


def parse_notes(body, repo):
    """A release's notes, without what the page already has: the install paragraph every release
    repeats and a discontinued plugin's notice."""
    paragraphs = [
        p for p in (body or "").strip().split("\n\n") if not (p.startswith("Install:") or DISCONTINUED.match(p))
    ]
    notes = "\n\n".join(paragraphs).replace("github.com/PluginsBTW/", f"github.com/{OWNER}/")
    rendered, _ = render_markdown(notes)
    return rendered


def parse_release(release, repo):
    published = datetime.fromisoformat(release["published_at"].replace("Z", "+00:00"))
    assets = {asset["name"]: asset for asset in release["assets"]}
    archive = next((asset for n, asset in assets.items() if n.endswith(".tar.gz")), None)
    checksum = assets.get(f"{archive['name']}.sha256") if archive else None
    return {
        "version": release["tag_name"],
        "published": published,
        "day": published.date().isoformat(),
        "date": f"{published.day} {published:%b %Y}",
        "url": release["html_url"],
        "notes": Markup(parse_notes(release["body"], repo)),
        "download": archive["browser_download_url"] if archive else release["html_url"],
        "size": f"{archive['size'] / 1_000_000:.1f} MB" if archive else None,
        "checksum": checksum["browser_download_url"] if checksum else None,
    }


def gallery(manual, source, main_image):
    """The manual's other screenshots, once each."""
    seen = {main_image}
    shots = []
    for alt, target in IMAGE.findall(manual):
        if target not in seen and (source / target).exists():
            seen.add(target)
            width, height = image_size(source / target)
            shots.append({"src": target, "alt": alt, "width": width, "height": height})
    return shots


def collect(repo):
    name = repo["name"].removesuffix("-release")
    releases = [r for r in api(f"repos/{repo['full_name']}/releases?per_page=100") if not (r["draft"] or r["prerelease"])]
    if not releases:
        print(f"  {name}: skipped, no published release yet")
        return None
    source = checkout(repo)
    readme = parse_readme((source / "README.md").read_text(), name)
    if repo["archived"] or readme["notice"] is not None:
        print(f"  {name}: skipped, discontinued")
        return None
    site = read_site(source, name)
    if missing := [field for field in SITE_FIELDS if field not in site]:
        print(f"  note: {name} has no {', '.join(missing)} in a site.toml: its page's search text comes from the README")
    manual = (source / "manual.md").read_text()
    width, height = image_size(source / readme["image"])
    parsed = [parse_release(r, repo) for r in releases]
    latest = parsed[0]
    if latest["version"].lstrip("v") not in (source / "README.md").read_text():
        print(f"  warning: {name}'s README doesn't mention its latest version, {latest['version']}")
    slug = name.lower()
    url = f"{SITE_URL}/plugins/{slug}/"
    # A README's paragraph that opens with a link to this page is for a reader on GitHub: here it would point at itself.
    own_page = re.compile(rf"\*{{0,2}}\[[^\]]*\]\({re.escape(url)}?\)")
    paragraphs = [p for p in readme["body"].split("\n\n") if not own_page.match(p)]
    body, _ = render_markdown("\n\n".join(paragraphs))
    body = rewrite_links(body, lambda t: page_link(repo, name, t))
    # The screenshots go after the README's opening paragraphs, before its first section (Features).
    cut = body.find("<h2")
    intro, sections = (body[:cut], body[cut:]) if cut >= 0 else (body, "")
    description = site.get("description") or one_line(html.unescape(TAG.sub("", readme["summary"])))
    tagline = site.get("tagline")
    return {
        "name": name,
        "slug": slug,
        "url": url,
        "repo": repo,
        "source": source,
        "summary": Markup(readme["summary"]),
        "formats": readme["formats"],
        "title": f"{name} – {site['title']}" if "title" in site else name,
        "tagline": tagline,
        "description": description,
        "manual_description": f"The {name} manual: every control and how to use it. {name} is a free "
        + (f"CLAP plugin: {lower_first(tagline)}." if tagline else "CLAP plugin for Linux."),
        "share": {"url": f"{url}{readme['image']}", "width": width, "height": height, "alt": readme["alt"]},
        "structured": json_ld(
            {
                "@type": "SoftwareApplication",
                "name": name,
                "description": description,
                "url": url,
                "applicationCategory": "MultimediaApplication",
                "operatingSystem": "Linux",
                "softwareVersion": latest["version"].lstrip("v"),
                "datePublished": latest["day"],
                "downloadUrl": latest["download"],
                "screenshot": f"{url}{readme['image']}",
                "softwareHelp": {"@type": "CreativeWork", "url": f"{url}manual/"},
                "license": repo_link(repo, "LICENSE"),
                "isAccessibleForFree": True,
                "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
                "author": {"@type": "Organization", "name": "JellyComet", "url": f"{SITE_URL}/"},
            }
        ),
        "image": readme["image"],
        "alt": readme["alt"],
        "width": width,
        "height": height,
        "intro": Markup(intro),
        "sections": Markup(sections),
        "manual": manual,
        "gallery": gallery(manual, source, readme["image"]),
        "pdf": f"{name}-manual.pdf",
        "latest": latest,
        "earlier": parsed[1:],
    }


def write_checked(path, content):
    if match := PRIVATE_LINK.search(content):
        sys.exit(f"{path}: links something private: {match.group(0)!r}")
    path.write_text(content)


def build_manual(plugin, out, hashes):
    """manual.md to a PDF with Chromium, redone only when its inputs changed: a PDF differs per run."""
    name, source = plugin["name"], plugin["source"]
    body, toc = render_markdown(plugin["manual"])
    body = rewrite_links(body, lambda t: manual_link(plugin["repo"], name, t))
    body = body.replace("<h2", toc + "<h2", 1)
    page = env.get_template("manual.html").render(
        title=f"{name} manual",
        body=Markup(body),
        css=Markup((ROOT / "templates" / "manual.css").read_text()),
        logo=(ROOT / "assets" / "logo-mark.svg").as_uri(),
        font=(ROOT / "assets" / "fonts" / "Ubuntu-Light.ttf").as_uri(),
    )
    if match := PRIVATE_LINK.search(page):
        sys.exit(f"{name}'s manual links something private: {match.group(0)!r}")

    digest = hashlib.sha256(page.encode())
    digest.update((ROOT / "assets" / "logo-mark.svg").read_bytes())
    for image in sorted((source / "images").iterdir()):
        digest.update(image.read_bytes())
    digest = digest.hexdigest()
    pdf = out / plugin["pdf"]
    if hashes.get(name) == digest and pdf.exists():
        return
    print(f"  {name}: printing the manual")
    # In the clone, so that images and the table of contents' anchors resolve.
    temporary = source / ".manual.html"
    temporary.write_text(page)
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            [
                "chromium",
                "--headless=new",
                "--disable-gpu",
                f"--user-data-dir={profile}",
                "--no-pdf-header-footer",
                "--generate-pdf-document-outline",
                f"--print-to-pdf={pdf}",
                temporary.as_uri(),
            ],
            check=True,
            capture_output=True,
        )
    temporary.unlink()
    hashes[name] = digest


def render(path, template, root, page_url=None, **context):
    """A page from its template. page_url is its address for search engines; a page without one
    (the 404) asks them to leave it out."""
    page = env.get_template(template).render(root=root, site_url=SITE_URL, owner=OWNER, page_url=page_url, **context)
    write_checked(path, page)


def build_manual_page(plugin, out):
    """manual.md as a page of the site, plugins/<name>/manual/: the same text as the PDF, for reading
    in a browser and for a search engine."""
    body, toc = render_markdown(plugin["manual"])
    body = rewrite_links(body, lambda t: web_manual_link(plugin["repo"], t))
    heading, end, rest = body.partition("</h1>")
    if not end:
        sys.exit(f"{plugin['name']}: manual.md doesn't start with a '# ' title")
    # A manual without a Contents section of its own gets the one the PDF has.
    if 'id="contents"' not in rest:
        rest = rest.replace("<h2", toc + "<h2", 1)
    (out / "manual").mkdir(exist_ok=True)
    render(
        out / "manual" / "index.html",
        "manual-page.html",
        "../../../",
        f"{plugin['url']}manual/",
        plugin=plugin,
        share=plugin["share"],
        heading=Markup(heading + end),
        body=Markup(rest),
    )


def build_plugin(plugin, others, hashes):
    out = PLUGINS / plugin["slug"]
    out.mkdir(parents=True, exist_ok=True)
    images = out / "images"
    if images.exists():
        shutil.rmtree(images)
    shutil.copytree(plugin["source"] / "images", images)
    build_manual(plugin, out, hashes)
    build_manual_page(plugin, out)
    render(
        out / "index.html",
        "plugin.html",
        "../../",
        plugin["url"],
        plugin=plugin,
        others=others,
        share=plugin["share"],
        structured=plugin["structured"],
    )


def sitemap(plugins):
    """Every page with the day it last changed: a plugin's with its latest release, the front page
    with the newest of them."""
    pages = [(f"{SITE_URL}/", max(plugin["latest"]["day"] for plugin in plugins))] if plugins else []
    for plugin in plugins:
        pages.append((plugin["url"], plugin["latest"]["day"]))
        pages.append((f"{plugin['url']}manual/", plugin["latest"]["day"]))
    urls = "".join(f"  <url><loc>{html.escape(loc)}</loc><lastmod>{day}</lastmod></url>\n" for loc, day in pages)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}</urlset>\n'


def main():
    global LOCAL
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--local",
        metavar="FOLDER",
        type=Path,
        help="read README, manual, images and site.toml from the <Name>-release checkouts in FOLDER, "
        "to look at a change before it is pushed; build again without it before committing the site",
    )
    LOCAL = parser.parse_args().local
    if LOCAL and not LOCAL.is_dir():
        sys.exit(f"{LOCAL} is not a folder")
    LOCAL = LOCAL.resolve() if LOCAL else None

    repos = api(f"users/{OWNER}/repos?per_page=100&type=owner")
    repos = [r for r in repos if r["name"].endswith("-release") and not r["private"]]
    print(f"{len(repos)} release repositories")
    plugins = [plugin for repo in repos if (plugin := collect(repo))]
    plugins.sort(key=lambda plugin: plugin["latest"]["published"], reverse=True)

    hashes = json.loads(HASHES.read_text()) if HASHES.exists() else {}
    for plugin in plugins:
        build_plugin(plugin, [other for other in plugins if other is not plugin], hashes)
    current = {plugin["slug"] for plugin in plugins}
    if PLUGINS.exists():
        for old in PLUGINS.iterdir():
            if old.is_dir() and old.name not in current:
                print(f"  removing {old.name}: discontinued, or its repository is gone or has no release")
                shutil.rmtree(old)
    hashes = {plugin["name"]: hashes[plugin["name"]] for plugin in plugins}
    HASHES.write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n")
    home = f"{SITE_URL}/"
    render(
        ROOT / "index.html",
        "index.html",
        "",
        home,
        plugins=plugins,
        share=SHARE,
        structured=json_ld(
            ORGANIZATION,
            {"@type": "WebSite", "name": "JellyComet", "url": home, "publisher": {"@id": ORGANIZATION["@id"]}},
        ),
    )
    # /plugins/ has no page of its own: it sends a visitor, and a search engine, to the front page.
    PLUGINS.mkdir(exist_ok=True)
    render(PLUGINS / "index.html", "moved.html", "../", home, share=SHARE)
    # GitHub Pages serves 404.html for every address that has no file, wherever it is: its links start at the root.
    render(ROOT / "404.html", "404.html", "/", plugins=plugins)
    write_checked(ROOT / "sitemap.xml", sitemap(plugins))
    write_checked(ROOT / "robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n")
    for plugin in plugins:
        print(f"  {plugin['name']} {plugin['latest']['version']} ({plugin['latest']['date']})")
    if LOCAL:
        print(f"Built from the checkouts in {LOCAL}: push them and build again without --local before committing.")


if __name__ == "__main__":
    main()
