#!/usr/bin/env python3
"""ukraine_lowpoly.svg -> +#cities layer (обласні центри, контур-кружечки).

Київ (raion-14), Харків (raion-1293), Запоріжжя (raion-564) вже існують
геометрично як окремі raion-полігони в базовій мапі — виділяємо їх СВОЇМ
контуром (не колом): для Києва raion data-id="14" колізує з oblast id, тому
дублюємо з data-id=regionId; Харків/Запоріжжя вже мають data-id==regionId,
дублюємо як є (для однакового вигляду/класу city в усіх трьох).
Решта 22 обласних центри не мають окремого полігону в джерельних даних ->
малюємо коло.
"""

import re
import numpy as np
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union, nearest_points

SRC = "/Users/artem/Documents/Projects/jaam_server/design/ukraine_lowpoly.svg"
OUT = "/Users/artem/Documents/Projects/jaam_server/design/ukraine_lowpoly_with_cities.svg"
R = 2.3  # цільовий радіус, viewBox-одиниці (~ реальний "відбиток" Харкова/Запоріжжя у цьому масштабі)

# oblast-id (data-oblast у ukraine_lowpoly.svg) -> (lon, lat) "location" ОБЛАСТІ
# (не міста!) з regions.json — калібрувальні точки для lon/lat -> viewBox проєкції.
CALIB = {
    3: (27.0635998, 49.268624),
    4: (28.516068, 48.8990315),
    5: (26.5208033, 51.2074112),
    8: (24.6627893, 51.5451167),
    9: (34.9501715, 48.662589),
    10: (28.3867504, 50.9080532),
    11: (23.4466092, 48.2953664),
    12: (35.922969, 47.4165079),
    13: (24.5207477, 48.7481718),
    14: (30.4924884, 50.178595),
    15: (31.6902953, 48.1916774),
    16: (38.9150477, 49.2724587),
    17: (31.9442334, 47.3886032),
    18: (29.9567193, 46.1147226),
    19: (33.7498787, 49.8607809),
    20: (34.3289305, 50.7696518),
    21: (25.6167516, 49.6630002),
    22: (36.3788957, 49.8299582),
    23: (33.4079326, 46.5421715),
    24: (31.2271744, 49.1460165),
    25: (31.7417235, 51.272593),
    26: (26.1081673, 48.3810791),
    27: (23.8266948, 49.6512234),
    28: (37.7809825, 47.9212914),
}

# oblast-id -> (regionId з regions.json *-CITY запису, назва, lat, lon міста)
# Харків(22)/Запоріжжя(12)/Київ(14) НЕ тут — обробляються окремо (див. докстрінг).
CITIES = {
    3: (1400, "Хмельницький", 49.4229, 26.9871),
    4: (155, "Вінниця", 49.2331, 28.4682),
    5: (1133, "Рівне", 50.6199, 26.2516),
    8: (225, "Луцьк", 50.7472, 25.3254),
    9: (332, "Дніпро", 48.4647, 35.0462),
    10: (442, "Житомир", 50.2547, 28.6587),
    11: (500, "Ужгород", 48.6208, 22.2879),
    13: (632, "Івано-Франківськ", 48.9226, 24.7111),
    15: (761, "Кропивницький", 48.5079, 32.2623),
    16: (7615, "Луганськ", 48.5740, 39.3078),
    17: (926, "Миколаїв", 46.9750, 31.9946),
    18: (964, "Одеса", 46.4825, 30.7233),
    19: (1060, "Полтава", 49.5883, 34.5514),
    20: (1187, "Суми", 50.9077, 34.7981),
    21: (1241, "Тернопіль", 49.5535, 25.5948),
    23: (1370, "Херсон", 46.6354, 32.6169),
    24: (1473, "Черкаси", 49.4444, 32.0598),
    25: (1591, "Чернігів", 51.4982, 31.2893),
    26: (1542, "Чернівці", 48.2921, 25.9358),
    27: (845, "Львів", 49.8397, 24.0297),
    28: (53, "Донецьк", 48.0159, 37.8028),
    9999: (7926, "Сімферополь", 44.9521, 34.1024),
}

# oblast-id -> (raion-id з ukraine_lowpoly.svg, regionId з regions.json, назва)
# — міста, що вже мають власний raion-полігон у базовій мапі.
OUTLINE_CITIES = {
    14: (31, 31, "Київ"),  # raion-31 у ukraine_lowpoly.svg (lowpoly.py RAION_ID_REMAP: 14->31)
    22: (1293, 1293, "Харків"),
    12: (564, 564, "Запоріжжя"),
}


def oblast_geom(txt, oid):
    m = re.search(rf'<g class="oblast" id="oblast-{oid}"[^>]*>(.*?)</g>', txt, re.S)
    pts_all = re.findall(r'points="([^"]+)"', m.group(1))
    polys = [Polygon([tuple(map(float, p.split(","))) for p in pts.split()]) for pts in pts_all]
    return unary_union(polys)


def fit_projection(txt):
    """lon/lat -> viewBox affine fit по 24 калібрувальних точках (least squares)."""
    geoms = {oid: oblast_geom(txt, oid) for oid in CALIB}
    lon = np.array([CALIB[o][0] for o in CALIB])
    lat = np.array([CALIB[o][1] for o in CALIB])
    sx = np.array([geoms[o].centroid.x for o in CALIB])
    sy = np.array([geoms[o].centroid.y for o in CALIB])
    A = np.column_stack([lon, lat, np.ones_like(lon)])
    cx, *_ = np.linalg.lstsq(A, sx, rcond=None)
    cy, *_ = np.linalg.lstsq(A, sy, rcond=None)
    return geoms, lambda lo, la: (cx[0] * lo + cx[1] * la + cx[2], cy[0] * lo + cy[1] * la + cy[2])


def fit_circle(geom, want_pt, r):
    """Найбільший радіус <= r, що повністю влазить у geom, центр максимально
    близько до want_pt. Якщо область вужча за r — бінарний пошук меншого радіуса."""
    eroded = geom.buffer(-r)
    if not eroded.is_empty:
        c = want_pt if eroded.contains(want_pt) else nearest_points(eroded, want_pt)[0]
        return c.x, c.y, r
    lo, hi, best = 0.05, r, None
    for _ in range(25):
        mid = (lo + hi) / 2
        e = geom.buffer(-mid)
        if not e.is_empty:
            best, lo = e, mid
        else:
            hi = mid
    if best is None:
        return want_pt.x, want_pt.y, 0.3
    c = want_pt if best.contains(want_pt) else nearest_points(best, want_pt)[0]
    return c.x, c.y, lo


def main():
    txt = open(SRC, encoding="utf-8").read()
    geoms, project = fit_projection(txt)
    geoms[9999] = oblast_geom(txt, 9999)

    rows = []
    for oid, (region_id, name, la, lo) in CITIES.items():
        x0, y0 = project(lo, la)
        g = geoms[oid]
        pt = Point(x0, y0)
        if not g.contains(pt):
            pt = nearest_points(g, pt)[0]
        x, y, r = fit_circle(g, pt, R)
        rows.append((oid, region_id, name, x, y, r))

    bad = [
        (rows[i][2], rows[j][2])
        for i in range(len(rows))
        for j in range(i + 1, len(rows))
        if ((rows[i][3] - rows[j][3]) ** 2 + (rows[i][4] - rows[j][4]) ** 2) ** 0.5 < rows[i][5] + rows[j][5]
    ]
    if bad:
        raise SystemExit(f"circle overlap: {bad}")

    markers = "\n".join(
        f'    <g class="city" data-oblast="{oid}" data-id="{region_id}"><title>{name}</title>'
        f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}"/></g>'
        for oid, region_id, name, x, y, r in rows
    )

    outline_blocks = []
    for oid, (raion_id, region_id, name) in OUTLINE_CITIES.items():
        m = re.search(rf'<g class="raion" id="raion-{raion_id}"[^>]*>(.*?)</g>', txt, re.S)
        polys = re.findall(r'<polygon points="([^"]+)"/>', m.group(1))
        outline_blocks.append(
            "\n".join(
                f'    <g class="city" data-oblast="{oid}" data-id="{region_id}"><title>{name}</title>'
                f'<polygon points="{p}"/></g>'
                for p in polys
            )
        )
    outlines = "\n".join(outline_blocks)

    city_layer = f"""<g id="cities">
<style>
  #cities .city circle, #cities .city polygon{{fill:none;stroke:var(--ua-line,#b8b8b4);stroke-width:.15;stroke-linejoin:round}}
</style>
{markers}
{outlines}
</g>
"""
    open(OUT, "w", encoding="utf-8").write(txt.replace("</svg>", city_layer + "</svg>"))
    print(f"cities: {len(rows)} кола + {len(OUTLINE_CITIES)} контури (Київ/Харків/Запоріжжя)")
    print(f"out: {OUT}")


if __name__ == "__main__":
    main()
