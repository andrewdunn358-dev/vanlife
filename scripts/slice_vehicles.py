#!/usr/bin/env python3
"""
Cut a grid of vehicle images into the seven separate files the picker wants.

Written for a screenshot of a mockup, where all seven sit in one image.
Finds the cards by looking for the near-white panels against the page
background, crops each, trims the surrounding whitespace and writes them
out in reading order.

    python3 scripts/slice_vehicles.py /volume1/data/veh_picker.png
    python3 scripts/slice_vehicles.py /volume1/data/veh_picker.png --write

Without --write it only reports what it found, so you can check the count
and the sizes before anything is created.

A screenshot is a poor source - the vehicles will be a few hundred pixels
across and will look soft at any reasonable display size. Fine to prove
the layout; generate them individually at about 1200x800 when you want
them to look right.
"""
import argparse
import os
import sys

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is needed: pip3 install pillow")

ORDER = ["vw", "panel", "coachbuilt", "aclass", "caravan", "twinaxle", "car"]


def find_cards(img, dark_below=200, min_w=60, min_h=40, min_px=250):
    """Find the vehicles themselves, not the cards.

    Card panels are white on a near-white page - no contrast to detect.
    The vehicles are the only substantial dark content, so look for those.
    """
    g = img.convert("L")
    w, h = g.size
    px = g.load()

    light = [[px[x, y] < dark_below for x in range(w)] for y in range(h)]

    seen = [[False] * w for _ in range(h)]
    boxes = []
    for y in range(h):
        for x in range(w):
            if not light[y][x] or seen[y][x]:
                continue
            # flood fill, iterative
            stack = [(x, y)]
            seen[y][x] = True
            x0 = x1 = x
            y0 = y1 = y
            n = 0
            while stack:
                cx, cy = stack.pop()
                n += 1
                x0, x1 = min(x0, cx), max(x1, cx)
                y0, y1 = min(y0, cy), max(y1, cy)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                               (1, 1), (-1, -1), (1, -1), (-1, 1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h and light[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            bw, bh = x1 - x0 + 1, y1 - y0 + 1
            if bw >= min_w and bh >= min_h and n >= min_px and bw < w * 0.6:
                boxes.append((x0, y0, x1, y1))
    return boxes


def reading_order(boxes, row_tol=30):
    rows = []
    for b in sorted(boxes, key=lambda b: b[1]):
        for r in rows:
            if abs(r[0][1] - b[1]) < row_tol:
                r.append(b)
                break
        else:
            rows.append([b])
    out = []
    for r in rows:
        out.extend(sorted(r, key=lambda b: b[0]))
    return out


def trim(img, tol=246):
    """Drop surrounding near-white so every crop frames its vehicle."""
    g = img.convert("L")
    w, h = g.size
    px = g.load()
    x0, y0, x1, y1 = w, h, 0, 0
    for y in range(h):
        for x in range(w):
            if px[x, y] < tol:
                x0, y0 = min(x0, x), min(y0, y)
                x1, y1 = max(x1, x), max(y1, y)
    if x1 <= x0 or y1 <= y0:
        return img
    pad = 6
    return img.crop((max(0, x0 - pad), max(0, y0 - pad),
                     min(w, x1 + pad), min(h, y1 + pad)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--out", default="site-assets/vehicles")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--min-width", type=int, default=60)
    args = ap.parse_args()

    if not os.path.exists(args.source):
        sys.exit(f"No such file: {args.source}")

    img = Image.open(args.source).convert("RGB")
    print(f"source {img.size[0]}x{img.size[1]}\n")

    boxes = reading_order(find_cards(img, min_w=args.min_width))
    print(f"found {len(boxes)} vehicles")
    small = [b for b in boxes if (b[2] - b[0]) < 300]
    if small:
        print(f"WARNING: {len(small)} are under 300px wide. The picker shows them at\n"
              "         about 250px, so anything smaller will look soft. Generate each\n"
              "         vehicle separately at around 1200x800 rather than slicing a grid.\n")
    if len(boxes) != len(ORDER):
        print(f"expected {len(ORDER)}. Try --min-width to include or exclude panels.")

    for i, b in enumerate(boxes):
        name = ORDER[i] if i < len(ORDER) else f"extra{i}"
        crop = trim(img.crop((b[0], b[1], b[2] + 1, b[3] + 1)))
        flag = "too small" if crop.size[0] < 300 else "ok"
        print(f"  {name:<11} {crop.size[0]:>4}x{crop.size[1]:<4}  {flag}")
        if args.write and i < len(ORDER):
            os.makedirs(args.out, exist_ok=True)
            crop.save(os.path.join(args.out, f"{name}.png"))

    if args.write:
        print(f"\nwritten to {args.out}/")
        print("Now set the image names in scripts/assets/vehicles.json and rebuild.")
    else:
        print("\nNothing written. Re-run with --write once the panels look right.")


if __name__ == "__main__":
    main()
