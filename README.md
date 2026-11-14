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
with a published release gets a card and a page. One without a release is skipped until it has one.
Run it after `gh release create`, since the version, the notes and the download link come from the
release.

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
| Main image, also the share picture | the README's first image |
| Page text | the rest of the README, without a paragraph that opens with a link to this page |
| Screenshots | the other images `manual.md` uses, captioned with their alt text |
| Manual page, `plugins/<name>/manual/` | `manual.md`; the README's link to `manual.md` goes there |
| Manual PDF | `manual.md`, printed with Chromium, reprinted only when it or its images change |
| Version, date, what's new, earlier versions | the GitHub releases and their notes, without the `Install:` paragraph |
| Download button | the release's `.tar.gz` |

A discontinued plugin (a `> **Discontinued** …` paragraph right under its README's title, see
`discontinue-plugin.md` in FrameworkBtw, or an archived repository) is left off the site: no card
and no page (owner, 2026-11-13).

So a release repository that follows `release-repo.md` in FrameworkBtw needs nothing else. The build
stops if anything would link a private source repository.

## What a search engine reads

The build writes it all, for every plugin, with nothing to keep up by hand except the front page's
text:

- Each page has one title, one meta description on one line, a canonical link, Open Graph and
  `twitter:card` tags with the picture's size and alt text.
- Structured data: `SoftwareApplication` on a plugin's page (version, date, download, price 0),
  `Organization` and `WebSite` on the front page. No rating: there is none, and a made-up one is
  never added.
- `sitemap.xml` (the front page, every plugin's page and manual page, dated by the latest release),
  `robots.txt`, `404.html` and `plugins/index.html`, which sends `/plugins/` to the front page.
- **By hand:** the front page's title, description, heading, lead and About paragraph in
  `templates/index.html` say what the plugins do. Go through them when a plugin joins or leaves.

The words follow one rule (the SEO plan of 2026-11-14): free, CLAP, Linux and what the plugin does.
Never "open source" (the source is private) and never VST (none ships).

## Files

- `build.py`: the generator. Needs `/usr/bin/python3` with `python-markdown` and `python-jinja`,
  `git` and `chromium`. It uses `gh`'s token if there is one, only for the API's rate limit.
- `templates/`: the pages and the PDF's style. `assets/`: the site's CSS, logo and font.
- Generated, committed because Pages serves them: `index.html`, `plugins/`, `404.html`,
  `sitemap.xml`, `robots.txt`, `.manual-hashes.json`. Don't edit these by hand. `.nojekyll` makes Pages serve the files as they are.
- `googleec76a87cafc4f47f.html`: Google Search Console's proof that the site is the owner's. The build
  leaves it alone; removing it loses the verification.
- `.cache/`, not committed: shallow clones of the release repositories.

The colors and the font are the ones the plugins use. Ubuntu Light is under the Ubuntu Font Licence,
`assets/fonts/UFL.txt`.

## The starfield

Every page has a still starfield behind it: `assets/stars-{far,mid,near}.svg`, drawn by
`python3 -I stars.py` and tiled by `site.css`. It doesn't move (the owner's choice, 2026-11-14), so it
costs nothing once the page is drawn.
