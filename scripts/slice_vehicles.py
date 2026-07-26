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


def find_cards(img, dark_below=232, min_w=60, min_h=40, min_px=250, close=9):
    """Find the vehicles themselves, not the cards.

    Card panels are white on a near-white page, so there is nothing to
    detect there. The vehicles are the only substantial darker content.

    A white van on a white background only registers as dark at its
    windows, wheels and shadow lines, which flood-fill then treats as
    several separate objects. So the mask is dilated by `close` pixels
    first, which bridges those gaps and makes each vehicle one blob.
    """
    g = img.convert("L")
    w, h = g.size
    px = g.load()

    raw = [[px[x, y] < dark_below for x in range(w)] for y in range(h)]

    # Horizontal then vertical dilation - cheap separable morphology.
    tmp = [[False] * w for _ in range(h)]
    for y in range(h):
        row = raw[y]
        run = -1
        for x in range(w):
            if row[x]:
                run = x
            if run >= 0 and x - run <= close:
                tmp[y][x] = True
        run = -1
        for x in range(w - 1, -1, -1):
            if row[x]:
                run = x
            if run >= 0 and run - x <= close:
                tmp[y][x] = True

    light = [[False] * w for _ in range(h)]
    for x in range(w):
        run = -1
        for y in range(h):
            if tmp[y][x]:
                run = y
            if run >= 0 and y - run <= close:
                light[y][x] = True
        run = -1
        for y in range(h - 1, -1, -1):
            if tmp[y][x]:
                run = y
            if run >= 0 and run - y <= close:
                light[y][x] = True

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
            if bw >= min_w and bh >= min_h and n >= min_px and bw < w * 0.75:
                # pull the box back in to the real content
                boxes.append((max(0, x0 + close), max(0, y0 + close),
                              min(w - 1, x1 - close), min(h - 1, y1 - close)))
    return boxes


def grid_boxes(img, cols, rows, top=0.0, bottom=1.0):
    """Slice into equal cells. Predictable, and the layout IS a grid.

    Blob detection struggles here: a white van on a white card only shows
    as dark at its windows and wheels, and bridging those gaps also
    bridges the vehicle to its caption. Cutting on the grid avoids the
    whole problem.

    top/bottom trim the region before slicing, to cut off a page heading
    or footer.
    """
    w, h = img.size
    y0 = int(h * top)
    y1 = int(h * bottom)
    ch = (y1 - y0) / rows
    cw = w / cols
    out = []
    for r in range(rows):
        for c in range(cols):
            out.append((int(c * cw), int(y0 + r * ch),
                        int((c + 1) * cw) - 1, int(y0 + (r + 1) * ch) - 1))
    return out


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
    ap.add_argument("--close", type=int, default=9,
                    help="pixels of gap to bridge. Raise if one vehicle splits "
                         "into several, lower if two merge into one.")
    ap.add_argument("--dark", type=int, default=232,
                    help="tone below which a pixel counts as content")
    ap.add_argument("--grid", metavar="COLSxROWS",
                    help="slice on a grid instead of detecting, e.g. 4x2. More "
                         "reliable when the source is a laid-out grid.")
    ap.add_argument("--top", type=float, default=0.0,
                    help="with --grid, skip this fraction from the top (page heading)")
    ap.add_argument("--bottom", type=float, default=1.0,
                    help="with --grid, stop at this fraction down")
    args = ap.parse_args()

    if not os.path.exists(args.source):
        sys.exit(f"No such file: {args.source}")

    img = Image.open(args.source).convert("RGB")
    print(f"source {img.size[0]}x{img.size[1]}\n")

    if args.grid:
        try:
            cols, rows = (int(x) for x in args.grid.lower().split("x"))
        except ValueError:
            sys.exit("--grid wants something like 4x2")
        boxes = grid_boxes(img, cols, rows, args.top, args.bottom)
        print(f"slicing {cols}x{rows} = {len(boxes)} cells "
              f"between {args.top:.0%} and {args.bottom:.0%} of the height")
    else:
        boxes = reading_order(find_cards(img, dark_below=args.dark,
                                         min_w=args.min_width, close=args.close))
        print(f"detected {len(boxes)} vehicles")
    small = [b for b in boxes if (b[2] - b[0]) < 300 and not args.grid]
    if small:
        print(f"WARNING: {len(small)} are under 300px wide. The picker shows them at\n"
              "         about 250px, so anything smaller will look soft. Generate each\n"
              "         vehicle separately at around 1200x800 rather than slicing a grid.\n")


    kept = 0
    for b in boxes:
        crop = trim(img.crop((b[0], b[1], b[2] + 1, b[3] + 1)))
        if crop.size[0] < 40 or crop.size[1] < 25:
            continue  # empty cell
        name = ORDER[kept] if kept < len(ORDER) else f"extra{kept}"
        i = kept
        kept += 1
        flag = "too small" if crop.size[0] < 300 else "ok"
        print(f"  {name:<11} {crop.size[0]:>4}x{crop.size[1]:<4}  {flag}")
        if args.write and i < len(ORDER):
            os.makedirs(args.out, exist_ok=True)
            crop.save(os.path.join(args.out, f"{name}.png"))

    if kept != len(ORDER):
        print(f"\n{kept} usable images for {len(ORDER)} slots. Adjust --grid, "
              "--top or --bottom.")
    if args.write:
        print(f"\nwritten to {args.out}/")
        print("Now set the image names in scripts/assets/vehicles.json and rebuild.")
    else:
        print("\nNothing written. Re-run with --write once the panels look right.")


if __name__ == "__main__":
    main()
