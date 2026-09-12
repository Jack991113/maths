#!/usr/bin/env python3
"""Deterministic black-and-white coordinate drawings. No model/API is used."""
from __future__ import annotations

import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _font(size: int):
    choices = [os.environ.get("MATHS_FIGURE_FONT", ""),
               "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
               "C:/Windows/Fonts/times.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"]
    for path in choices:
        if path and Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def draw_figure(spec: dict, output: Path) -> dict:
    """Render curves, exact-coordinate segments, circles and labelled points.

    Coordinates have an equal physical scale. Curves are selected by family,
    never evaluated as Python. For reciprocal graphs x=0 is excluded and
    separate branches are drawn. Labels are literal ASCII mathematical labels.
    """
    xmin, xmax, ymin, ymax = map(float, spec["bounds"])
    if not all(map(math.isfinite, (xmin, xmax, ymin, ymax))):
        raise ValueError("Figure bounds must be finite")
    if xmin >= xmax or ymin >= ymax:
        raise ValueError("Figure bounds must be increasing")
    width = 1400
    scale = (width - 160) / (xmax - xmin)
    height = round((ymax - ymin) * scale + 160)
    im = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(im)
    font = _font(72)
    def xy(p):
        return (80 + (float(p[0]) - xmin) * scale,
                80 + (ymax - float(p[1])) * scale)
    def inside(p):
        return xmin <= p[0] <= xmax and ymin <= p[1] <= ymax
    def line(a, b, dash=False, weight=4):
        aa, bb = xy(a), xy(b)
        if not dash:
            d.line([aa, bb], fill="black", width=weight)
        else:
            dist = math.dist(aa, bb)
            for start in range(0, math.ceil(dist), 26):
                t1, t2 = start / dist, min((start + 15) / dist, 1)
                d.line([(aa[0]+(bb[0]-aa[0])*t1, aa[1]+(bb[1]-aa[1])*t1),
                        (aa[0]+(bb[0]-aa[0])*t2, aa[1]+(bb[1]-aa[1])*t2)],
                       fill="black", width=weight)
    def label(p, value, offset=(10, -52)):
        px, py = xy(p)
        d.text((px + offset[0], py + offset[1]), value, fill="black", font=font)
    if spec.get("axes", False):
        if ymin < 0 < ymax:
            line((xmin, 0), (xmax, 0), weight=3)
            xx, yy = xy((xmax, 0))
            d.polygon([(xx, yy), (xx-21, yy-10), (xx-21, yy+10)], fill="black")
            label((xmax, 0), "x", (-35, 12))
        if xmin < 0 < xmax:
            line((0, ymin), (0, ymax), weight=3)
            xx, yy = xy((0, ymax))
            d.polygon([(xx, yy), (xx-10, yy+21), (xx+10, yy+21)], fill="black")
            label((0, ymax), "y", (15, -8))
        if inside((0, 0)):
            label((0, 0), "O", (-65, 9))
    for curve in spec.get("curves", []):
        family = curve["family"]
        if family not in ("reciprocal", "linear", "quadratic"):
            raise ValueError(f"Unsupported curve family: {family}")
        previous = None
        for i in range(3201):
            x = xmin + (xmax-xmin)*i/3200
            if family == "reciprocal":
                if abs(x) < (xmax-xmin)/6400:
                    previous = None
                    continue
                y = float(curve["k"])/x
            elif family == "linear":
                y = float(curve.get("a", 1))*x + float(curve.get("b", 0))
            else:
                y = float(curve["a"])*x*x+float(curve["b"])*x+float(curve["c"])
            p = (x, y)
            if inside(p):
                if previous and not (family == "reciprocal" and previous[0]*x <= 0):
                    line(previous, p, weight=4)
                previous = p
            else:
                previous = None
    for c in spec.get("circles", []):
        cx, cy, r = float(c["center"][0]), float(c["center"][1]), float(c["radius"])
        if r <= 0:
            raise ValueError("Circle radius must be positive")
        d.ellipse([xy((cx-r, cy+r)), xy((cx+r, cy-r))], outline="black", width=4)
    for segment in spec.get("segments", []):
        line(segment["a"], segment["b"], segment.get("dash", False))
    for mark in spec.get("right_angles", []):
        p, u, v = mark["vertex"], mark["u"], mark["v"]
        size = mark.get("size", .25)
        nu, nv = math.hypot(*u), math.hypot(*v)
        a = [p[j]+u[j]/nu*size for j in (0, 1)]
        b = [a[j]+v[j]/nv*size for j in (0, 1)]
        c = [p[j]+v[j]/nv*size for j in (0, 1)]
        line(a, b, weight=3)
        line(b, c, weight=3)
    for point in spec.get("points", []):
        p = point["xy"]
        if not inside(p):
            raise ValueError(f"Point is outside figure bounds: {point}")
        xx, yy = xy(p)
        if point.get("dot", True):
            d.ellipse((xx-6, yy-6, xx+6, yy+6), fill="black")
        if point.get("label"):
            label(p, point["label"], point.get("offset", (12, -50)))
    for item in spec.get("labels", []):
        label(item["xy"], item["text"], item.get("offset", (0, 0)))
    output.parent.mkdir(parents=True, exist_ok=True)
    im.save(output, dpi=(300, 300))
    return {"path": str(output), "pixels": [width, height], "dpi": 300,
            "method": "deterministic_coordinate_drawing", "bounds": spec["bounds"]}
