"""Generate ProjectHub's icons: the Teams app icons and the website favicon.

The in-app logo (frontend/index.html) is the same mark drawn as inline SVG;
keep the geometry below in sync with it.

    python scripts/make_icons.py
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]

PURPLE_LIGHT = (189, 92, 255)   # #BD5CFF
PURPLE = (161, 0, 255)          # #A100FF (brand)
PURPLE_DARK = (98, 0, 170)      # #6200AA
WHITE = (255, 255, 255, 255)

SCALE = 4  # draw large, then downsample for smooth edges

# Mark geometry as fractions of the icon size.
CENTER = (0.5, 0.53)
NODE_ANGLES = (-90, 30, 150)    # degrees: top, lower right, lower left
NODE_DISTANCE = 0.27
NODE_RADIUS = 0.085
HUB_RADIUS = 0.125
HUB_DOT_RADIUS = 0.05
LINE_WIDTH = 0.055


def gradient(size):
    """Diagonal purple gradient, light top-left to dark bottom-right."""
    image = Image.new("RGB", (size, size))
    pixels = image.load()
    stops = [(0.0, PURPLE_LIGHT), (0.45, PURPLE), (1.0, PURPLE_DARK)]

    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
                if t <= t1:
                    f = (t - t0) / (t1 - t0)
                    pixels[x, y] = tuple(round(a + (b - a) * f) for a, b in zip(c0, c1))
                    break
    return image


def node_positions(size):
    cx, cy = CENTER[0] * size, CENTER[1] * size
    return (cx, cy), [
        (cx + NODE_DISTANCE * size * math.cos(math.radians(a)),
         cy + NODE_DISTANCE * size * math.sin(math.radians(a)))
        for a in NODE_ANGLES
    ]


def circle(draw, center, radius, fill):
    x, y = center
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)


def draw_mark(draw, size, hub_dot_fill):
    hub, nodes = node_positions(size)
    for node in nodes:
        draw.line((hub, node), fill=WHITE, width=round(LINE_WIDTH * size))
    for node in nodes:
        circle(draw, node, NODE_RADIUS * size, WHITE)
    circle(draw, hub, HUB_RADIUS * size, WHITE)
    if hub_dot_fill:
        circle(draw, hub, HUB_DOT_RADIUS * size, hub_dot_fill)


def color_icon(size, rounded):
    big = size * SCALE
    background = gradient(big).convert("RGBA")

    if rounded:
        mask = Image.new("L", (big, big), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=round(big * 0.22), fill=255)
        background.putalpha(mask)

    draw_mark(ImageDraw.Draw(background), big, PURPLE + (255,))
    return background.resize((size, size), Image.Resampling.LANCZOS)


def outline_icon(size):
    """White mark on transparent, as Teams requires for the 32px outline icon."""
    big = size * SCALE
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw_mark(ImageDraw.Draw(image), big, (0, 0, 0, 0))
    return image.resize((size, size), Image.Resampling.LANCZOS)


if __name__ == "__main__":
    # Teams: full-bleed color icon (Teams rounds the corners itself).
    color_icon(192, rounded=False).save(ROOT / "teams" / "color.png")
    outline_icon(32).save(ROOT / "teams" / "outline.png")
    # Website favicon and home-screen icon.
    color_icon(192, rounded=True).save(ROOT / "frontend" / "icon.png")
    color_icon(32, rounded=True).save(ROOT / "frontend" / "favicon-32.png")
    print("Icons written.")
