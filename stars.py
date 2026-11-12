#!/usr/bin/env python3
"""The starfield behind every page: three tiles of stars, far to near, in the design tokens' colors.

    python3 -I stars.py

Writes assets/stars-far.svg, stars-mid.svg and stars-near.svg. site.css tiles each over a layer
that drifts by exactly one tile and starts over, so the movement never jumps. The same seed
gives the same sky, so rerunning changes nothing unless the numbers here change.
"""

import pathlib
import random

ASSETS = pathlib.Path(__file__).resolve().parent / "assets"
TEXT_DIM, GLOW, ACCENT = "#8a95a9", "#5fd0ff", "#3d9bff"

# name, tile size, number of stars, seed
LAYERS = [("far", 360, 40, 1), ("mid", 720, 28, 2), ("near", 1080, 12, 3)]


def star(kind, rng):
    """The circles of one star at (0, 0): a dot, and for the near ones a soft halo."""
    if kind == "far":
        return [(rng.uniform(0.5, 0.9), TEXT_DIM, rng.uniform(0.3, 0.6))]
    if kind == "mid":
        color = GLOW if rng.random() < 0.3 else TEXT_DIM
        return [(rng.uniform(0.8, 1.2), color, rng.uniform(0.45, 0.7))]
    color = ACCENT if rng.random() < 0.3 else GLOW
    return [(9, color, 0.05), (5, color, 0.1), (2.8, color, 0.22), (rng.uniform(1.3, 1.8), color, 1.0)]


def tile(kind, size, count, seed):
    rng = random.Random(seed)
    circles = []
    for _ in range(count):
        x, y = rng.uniform(0, size), rng.uniform(0, size)
        parts = star(kind, rng)
        reach = max(r for r, _, _ in parts)
        # A star near an edge is drawn again across it, so the tiles meet without a cut.
        for dx in (-size, 0, size):
            for dy in (-size, 0, size):
                px, py = x + dx, y + dy
                if -reach <= px <= size + reach and -reach <= py <= size + reach:
                    for r, color, opacity in parts:
                        circles.append(
                            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{r:.2f}" fill="{color}" opacity="{opacity:.2f}"/>'
                        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
        + "".join(circles)
        + "</svg>\n"
    )


def main():
    for kind, size, count, seed in LAYERS:
        path = ASSETS / f"stars-{kind}.svg"
        path.write_text(tile(kind, size, count, seed))
        print(path.relative_to(ASSETS.parent))


if __name__ == "__main__":
    main()
