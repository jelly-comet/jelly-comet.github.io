# jelly-comet.github.io

An overview of the plugins, latest release first, a page for each one and a page for its manual,
generated from the public `<Name>-release` repositories on GitHub and served by GitHub Pages from
`main`.

## After a release, or for a new plugin

```bash
./build.py
git add -A && git commit -m "Site: <what changed>" && git push
```

That is all, also for a new plugin: every public repository of `jelly-comet` named `<Name>-release`
with a published release gets a panel on the front page, a place in its install window, a page and a
manual page, and the three latest releases a place in the front page's window switcher (owner, 2026-11-20). One without a release is skipped until it has one. Run it after
`gh release create`, since the version, the notes and the download link come from the release.

For a new plugin, two things are by hand:

- **An entry in `highlights.toml`** (see below): what kind of plugin it is, its colour, three facts
  beside its window. The build notes a plugin that has none; it still gets its panel and page, with a
  stand-in colour and no facts.
- **The front page's words** in `templates/index.html` (see "What a search engine reads").

To look at it first:

```bash
python3 -m http.server 8765
```

and open <http://127.0.0.1:8765/>.

To look at a release repository's change before it is pushed (a README, a manual, a `site.toml`):

```bash
./build.py --local ../releases
```

reads the `<Name>-release` checkouts in that folder as they lie, in place of GitHub's. Versions and
notes still come from the published releases. Build again without `--local` after pushing them,
before committing the site.

## What comes from where

| On the site | From the release repository |
| --- | --- |
| Name | the repository's name without `-release`; the README's `# <Name>` must start the file |
| Summary on the card and page | the README's first paragraph, without its last words "CLAP for Linux." |
| Page title, after the name | `site.toml`'s `title`; without it the bare name |
| Tagline in the page's heading, on the card and in "More from JellyComet" | `site.toml`'s `tagline`; without it none |
| Meta description | `site.toml`'s `description`; without it the README's first paragraph on one line |
| Main image | the README's first image, with a WebP copy beside every PNG of `images/` (a browser that shows WebP loads that, about an eighth of the size) and a 480 px one for the cards |
| Share picture, `plugins/<name>/share.png` | the name, kind, tagline and main image on 1200 x 630 (`templates/share.html`), drawn with Chromium, redrawn only when they change |
| Page text | the rest of the README, without a paragraph that opens with a link to this page |
| Screenshots | the other images `manual.md` uses, captioned with their alt text |
| Manual page, `plugins/<name>/manual/` | `manual.md`; the README's link to `manual.md` goes there |
| Manual PDF | `manual.md`, printed with Chromium, reprinted only when it or its images change |
| Version, date, what's new, earlier versions | the GitHub releases and their notes, without the `Install:` paragraph |
| Download button | the release's `.tar.gz` |

A plugin's page lays out the README's sections by their headings: **What it's for** as tiles and
**Features** as a checklist (each a list whose items open with a bold label), **FAQ** folded (one
`###` per question), **Requirements** in the box beside the text, every code block as a small
terminal with a Copy button. A section that doesn't match shows as written. The front page's install
window takes the archive's name from the release and the `.clap` file's from the README's `cp … ~/.clap/`.

A discontinued plugin (a `> **Discontinued** …` paragraph right under its README's title, see
`discontinue-plugin.md` in FrameworkBtw, or an archived repository) is left off the site: no card
and no page (owner, 2026-11-13).

So a release repository that follows `release-repo.md` in FrameworkBtw needs nothing else. The build
stops if anything would link a private source repository.

## highlights.toml

The site's own words about each plugin, beside what its release repository says. Every field is
optional:

| Field | Where it shows |
| --- | --- |
| `kind` | above the name on its page and on its front-page panel ("Vocal effect") |
| `short` | one word beside its name in the front page's window switcher ("Pitch") |
| `accent` | its colour: dots, lines, ticks and glows; `#rrggbb` |
| `chips` | up to three facts beside its window, each `{ icon = "…", text = "…" }`; the icons are listed in the file |
| `glance` | more rows of its page's "At a glance" box, like `Latency = "0.25 ms"` |

Every fact must be one its README states. A name the site doesn't show (a discontinued plugin) gets a
note from the build; take its entry out.

## What a search engine reads

The build writes it all, for every plugin, with nothing to keep up by hand except the front page's
text:

- Each page has one title, one meta description on one line, a canonical link, Open Graph and
  `twitter:card` tags with the picture's size, type and alt text.
- Structured data: `SoftwareApplication` and `BreadcrumbList` on a plugin's page (version, first and
  latest release, download and its size, price 0, the Features labels, the Requirements, the install
  section), `BreadcrumbList` and `TechArticle` on its manual page, `Organization` and `WebSite` on the front
  page. No rating: there is none, and a made-up one is never added. No `FAQPage` or `HowTo`: Google
  shows neither any more.
- A manual page's pictures carry their width and height, and all but the first load lazily. A page's
  biggest picture (the front page's first window, a plugin page's main image) is fetched first
  (`fetchpriority`).
- `sitemap.xml` (the front page, every plugin's page and manual page, dated by the latest release),
  `robots.txt`, `404.html` and `plugins/index.html`, which sends `/plugins/` to the front page.
- **By hand:** the front page's title, description, heading, lead and About paragraph in
  `templates/index.html` say what the plugins do. Go through them when a plugin joins or leaves.

The words follow one rule (the SEO plan of 2026-11-14): free, CLAP, Linux and what the plugin does.
Never "open source" (the source is private), and VST only where a README's FAQ says none ships.

## Files

- `build.py`: the generator. Needs `/usr/bin/python3` with `python-markdown` and `python-jinja`,
  `git`, `chromium` and ImageMagick's `magick`. It uses `gh`'s token if there is one, only for the API's rate limit.
- `highlights.toml`: each plugin's kind, colour and facts, by hand (above).
- `templates/`: the pages and the PDF's style; `icons.html` holds the icons every page draws.
  `assets/`: the site's CSS, `site.js` (the window switcher, install tabs, Copy buttons and the
  plugin page's section bar; every page works without it), `lightbox.js`, logo and fonts.
- Generated, committed because Pages serves them: `index.html`, `plugins/`, `404.html`,
  `sitemap.xml`, `robots.txt`, `.manual-hashes.json`. Don't edit these by hand. `.nojekyll` makes Pages serve the files as they are.
- `googleec76a87cafc4f47f.html` and `BingSiteAuth.xml`: Google Search Console's and Bing Webmaster
  Tools' proof that the site is the owner's. The build leaves them alone; removing one loses its
  verification.
- `favicon.ico`, `apple-touch-icon.png`, `site.webmanifest` and `assets/icon-{192,512}.png`: the icons
  browsers and phones ask for, drawn once from `assets/favicon.svg` and `assets/logo-mark.svg` with
  `magick`; the build leaves them alone.
- `.cache/`, not committed: shallow clones of the release repositories.

The blue and the font are the ones the plugins use. Ubuntu (Light, Regular and Medium for the pages,
Light alone for the PDFs) is under the Ubuntu Font Licence, `assets/fonts/UFL.txt`.

## The starfield

Every page has a still starfield behind it: `assets/stars-{far,mid,near}.svg`, drawn by
`python3 -I stars.py` and tiled by `site.css`. It doesn't move (the owner's choice, 2026-11-14), so it
costs nothing once the page is drawn.
