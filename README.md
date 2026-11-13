# jelly-comet.github.io

An overview of the plugins, latest release first, and a page for each one, generated from the
public `<Name>-release` repositories on GitHub and served by GitHub Pages from `main`.

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

## What comes from where

| On the site | From the release repository |
| --- | --- |
| Name | the repository's name without `-release`; the README's `# <Name>` must start the file |
| Summary on the card and page | the README's first paragraph, without "CLAP and VST3 for Linux." |
| Main image | the README's first image |
| Page text | the rest of the README |
| Screenshots | the other images `manual.md` uses, captioned with their alt text |
| Manual PDF | `manual.md`, printed with Chromium, reprinted only when it or its images change |
| Version, date, what's new, earlier versions | the GitHub releases and their notes, without the `Install:` paragraph |
| Download button | the release's `.tar.gz` |

A discontinued plugin (a `> **Discontinued** …` paragraph right under its README's title, see
`discontinue-plugin.md` in FrameworkBtw, or an archived repository) is left off the site: no card
and no page (owner, 2026-11-13).

So a release repository that follows `release-repo.md` in FrameworkBtw needs nothing else. The build
stops if anything would link a private source repository.

## Files

- `build.py`: the generator. Needs `/usr/bin/python3` with `python-markdown` and `python-jinja`,
  `git` and `chromium`. It uses `gh`'s token if there is one, only for the API's rate limit.
- `templates/`: the pages and the PDF's style. `assets/`: the site's CSS, logo and font.
- Generated, committed because Pages serves them: `index.html`, `plugins/`, `.manual-hashes.json`.
  Don't edit these by hand. `.nojekyll` makes Pages serve the files as they are.
- `.cache/`, not committed: shallow clones of the release repositories.

The colors and the font are the ones the plugins use. Ubuntu Light is under the Ubuntu Font Licence,
`assets/fonts/UFL.txt`.

## The starfield

Every page has a slowly drifting starfield behind it: `assets/stars-{far,mid,near}.svg`, drawn by
`python3 -I stars.py`, tiled and moved by `site.css`, smooth at the screen's rate for everyone (the
owner's choice, 2026-11-12: no slower fallback). It adds about 6 % of a core to what the moving logo
costs where the browser draws with a graphics card, and about 60 % where it draws without one
(headless Chromium at 1920 x 1080). Still for anyone who asks for less motion.
