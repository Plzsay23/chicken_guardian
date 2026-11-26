"""Procedural synthetic frames for bootstrapping the trace detector before real data exists.

A frame = background (user photo or procedural ground) + labelled objects
(rodent droppings, feed pellets) + unlabelled look-alikes (pebbles, rice husks, twigs,
dirt clods, feather bits) + camera effects (perspective size falloff, defocus,
patrol motion blur, night NoIR/940nm look, JPEG).

The look-alikes are the point: a model that only ever sees droppings on clean concrete
will fire on every dark pebble on the farm.
"""

from pathlib import Path

import cv2
import numpy as np

from .imgio import imread, list_images

SS = 4  # supersampling factor for sprite rendering (anti-aliasing of 5-px objects)


# --------------------------------------------------------------------------- noise / textures
def fractal_noise(h, w, rng, octaves=5, base=4, persistence=0.55):
    out = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        gh, gw = max(2, int(base * 2**o * h / w)), max(2, base * 2**o)
        g = rng.standard_normal((gh, gw)).astype(np.float32)
        out += amp * cv2.resize(g, (w, h), interpolation=cv2.INTER_CUBIC)
        total += amp
        amp *= persistence
    out /= total
    return (out - out.mean()) / (out.std() + 1e-6)


def _tint(gray, bgr_mean, contrast):
    """gray: zero-mean noise field -> BGR float image around bgr_mean."""
    img = np.asarray(bgr_mean, np.float32)[None, None, :] + contrast * gray[..., None]
    return img


def _random_pebbles(img, rng, n, size_px, palette, darken=0.0):
    """Paint small rounded stones directly into a background (unlabelled texture)."""
    h, w = img.shape[:2]
    for _ in range(n):
        r = max(1.0, rng.uniform(*size_px) / 2)
        cx, cy = rng.uniform(0, w), rng.uniform(0, h)
        col = np.array(palette[rng.integers(len(palette))], np.float32) * rng.uniform(0.75, 1.2) * (1 - darken)
        axes = (max(1, int(r * rng.uniform(0.7, 1.3))), max(1, int(r * rng.uniform(0.6, 1.0))))
        cv2.ellipse(img, (int(cx), int(cy)), axes, rng.uniform(0, 180), 0, 360, col.tolist(), -1, cv2.LINE_AA)


def bg_concrete(h, w, rng):
    base = rng.uniform(110, 175)
    n = fractal_noise(h, w, rng)
    img = _tint(n, [base, base * rng.uniform(0.98, 1.03), base * rng.uniform(0.98, 1.06)], rng.uniform(6, 16))
    fine = rng.standard_normal((h, w)).astype(np.float32) * rng.uniform(2, 6)
    img += fine[..., None]
    for _ in range(rng.integers(0, 6)):  # cracks
        pts = np.cumsum(rng.normal(0, 25, (rng.integers(5, 25), 2)), 0) + [rng.uniform(0, w), rng.uniform(0, h)]
        cv2.polylines(img, [pts.astype(np.int32)], False, (base * 0.45,) * 3, int(rng.integers(1, 3)), cv2.LINE_AA)
    for _ in range(rng.integers(0, 5)):  # wet / oil stains
        m = np.zeros((h, w), np.float32)
        cv2.ellipse(m, (int(rng.uniform(0, w)), int(rng.uniform(0, h))),
                    (int(rng.uniform(40, 300)), int(rng.uniform(30, 200))), rng.uniform(0, 180), 0, 360, 1, -1)
        m = cv2.GaussianBlur(m, (0, 0), rng.uniform(15, 40))
        img *= (1 - rng.uniform(0.1, 0.35) * m)[..., None]
    _random_pebbles(img, rng, int(rng.uniform(50, 400)), (1, 4), [(base * 0.7,) * 3, (base * 1.15,) * 3])
    return img


def bg_soil(h, w, rng):
    r = rng.uniform(85, 145)  # brown: B < G < R in BGR
    g = r * rng.uniform(0.72, 0.88)
    b = g * rng.uniform(0.6, 0.82)
    n = fractal_noise(h, w, rng, octaves=6)
    img = _tint(n, [b, g, r], rng.uniform(8, 20))
    img += rng.standard_normal((h, w, 1)).astype(np.float32) * rng.uniform(4, 9)
    pal = [(b * 0.6, g * 0.6, r * 0.6), (b * 1.3, g * 1.25, r * 1.2), (115, 120, 125), (70, 75, 80)]
    _random_pebbles(img, rng, int(rng.uniform(300, 1500)), (2, 10), pal)
    return img


def bg_gravel(h, w, rng):
    base = rng.uniform(90, 150)
    img = _tint(fractal_noise(h, w, rng), [base] * 3, 10)
    pal = [(base * k, base * k * rng.uniform(0.95, 1.05), base * k * rng.uniform(0.95, 1.1)) for k in (0.55, 0.8, 1.1, 1.35)]
    for size in ((15, 45), (6, 18), (2, 7)):
        _random_pebbles(img, rng, int(w * h / (size[1] ** 2) * rng.uniform(0.15, 0.4)), size, pal)
    return img


def bg_husk_litter(h, w, rng):
    """Rice-husk / straw litter spill (왕겨) - elongated tan flakes, same size as droppings."""
    img = bg_soil(h, w, rng)
    n = int(rng.uniform(300, 2500))
    for _ in range(n):
        L = rng.uniform(8, 30)
        cx, cy, a = rng.uniform(0, w), rng.uniform(0, h), rng.uniform(0, 180)
        col = (rng.uniform(90, 140), rng.uniform(150, 190), rng.uniform(175, 215))
        cv2.ellipse(img, (int(cx), int(cy)), (int(L / 2), max(1, int(L / rng.uniform(3, 5) / 2))), a, 0, 360, col, -1, cv2.LINE_AA)
    return img


def bg_grass_edge(h, w, rng):
    img = bg_soil(h, w, rng)
    for _ in range(int(rng.uniform(200, 1200))):
        x0, y0 = rng.uniform(0, w), rng.uniform(0, h)
        L, a = rng.uniform(20, 120), rng.uniform(-np.pi, np.pi)
        col = (rng.uniform(30, 70), rng.uniform(90, 150), rng.uniform(60, 110))
        cv2.line(img, (int(x0), int(y0)), (int(x0 + L * np.cos(a)), int(y0 + L * np.sin(a))), col, int(rng.integers(1, 4)), cv2.LINE_AA)
    return img


def bg_plain_floor(h, w, rng):
    """Smooth tan/beige/grey floor (panel, mat, sacking) with woven grain and fine debris -
    the indoor-ish surfaces most dropping photos are taken on."""
    tone = rng.uniform(90, 190)
    r = tone
    g = r * rng.uniform(0.78, 0.98)
    b = g * rng.uniform(0.6, 0.95)
    img = _tint(fractal_noise(h, w, rng, octaves=4), [b, g, r], rng.uniform(5, 14))
    if rng.random() < 0.6:  # woven / brushed grain
        period = rng.uniform(3, 9)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        a = rng.uniform(0, np.pi)
        grain = np.sin((xx * np.cos(a) + yy * np.sin(a)) * 2 * np.pi / period)
        img *= (1 + rng.uniform(0.03, 0.1) * grain)[..., None]
    img += rng.standard_normal((h, w, 1)).astype(np.float32) * rng.uniform(2, 6)
    dark = [(b * 0.45, g * 0.45, r * 0.45), (b * 0.7, g * 0.7, r * 0.7)]
    light = [(b * 1.3, g * 1.25, r * 1.2), (200, 205, 210)]
    _random_pebbles(img, rng, int(rng.uniform(300, 2000)), (1, 4), dark + light)  # dust, grit
    return img


PROCEDURAL_BG = [bg_concrete, bg_concrete, bg_soil, bg_gravel, bg_husk_litter, bg_grass_edge, bg_plain_floor, bg_plain_floor]


def add_wall(img, rng):
    """Upper part becomes the poultry-house wall; returns floor start row.
    The robot patrols the wall-floor junction (FR-02/FR-06)."""
    h, w = img.shape[:2]
    split = int(h * rng.uniform(0.1, 0.4))
    tone = rng.uniform(120, 220)
    wall = _tint(fractal_noise(split, w, rng, octaves=3), [tone * rng.uniform(0.9, 1.0), tone, tone * rng.uniform(1.0, 1.1)], 6)
    if rng.random() < 0.5:  # sandwich-panel ribs
        period = int(rng.uniform(40, 160))
        for x in range(int(rng.uniform(0, period)), w, period):
            cv2.line(wall, (x, 0), (x, split), (tone * 0.8,) * 3, 2, cv2.LINE_AA)
    img[:split] = wall
    cv2.line(img, (0, split), (w, split), (tone * 0.35,) * 3, int(rng.integers(2, 6)), cv2.LINE_AA)
    shade = np.linspace(0.55, 1.0, min(60, h - split))[:, None, None]
    img[split:split + len(shade)] *= shade  # contact shadow along wall base
    return split


# --------------------------------------------------------------------------- sprites
def _finish_sprite(col, alpha, angle, rng):
    """Rotate at supersampled scale then downsample. Returns (bgr uint8-range float, alpha)."""
    h, w = alpha.shape
    d = int(np.ceil(np.hypot(h, w))) + 4
    pad_y, pad_x = (d - h) // 2, (d - w) // 2
    C = np.zeros((d, d, 3), np.float32)
    A = np.zeros((d, d), np.float32)
    C[pad_y:pad_y + h, pad_x:pad_x + w] = col
    A[pad_y:pad_y + h, pad_x:pad_x + w] = alpha
    M = cv2.getRotationMatrix2D((d / 2, d / 2), angle, 1.0)
    C = cv2.warpAffine(C, M, (d, d), flags=cv2.INTER_LINEAR)
    A = cv2.warpAffine(A, M, (d, d), flags=cv2.INTER_LINEAR)
    out = max(3, d // SS)
    C = cv2.resize(C, (out, out), interpolation=cv2.INTER_AREA)
    A = cv2.resize(A, (out, out), interpolation=cv2.INTER_AREA)
    ys, xs = np.where(A > 0.05)
    if len(ys) == 0:
        return C, A
    return C[ys.min():ys.max() + 1, xs.min():xs.max() + 1], A[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def _spindle(L, aspect, rng, bend=0.0, pointy=2.0, lumpy=0.0):
    """Supersampled spindle mask + 'height' map z in [0,1] for shading.
    lumpy > 0 modulates the width along the body (irregular, segmented outline)."""
    Ls = L * SS
    W = Ls / aspect
    hh, ww = int(W * 2.4 + Ls * abs(bend) * 0.3 + 8), int(Ls + 8)
    yy, xx = np.mgrid[0:hh, 0:ww].astype(np.float32)
    x = (xx - ww / 2) / (Ls / 2)
    y = yy - hh / 2 - bend * (x**2) * Ls * 0.15
    prof = (W / 2) * np.clip(1 - np.abs(x) ** pointy, 0, None) ** 0.5
    if lumpy > 0:
        k = rng.uniform(1.5, 4.0)
        ph = rng.uniform(0, 2 * np.pi, 2)
        prof = prof * (1 + lumpy * (0.6 * np.sin(k * np.pi * x + ph[0]) + 0.4 * np.sin(2.3 * k * np.pi * x + ph[1])))
        # asymmetric top/bottom edges
        y = y + lumpy * (W / 2) * 0.5 * np.sin(rng.uniform(1, 3) * np.pi * x + rng.uniform(0, 6))
    inside = (np.abs(x) < 1) & (np.abs(y) < prof)
    nrm = np.where(inside, np.abs(y) / np.maximum(prof, 1e-3), 1.0)
    z = np.sqrt(np.clip(1 - nrm**2, 0, 1)) * inside
    side = np.where(inside, y / np.maximum(prof, 1e-3), 0)  # -1 top edge .. 1 bottom edge
    return inside.astype(np.float32), z, side


def make_dropping(rng, length_px):
    """Matched to real photos (references/, 48 boxes): dark core BGR ~ (19, 33, 48) +- 8,
    matte, stubby (L/W 1.5-2.6), blunt ends, lumpy outline, only a soft broad sheen."""
    if length_px < 7 and rng.random() < 0.5:  # tiny mouse pellets read as near-round dark blobs
        aspect = rng.uniform(1.2, 1.8)
    else:
        aspect = rng.uniform(1.5, 2.8)
    mask, z, side = _spindle(length_px, aspect, rng, bend=rng.normal(0, 0.2),
                             pointy=rng.uniform(1.8, 4.0), lumpy=rng.uniform(0.0, 0.18))
    mask = cv2.GaussianBlur(mask, (0, 0), SS * 0.35)  # soft, slightly fuzzy edge
    r = rng.random()
    if r < 0.75:  # fresh / typical
        base = np.array([18.6, 32.7, 47.7], np.float32) * rng.uniform(0.6, 1.35) * (1 + rng.normal(0, 0.08, 3))
        base = np.sort(base)  # keep B <= G <= R: brown, never purple/green
    elif r < 0.9:  # near-black
        v = rng.uniform(10, 25)
        base = np.array([v, v * 1.15, v * 1.3], np.float32)
    else:  # old / dried: greyer brown, lighter
        v = rng.uniform(50, 90)
        base = np.array([v * 0.8, v * 0.95, v * 1.1], np.float32)
    base = np.clip(base, 5, 255)
    shade = 0.72 + 0.28 * z - 0.12 * side
    tex = 1 + 0.18 * fractal_noise(*mask.shape, rng, octaves=3, base=4)  # rough, granular surface
    col = base[None, None] * (shade * tex)[..., None]
    u = rng.random()
    if u < 0.15:  # fresh & wet (outdoor rat droppings): olive-brown body with scattered specular spots
        col = col * np.array([0.9, 1.15, 1.2], np.float32) + 10
        spots = (rng.random(mask.shape) < 0.02) * (z > 0.55) * (side < 0.3)
        spots = cv2.GaussianBlur(spots.astype(np.float32), (0, 0), SS * 0.5)
        col = col + 255 * np.clip(spots * 6, 0, 1)[..., None] * rng.uniform(0.5, 0.9)
    elif u < 0.6:  # soft broad sheen, never a hard streak
        sheen = cv2.GaussianBlur(np.clip(z - 0.5, 0, 1) * (side < 0), (0, 0), SS) * rng.uniform(15, 45)
        col = col + sheen[..., None]
    return _finish_sprite(col, mask, rng.uniform(0, 360), rng)


def make_pellet(rng, length_px):
    h_ = rng.uniform(0.75, 1.15)
    base = np.array([rng.uniform(85, 140), rng.uniform(135, 185), rng.uniform(165, 220)], np.float32) * h_
    if rng.random() < 0.6:  # extruded cylinder pellet, flat ends
        Ls = length_px * SS
        D = Ls / rng.uniform(1.2, 2.6)
        hh, ww = int(D + 6), int(Ls + 6)
        mask = np.zeros((hh, ww), np.float32)
        cv2.rectangle(mask, (3, 3), (ww - 4, hh - 4), 1, -1)
        mask = cv2.GaussianBlur(mask, (0, 0), SS * 0.4) > 0.5
        yy = np.linspace(-1, 1, hh)[:, None]
        z = np.sqrt(np.clip(1 - yy**2, 0, 1)) * np.ones((1, ww))
        shade = 0.6 + 0.4 * z - 0.15 * yy
        shade[:, :int(SS * 2) + 3] *= 1.12  # cut faces catch light
        mask = mask.astype(np.float32)
    else:  # crumble: irregular polygon
        r = length_px * SS / 2
        n = rng.integers(5, 10)
        ang = np.sort(rng.uniform(0, 2 * np.pi, n))
        rad = r * rng.uniform(0.55, 1.0, n)
        pts = np.stack([np.cos(ang) * rad, np.sin(ang) * rad], 1) + r + 4
        hh = ww = int(2 * r + 8)
        mask = np.zeros((hh, ww), np.float32)
        cv2.fillPoly(mask, [pts.astype(np.int32)], 1, cv2.LINE_AA)
        d = cv2.distanceTransform((mask > 0).astype(np.uint8), cv2.DIST_L2, 3)
        shade = 0.65 + 0.35 * np.clip(d / (r * 0.5 + 1e-6), 0, 1)
    tex = 1 + 0.18 * fractal_noise(*mask.shape, rng, octaves=3, base=4)
    col = base[None, None] * (shade * tex)[..., None]
    if rng.random() < 0.25:  # corn fragment in mash: yellow
        col *= np.array([0.45, 1.0, 1.1], np.float32)
    return _finish_sprite(col, mask, rng.uniform(0, 360), rng)


def make_distractor(rng, gsd):
    """Unlabelled look-alike. Returns (bgr, alpha)."""
    kind = rng.choice(["pebble", "husk", "clod", "seed", "twig", "feather"], p=[0.36, 0.2, 0.16, 0.16, 0.07, 0.05])
    if kind == "pebble":
        L = rng.uniform(2, 15) / gsd
        r = L * SS / 2
        n = rng.integers(6, 12)
        ang = np.sort(rng.uniform(0, 2 * np.pi, n))
        rad = r * rng.uniform(0.7, 1.0, n)
        pts = np.stack([np.cos(ang) * rad * rng.uniform(1, 1.6), np.sin(ang) * rad], 1) + r * 1.6 + 4
        s = int(r * 3.2 + 8)
        mask = np.zeros((s, s), np.float32)
        cv2.fillPoly(mask, [pts.astype(np.int32)], 1, cv2.LINE_AA)
        mask = cv2.GaussianBlur(mask, (0, 0), SS * 0.6)
        d = cv2.distanceTransform((mask > 0.5).astype(np.uint8), cv2.DIST_L2, 3)
        v = rng.uniform(35, 190)  # includes dark stones that look like droppings
        base = np.array([v, v * rng.uniform(0.95, 1.08), v * rng.uniform(0.95, 1.15)], np.float32)
        col = base * (0.6 + 0.4 * np.clip(d / (r * 0.6 + 1e-6), 0, 1))[..., None]
        return _finish_sprite(col, mask, rng.uniform(0, 360), rng)
    if kind == "husk":
        mask, z, side = _spindle(rng.uniform(6, 10) / gsd, rng.uniform(3.5, 5.5), rng, bend=rng.normal(0, 0.4), pointy=1.2)
        base = np.array([rng.uniform(90, 140), rng.uniform(150, 195), rng.uniform(180, 225)], np.float32)
        ridges = 1 - 0.15 * (np.sin(side * 9) > 0.6)
        col = base[None, None] * ((0.75 + 0.25 * z) * ridges)[..., None]
        return _finish_sprite(col, mask, rng.uniform(0, 360), rng)
    if kind == "twig":
        mask, z, side = _spindle(rng.uniform(10, 40) / gsd, rng.uniform(8, 20), rng, bend=rng.normal(0, 0.5), pointy=6)
        v = rng.uniform(25, 90)
        col = np.array([v, v * 1.1, v * 1.25], np.float32)[None, None] * (0.6 + 0.4 * z)[..., None]
        return _finish_sprite(col, mask, rng.uniform(0, 360), rng)
    if kind == "clod":
        L = rng.uniform(4, 20) / gsd
        s = int(L * SS + 8)
        mask = (fractal_noise(s, s, rng, octaves=3, base=2) > 0.3).astype(np.float32)
        yy, xx = np.mgrid[0:s, 0:s]
        mask *= ((xx - s / 2) ** 2 + (yy - s / 2) ** 2) < (s / 2.2) ** 2
        mask = cv2.GaussianBlur(mask, (0, 0), SS)
        v = rng.uniform(30, 80)
        col = np.array([v, v * 1.15, v * 1.35], np.float32)[None, None] * np.ones((s, s, 1), np.float32)
        return _finish_sprite(col, mask * rng.uniform(0.5, 0.9), 0, rng)
    if kind == "seed":  # round dark seed: dropping colour, wrong shape
        mask, z, side = _spindle(rng.uniform(2, 5) / gsd, rng.uniform(1.0, 1.4), rng, pointy=2)
        v = rng.uniform(15, 60)
        col = np.array([v, v, v * 1.1], np.float32)[None, None] * (0.5 + 0.5 * z)[..., None]
        return _finish_sprite(col, mask, 0, rng)
    # feather fragment: white thin curve
    mask, z, side = _spindle(rng.uniform(8, 25) / gsd, rng.uniform(4, 9), rng, bend=rng.normal(0, 0.8), pointy=1.5)
    v = rng.uniform(190, 250)
    col = np.full(mask.shape + (3,), v, np.float32) * (0.85 + 0.15 * z)[..., None]
    return _finish_sprite(col, mask * 0.9, rng.uniform(0, 360), rng)


def cut_sprite(img, x, y, w, h, margin=3, min_contrast=12):
    """Cut a real object out of a labelled photo as BGRA.

    Alpha from local darkness: droppings are darker than the floor around them.
    Returns None when the object is not clearly darker than its surroundings
    (light pellets, dark floors) - such crops would paste as a rectangle of floor.
    """
    H, W = img.shape[:2]
    x, y, w, h = int(x), int(y), int(w), int(h)
    x1, y1 = max(0, x - margin), max(0, y - margin)
    x2, y2 = min(W, x + w + margin), min(H, y + h + margin)
    patch = img[y1:y2, x1:x2].astype(np.float32)
    if patch.shape[0] < 3 or patch.shape[1] < 3:
        return None
    g = patch.mean(2)
    ring = np.concatenate([g[0], g[-1], g[:, 0], g[:, -1]])
    bg = np.median(ring)
    if bg - np.percentile(g, 10) < min_contrast:
        return None
    a = np.clip((bg - g - 8) / 25, 0, 1)
    yy, xx = np.mgrid[0:g.shape[0], 0:g.shape[1]]
    ell = (((xx - g.shape[1] / 2) / (g.shape[1] / 2)) ** 2 + ((yy - g.shape[0] / 2) / (g.shape[0] / 2)) ** 2) < 1.1
    a = cv2.GaussianBlur(a * ell, (0, 0), 0.6)
    return np.dstack([patch, a * 255]).astype(np.uint8)


def load_sprite_bank(folder):
    """User-supplied cut-outs: <folder>/<class_name>/*.png with alpha channel."""
    bank = {}
    folder = Path(folder)
    if not folder.exists():
        return bank
    for d in folder.iterdir():
        if not d.is_dir():
            continue
        items = []
        for p in sorted(d.glob("*.png")):
            im = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_UNCHANGED)
            if im is not None and im.ndim == 3 and im.shape[2] == 4:
                items.append((im[..., :3].astype(np.float32), im[..., 3].astype(np.float32) / 255))
        if items:
            bank[d.name] = items
    return bank


def _augment_bank_sprite(bgr, alpha, length_px, rng):
    cur = max(bgr.shape[:2])
    s = max(length_px, 3) / cur
    s *= SS  # go through _finish_sprite for rotation + AA
    big_c = cv2.resize(bgr, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
    big_a = cv2.resize(alpha, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
    big_c = big_c * rng.uniform(0.8, 1.2) + rng.normal(0, 6, 3)
    return _finish_sprite(big_c, np.clip(big_a, 0, 1), rng.uniform(0, 360), rng)


# --------------------------------------------------------------------------- compositing
def paste(img, bgr, alpha, x, y, rng, light=(1.0, 1.0), shadow=True):
    """Alpha-composite a sprite with top-left (x, y). Returns tight box or None."""
    h, w = alpha.shape
    H, W = img.shape[:2]
    if x < 0 or y < 0 or x + w > W or y + h > H:
        return None
    if shadow:
        # pad before blurring, otherwise the blur is cut at the sprite canvas and leaves a visible rectangle
        k = rng.uniform(0.15, 0.45)
        sig = max(0.6, 0.12 * max(h, w))
        p = int(np.ceil(3 * sig)) + 2
        sh = cv2.GaussianBlur(np.pad(alpha, p), (0, 0), sig)
        dx, dy = int(round(light[0] * max(1, 0.15 * w))), int(round(light[1] * max(1, 0.15 * h)))
        sx, sy = x + dx - p, y + dy - p
        ax1, ay1 = max(0, sx), max(0, sy)
        ax2, ay2 = min(W, sx + sh.shape[1]), min(H, sy + sh.shape[0])
        if ax2 > ax1 and ay2 > ay1:
            img[ay1:ay2, ax1:ax2] *= (1 - k * sh[ay1 - sy:ay2 - sy, ax1 - sx:ax2 - sx])[..., None]
    a = alpha[..., None]
    img[y:y + h, x:x + w] = img[y:y + h, x:x + w] * (1 - a) + bgr * a
    ys, xs = np.where(alpha > 0.35)
    if len(ys) == 0:
        return None
    return [x + xs.min(), y + ys.min(), x + xs.max() + 1, y + ys.max() + 1]


def _iou_any(box, boxes, thr):
    if not boxes:
        return False
    b = np.array(boxes, np.float32)[:, 1:]
    ix = np.clip(np.minimum(b[:, 2], box[2]) - np.maximum(b[:, 0], box[0]), 0, None)
    iy = np.clip(np.minimum(b[:, 3], box[3]) - np.maximum(b[:, 1], box[1]), 0, None)
    inter = ix * iy
    a1 = (box[2] - box[0]) * (box[3] - box[1])
    a2 = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return bool((inter / (a1 + a2 - inter + 1e-6) > thr).any())


# --------------------------------------------------------------------------- camera effects
def camera_effects(img, rng, ir_prob=0.3):
    h, w = img.shape[:2]
    # global illumination gradient + vignette
    gx, gy = rng.uniform(-0.25, 0.25, 2)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    illum = 1 + gx * (xx / w - 0.5) + gy * (yy / h - 0.5)
    r2 = ((xx - w / 2) / w) ** 2 + ((yy - h / 2) / h) ** 2
    illum *= 1 - rng.uniform(0, 0.6) * r2
    ir = rng.random() < ir_prob
    if ir:  # 940nm flood light: strong centre hotspot, fast falloff
        cx, cy = rng.uniform(0.3, 0.7) * w, rng.uniform(0.4, 0.9) * h
        illum *= 0.25 + 0.95 * np.exp(-(((xx - cx) / (0.5 * w)) ** 2 + ((yy - cy) / (0.6 * h)) ** 2))
    else:
        illum *= rng.uniform(0.7, 1.25)
        if rng.random() < 0.35:  # hard cast shadow (robot body, wall, post)
            m = np.zeros((h, w), np.float32)
            pts = np.stack([rng.uniform(0, w, 4), rng.uniform(0, h, 4)], 1).astype(np.int32)
            cv2.fillConvexPoly(m, cv2.convexHull(pts), 1)
            illum *= 1 - rng.uniform(0.25, 0.55) * cv2.GaussianBlur(m, (0, 0), rng.uniform(2, 15))
    img = img * illum[..., None]
    if ir:  # NoIR sensor under 940nm: near-monochrome with slight magenta cast
        g = img.mean(2, keepdims=True)
        img = g * np.array([rng.uniform(0.95, 1.05), rng.uniform(0.9, 1.0), rng.uniform(1.0, 1.08)], np.float32)
    # optics / motion
    if rng.random() < 0.5:
        img = cv2.GaussianBlur(img, (0, 0), rng.uniform(0.3, 1.3))
    if rng.random() < 0.3:  # patrol mode: robot moving while exposing
        k = int(rng.integers(3, 10))
        ker = np.zeros((k, k), np.float32)
        ker[k // 2] = 1 / k
        M = cv2.getRotationMatrix2D((k / 2 - 0.5, k / 2 - 0.5), rng.uniform(-20, 20), 1)
        ker = cv2.warpAffine(ker, M, (k, k))
        img = cv2.filter2D(img, -1, ker / max(ker.sum(), 1e-6))
    noise = rng.uniform(1, 4) * (2.5 if ir else 1)
    img = img + rng.standard_normal(img.shape).astype(np.float32) * noise
    img = np.clip(img, 0, 255).astype(np.uint8)
    q = int(rng.uniform(55, 95))
    img = cv2.imdecode(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])[1], cv2.IMREAD_COLOR)
    return img, ir


# --------------------------------------------------------------------------- frame generator
class SynthGenerator:
    def __init__(self, cfg, bg_dir=None, sprite_dir=None, seed=0):
        s = cfg["synth"]
        self.classes = cfg["classes"]
        self.W, self.H = s["frame"]
        self.gsd_range = s["gsd_mm_per_px"]
        self.ir_prob = s["ir_prob"]
        self.empty_prob = s["empty_prob"]
        self.rng = np.random.default_rng(seed)
        self.bg_paths = list_images(bg_dir) if bg_dir and Path(bg_dir).exists() else []
        self.bank = load_sprite_bank(sprite_dir) if sprite_dir else {}

    def _background(self):
        rng = self.rng
        if self.bg_paths and rng.random() < 0.7:
            im = imread(self.bg_paths[rng.integers(len(self.bg_paths))]).astype(np.float32)
            s = max(self.W / im.shape[1], self.H / im.shape[0]) * rng.uniform(1.0, 1.3)
            im = cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
            y0 = rng.integers(0, im.shape[0] - self.H + 1)
            x0 = rng.integers(0, im.shape[1] - self.W + 1)
            im = im[y0:y0 + self.H, x0:x0 + self.W]
            if rng.random() < 0.5:
                im = im[:, ::-1]
            return np.ascontiguousarray(im), 0
        fn = PROCEDURAL_BG[rng.integers(len(PROCEDURAL_BG))]
        img = fn(self.H, self.W, rng)
        floor = add_wall(img, rng) if rng.random() < 0.4 else 0
        return img, floor

    def _object(self, cls_name, length_px):
        rng = self.rng
        if cls_name in self.bank and rng.random() < 0.5:
            bgr, a = self.bank[cls_name][rng.integers(len(self.bank[cls_name]))]
            return _augment_bank_sprite(bgr, a, length_px, rng)
        if cls_name == "rodent_dropping":
            return make_dropping(rng, length_px)
        if cls_name == "feed_pellet":
            return make_pellet(rng, length_px)
        raise ValueError(f"no procedural sprite for class '{cls_name}' - add cut-outs under sprites/{cls_name}/")

    def _length_mm(self, cls_name):
        rng = self.rng
        if cls_name == "rodent_dropping":  # house mouse vs Norway rat
            return rng.uniform(3, 6.5) if rng.random() < 0.5 else rng.uniform(10, 20)
        return rng.uniform(3, 10)

    def frame(self):
        rng = self.rng
        img, floor = self._background()
        gsd = rng.uniform(*self.gsd_range)
        light = tuple(rng.uniform(-1, 1, 2))
        persp = lambda y: 0.55 + 0.45 * (y / self.H)  # top of frame is farther away

        def place(make, clustered, avoid_boxes, label=None):
            for _ in range(20):
                if clustered is not None:
                    cx, cy, sig = clustered
                    x, y = rng.normal(cx, sig), rng.normal(cy, sig * 0.6)
                else:
                    x, y = rng.uniform(0, self.W), rng.uniform(floor, self.H)
                if not (0 <= x < self.W and floor <= y < self.H):
                    continue
                bgr, a = make(persp(y))
                if a.size == 0:
                    return
                bx, by = int(x - a.shape[1] / 2), int(y - a.shape[0] / 2)
                cand = [bx, by, bx + a.shape[1], by + a.shape[0]]
                if label is not None and _iou_any(cand, avoid_boxes, 0.05):
                    continue
                if label is not None:  # an invisible object must not become a label
                    under = img[max(0, by):by + a.shape[0], max(0, bx):bx + a.shape[1]]
                    if under.shape[:2] != a.shape or np.abs((bgr - under).mean(2))[a > 0.5].mean() < 18:
                        continue
                box = paste(img, bgr, a, bx, by, rng, light)
                if box is not None and label is not None:
                    avoid_boxes.append([label] + box)
                return

        boxes = []
        # unlabelled look-alikes first so labelled objects sit on top of the clutter
        for _ in range(int(rng.uniform(20, 200))):
            place(lambda p: make_distractor(rng, gsd / p), None, boxes)
        if rng.random() >= self.empty_prob:
            for ci, cname in enumerate(self.classes):
                if cname == "feed_pellet" and rng.random() < 0.5:
                    continue  # pellets present in about half the frames
                for _ in range(int(rng.integers(1, 5))):
                    cl = (rng.uniform(0, self.W), rng.uniform(floor, self.H), rng.uniform(20, 250))
                    for _ in range(int(rng.integers(2, 20))):
                        mm = self._length_mm(cname)
                        place(lambda p, mm=mm, cname=cname: self._object(cname, max(4.0, mm / gsd * p)), cl, boxes, ci)
        out, ir = camera_effects(img, rng, self.ir_prob)
        b = np.array(boxes, np.float32).reshape(-1, 5)
        return out, b, {"gsd": float(gsd), "ir": bool(ir), "floor": int(floor)}
