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
    "type": "image/png",
    "alt": "The JellyComet logo, a jellyfish with a comet's tail, and the words: Audio plugins for Linux",
}
# The screenshots' WebP copies: lossy at this quality, the windows' text and lines look the same as the PNG's.
WEBP_QUALITY = 88
# The width of the main screenshot's small copy: a card shows it at most 180 px wide, twice that on a sharp screen.
THUMB_WIDTH = 480
# The width of its middle copy: what a phone or a half-width panel loads in place of the full screenshot.
MID_WIDTH = 840
# A plugin's share picture (plugins/<name>/share.png): the size Slack, Discord, X and Mastodon show whole.
SHARE_SIZE = (1200, 630)
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
IMG_TAG = re.compile(r'<img\b[^>]*?\bsrc="([^"]+)"[^>]*?/?>')
LINK_ATTR = re.compile(r'(href|src)="([^"]*)"')
TAG = re.compile(r"<[^>]+>")
DISCONTINUED = re.compile(r"^> \*\*Discontinued\b")

env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]))
# The stylesheet's and the lightbox script's links carry a hash of the file, so a browser fetches the new one when it changes
# instead of laying out new pages with the cached old one (GitHub Pages lets it keep it 10 minutes).
env.globals["css_version"] = hashlib.sha256((ROOT / "assets" / "site.css").read_bytes()).hexdigest()[:10]
env.globals["js_version"] = hashlib.sha256((ROOT / "assets" / "lightbox.js").read_bytes()).hexdigest()[:10]
env.globals["site_js_version"] = hashlib.sha256((ROOT / "assets" / "site.js").read_bytes()).hexdigest()[:10]

# The site's own words about each plugin beyond its README (highlights.toml): its kind, colour and a few facts.
HIGHLIGHTS = tomllib.loads((ROOT / "highlights.toml").read_text())
HIGHLIGHT_FIELDS = ("kind", "short", "accent", "chips", "glance")
CHIP_ICONS = ("clock", "cpu", "spark", "keys", "loop", "mic", "shield")
# The accents of plugins highlights.toml doesn't colour, in turn.
ACCENTS = ("#6fd8ff", "#b49bff", "#ffc46b", "#6fe0b0", "#ff8577")
H2 = re.compile(r'<h2 id="([^"]+)">(.*?)</h2>', re.S)
H3 = re.compile(r"<h3[^>]*>(.*?)</h3>", re.S)
LEAD_ITEM = re.compile(r"<li>\s*<strong>(.*?)</strong>\s*(.*?)</li>", re.S)
ITEM = re.compile(r"<li>(.*?)</li>", re.S)
CLAP_FILE = re.compile(r"\bcp (\S+\.clap) ~/\.clap/")


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


def plain(rendered):
    """Rendered HTML as one line of plain text, for structured data."""
    return one_line(html.unescape(TAG.sub("", rendered)))


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


def read_highlights(name, index):
    """What highlights.toml says about a plugin; a plugin it doesn't name gets a colour and nothing else."""
    found = HIGHLIGHTS.get(name, {})
    if unknown := sorted(set(found) - set(HIGHLIGHT_FIELDS)):
        sys.exit(f"highlights.toml: {name} has {', '.join(unknown)}; it knows {', '.join(HIGHLIGHT_FIELDS)}")
    if not found:
        print(
            f"  note: {name} has no entry in highlights.toml: its page shows no kind and no facts beside its window, "
            f"and its colour is a stand-in ({ACCENTS[index % len(ACCENTS)]})"
        )
    chips = found.get("chips", [])
    if len(chips) > 3 or any(chip.get("icon") not in CHIP_ICONS or not chip.get("text") for chip in chips):
        sys.exit(f"highlights.toml: {name}'s chips must be at most three, each an icon of {', '.join(CHIP_ICONS)} and a text")
    if "accent" in found and not re.fullmatch(r"#[0-9a-fA-F]{6}", found["accent"]):
        sys.exit(f"highlights.toml: {name}'s accent must be a colour like #6fd8ff")
    for field in ("kind", "short"):
        if field in found and (not isinstance(found[field], str) or not found[field].strip()):
            sys.exit(f"highlights.toml: {name}'s {field} must be a line of text")
    if not all(isinstance(value, str) for value in found.get("glance", {}).values()):
        sys.exit(f"highlights.toml: {name}'s glance rows must be texts, like Latency = \"0.25 ms\"")
    return {
        "kind": found.get("kind"),
        "short": found.get("short"),
        "accent": found.get("accent", ACCENTS[index % len(ACCENTS)]),
        "chips": chips,
        "glance": found.get("glance", {}),
    }


def terminal(rendered):
    """A README's code blocks as small terminal windows, with a copy button site.js shows."""
    return rendered.replace(
        "<pre><code",
        '<div class="term"><div class="term-bar"><i></i><i></i><i></i><span class="term-name">bash</span>'
        '<button class="copy" type="button" hidden>Copy</button></div><pre><code',
    ).replace("</code></pre>", "</code></pre></div>")


def parts_of(sections):
    """The README's sections after its intro, each as the page shows it: What it's for as tiles,
    Features as a checklist, FAQ folded, Requirements in the side box, the rest as written."""
    found = list(H2.finditer(sections))
    parts = []
    for number, heading in enumerate(found):
        end = found[number + 1].start() if number + 1 < len(found) else len(sections)
        body = sections[heading.end() : end].strip()
        part = {"id": heading.group(1), "title": Markup(heading.group(2)), "kind": "prose", "html": Markup(terminal(body))}
        items = ITEM.findall(body)
        leads = LEAD_ITEM.findall(body)
        only_list = re.fullmatch(r"<ul>.*</ul>", body, re.S)
        if part["id"] == "what-its-for" and only_list and len(leads) == len(items):
            part["kind"] = "uses"
            # A tile's text stands alone under its label: "a slower SPEED" there reads "A slower SPEED".
            part["entries"] = [
                {"label": Markup(lead.rstrip(":")), "text": Markup(text[:1].upper() + text[1:])} for lead, text in leads
            ]
        elif part["id"] == "features" and only_list and len(leads) == len(items):
            part["kind"] = "features"
            part["entries"] = [{"lead": Markup(lead), "text": Markup(text)} for lead, text in leads]
        elif part["id"] == "faq" and body.startswith("<h3"):
            questions = list(H3.finditer(body))
            part["kind"] = "faq"
            part["entries"] = [
                {
                    "question": Markup(question.group(1)),
                    "answer": Markup(body[question.end() : questions[n + 1].start() if n + 1 < len(questions) else len(body)].strip()),
                }
                for n, question in enumerate(questions)
            ]
        elif part["id"] == "requirements" and body.startswith("<ul>"):
            ul_end = body.index("</ul>") + len("</ul>")
            part["kind"] = "requirements"
            part["entries"] = [Markup(item) for item in ITEM.findall(body[:ul_end])]
            part["note"] = Markup(body[ul_end:].strip())
        parts.append(part)
    return parts


def size_images(rendered, source):
    """Gives every picture in rendered Markdown its width and height, so the page doesn't jump while
    they load, and lets all but the first load when they come into view."""
    seen = 0

    def replace(match):
        nonlocal seen
        tag, target = match.group(0), html.unescape(match.group(1))
        path = source / target
        width, height = image_size(path) if path.is_file() else (None, None)
        extra = f' width="{width}" height="{height}"' if width else ""
        if seen:
            extra += ' loading="lazy"'
        seen += 1
        return re.sub(r"\s*/?>$", f"{extra}>", tag)

    return IMG_TAG.sub(replace, rendered)


def webp(src):
    """The WebP copy build_plugin makes beside every PNG of a plugin's images."""
    return re.sub(r"\.png$", ".webp", src)


def thumb(src):
    """The small WebP copy of a plugin's main screenshot, for the cards of the other plugins."""
    return re.sub(r"\.png$", f"-{THUMB_WIDTH}.webp", src)


def mid(src):
    """The middle WebP copy of a plugin's main screenshot, for a phone or a half-width panel."""
    return re.sub(r"\.png$", f"-{MID_WIDTH}.webp", src)


env.filters["webp"] = webp
env.filters["thumb"] = thumb
env.filters["mid"] = mid
env.globals["thumb_width"] = THUMB_WIDTH
env.globals["mid_width"] = MID_WIDTH


def pictures(rendered):
    """Wraps every PNG of the plugin's own images in rendered HTML in a <picture> with its WebP copy first:
    a browser that shows WebP loads that, about an eighth of the PNG."""

    def replace(match):
        tag, src = match.group(0), html.unescape(match.group(1))
        if re.match(r"[a-z]+:", src) or not src.endswith(".png"):
            return tag
        return f'<picture><source type="image/webp" srcset="{html.escape(webp(src))}">{tag}</picture>'

    return IMG_TAG.sub(replace, rendered)


def make_webp(images, main_image):
    """A WebP copy of every PNG in a plugin's images, and a small one of its main screenshot. The PNGs stay:
    the PDF, the share pictures and a browser without WebP use them. The same PNG gives the same file every run."""
    if not shutil.which("magick"):
        sys.exit("build.py needs ImageMagick's magick for the WebP copies of the screenshots")
    for png in sorted(images.rglob("*.png")):
        subprocess.run(
            ["magick", png, "-strip", "-quality", str(WEBP_QUALITY), "-define", "webp:method=6", png.with_suffix(".webp")],
            check=True,
        )
    main = images.parent / main_image
    for width, name in ((THUMB_WIDTH, thumb(main_image)), (MID_WIDTH, mid(main_image))):
        subprocess.run(
            ["magick", main, "-strip", "-resize", f"{width}x", "-quality", "82", "-define", "webp:method=6",
             images.parent / name],
            check=True,
        )


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
    body = pictures(rewrite_links(body, lambda t: page_link(repo, name, t)))
    # The screenshots go after the README's opening paragraphs, before its first section (Features).
    cut = body.find("<h2")
    intro, sections = (body[:cut], body[cut:]) if cut >= 0 else (body, "")
    description = site.get("description") or one_line(html.unescape(TAG.sub("", readme["summary"])))
    tagline = site.get("tagline")
    # The front page's install window: the archive, the folder it unpacks to and the file to copy.
    archive = latest["download"].rsplit("/", 1)[-1] if latest["download"].endswith(".tar.gz") else f"{name}.tar.gz"
    clap_file = CLAP_FILE.search(readme["body"])
    parts = parts_of(sections)
    features = next((part["entries"] for part in parts if part["kind"] == "features"), [])
    requirements = next((part["entries"] for part in parts if part["kind"] == "requirements"), [])
    software = {
        "@type": "SoftwareApplication",
        "@id": f"{url}#software",
        "name": name,
        "description": description,
        "url": url,
        "applicationCategory": "MultimediaApplication",
        "applicationSubCategory": "Audio plugin (CLAP)",
        "operatingSystem": "Linux",
        "softwareVersion": latest["version"].lstrip("v"),
        "datePublished": parsed[-1]["day"],
        "dateModified": latest["day"],
        "downloadUrl": latest["download"],
        "screenshot": f"{url}{readme['image']}",
        "image": f"{url}share.png",
        "softwareHelp": {"@type": "CreativeWork", "url": f"{url}manual/"},
        "license": repo_link(repo, "LICENSE"),
        "isAccessibleForFree": True,
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
        "author": ORGANIZATION,
        "publisher": {"@id": ORGANIZATION["@id"]},
    }
    if features:
        software["featureList"] = [plain(entry["lead"]).rstrip(":.,; ") for entry in features]
    if requirements:
        software["softwareRequirements"] = "; ".join(plain(entry).rstrip(". ") for entry in requirements)
    if latest["size"]:
        software["fileSize"] = latest["size"]
    if 'id="install"' in sections:
        software["installUrl"] = f"{url}#install"
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
        "share": {
            "url": f"{url}share.png",
            "width": SHARE_SIZE[0],
            "height": SHARE_SIZE[1],
            "type": "image/png",
            "alt": f"{name}, {lower_first(tagline) if tagline else 'a free CLAP plugin for Linux'}, beside its window",
        },
        "structured": json_ld(
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "JellyComet", "item": f"{SITE_URL}/"},
                    {"@type": "ListItem", "position": 2, "name": name},
                ],
            },
            software,
        ),
        "image": readme["image"],
        "alt": readme["alt"],
        "width": width,
        "height": height,
        "intro": Markup(intro),
        "sections": Markup(sections),
        "parts": parts,
        "install": {
            "archive": archive,
            "folder": archive.removesuffix(".tar.gz"),
            "clap": clap_file.group(1) if clap_file else f"{name}.clap",
        },
        "manual": manual,
        "gallery": gallery(manual, source, readme["image"]),
        "pdf": f"{name}-manual.pdf",
        "first_day": parsed[-1]["day"],
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


def build_share(plugin, out, hashes):
    """The plugin's share picture, plugins/<name>/share.png: its name, tagline and window on 1200 x 630,
    the shape a link preview shows whole (its screenshot alone is cropped there). Chromium draws
    templates/share.html; like the PDF, it is redone only when its inputs changed."""
    name, source = plugin["name"], plugin["source"]
    page = env.get_template("share.html").render(
        plugin=plugin,
        width=SHARE_SIZE[0],
        height=SHARE_SIZE[1],
        screenshot=(source / plugin["image"]).as_uri(),
        logo=(ROOT / "assets" / "logo-mark.svg").as_uri(),
        fonts=(ROOT / "assets" / "fonts").as_uri(),
    )
    digest = hashlib.sha256(page.encode())
    digest.update((source / plugin["image"]).read_bytes())
    digest = digest.hexdigest()
    share = out / "share.png"
    key = f"{name} share"
    if hashes.get(key) == digest and share.exists():
        return
    print(f"  {name}: drawing the share picture")
    temporary = source / ".share.html"
    temporary.write_text(page)
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            [
                "chromium",
                "--headless=new",
                "--disable-gpu",
                f"--user-data-dir={profile}",
                "--hide-scrollbars",
                f"--window-size={SHARE_SIZE[0]},{SHARE_SIZE[1]}",
                f"--screenshot={share}",
                temporary.as_uri(),
            ],
            check=True,
            capture_output=True,
        )
    temporary.unlink()
    hashes[key] = digest


def render(path, template, root, page_url=None, **context):
    """A page from its template. page_url is its address for search engines; a page without one
    (the 404) asks them to leave it out."""
    page = env.get_template(template).render(root=root, site_url=SITE_URL, owner=OWNER, page_url=page_url, **context)
    write_checked(path, page)


def build_manual_page(plugin, others, out):
    """manual.md as a page of the site, plugins/<name>/manual/: the same text as the PDF, for reading
    in a browser and for a search engine."""
    body, toc = render_markdown(plugin["manual"])
    body = size_images(body, plugin["source"])
    body = pictures(rewrite_links(body, lambda t: web_manual_link(plugin["repo"], t)))
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
        others=others,
        plugins_root="../../",
        share=plugin["share"],
        structured=json_ld(
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "JellyComet", "item": f"{SITE_URL}/"},
                    {"@type": "ListItem", "position": 2, "name": plugin["name"], "item": plugin["url"]},
                    {"@type": "ListItem", "position": 3, "name": "Manual"},
                ],
            },
            {
                "@type": "TechArticle",
                "headline": f"{plugin['name']} manual",
                "description": plugin["manual_description"],
                "url": f"{plugin['url']}manual/",
                "image": plugin["share"]["url"],
                "datePublished": plugin["first_day"],
                "dateModified": plugin["latest"]["day"],
                "mainEntityOfPage": f"{plugin['url']}manual/",
                "author": {"@id": ORGANIZATION["@id"]},
                "about": {"@type": "SoftwareApplication", "@id": f"{plugin['url']}#software", "name": plugin["name"], "url": plugin["url"]},
                "publisher": ORGANIZATION,
            },
        ),
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
    make_webp(images, plugin["image"])
    build_share(plugin, out, hashes)
    build_manual(plugin, out, hashes)
    build_manual_page(plugin, others, out)
    render(
        out / "index.html",
        "plugin.html",
        "../../",
        plugin["url"],
        plugin=plugin,
        others=others,
        plugins_root="../",
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
    for index, plugin in enumerate(plugins):
        plugin.update(read_highlights(plugin["name"], index))
    if unknown := sorted(set(HIGHLIGHTS) - {plugin["name"] for plugin in plugins}):
        print(f"  note: highlights.toml names {', '.join(unknown)}, which the site doesn't show")
    # Every page's header and footer list the plugins.
    env.globals["catalog"] = [{"name": plugin["name"], "slug": plugin["slug"]} for plugin in plugins]

    hashes = json.loads(HASHES.read_text()) if HASHES.exists() else {}
    for plugin in plugins:
        build_plugin(plugin, [other for other in plugins if other is not plugin], hashes)
    current = {plugin["slug"] for plugin in plugins}
    if PLUGINS.exists():
        for old in PLUGINS.iterdir():
            if old.is_dir() and old.name not in current:
                print(f"  removing {old.name}: discontinued, or its repository is gone or has no release")
                shutil.rmtree(old)
    keys = [key for plugin in plugins for key in (plugin["name"], f"{plugin['name']} share")]
    hashes = {key: hashes[key] for key in keys}
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
    render(ROOT / "404.html", "404.html", "/", others=plugins, plugins_root="/plugins/")
    write_checked(ROOT / "sitemap.xml", sitemap(plugins))
    write_checked(ROOT / "robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n")
    for plugin in plugins:
        print(f"  {plugin['name']} {plugin['latest']['version']} ({plugin['latest']['date']})")
    if LOCAL:
        print(f"Built from the checkouts in {LOCAL}: push them and build again without --local before committing.")


if __name__ == "__main__":
    main()
