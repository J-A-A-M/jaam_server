#!/usr/bin/env python3
"""states.svg / districts.svg -> low-poly SVG via mapshaper.

mapshaper snaps coincident vertices and runs a topology-aware Visvalingam
simplify across the whole layer, so neighbouring raions/oblasts share one arc
per border — borders coincide exactly, simplify identically, fewer sharp angles.
id per raion is preserved for individual alert highlighting.
"""

import re
import sys
import json
import subprocess
from svgpathtools import parse_path, Line
from shapely.geometry import Polygon, MultiPolygon, shape, mapping
from shapely.ops import unary_union

sys.setrecursionlimit(100000)

SRC_DIST = "/tmp/districts.svg"
SRC_STATE = "/tmp/states.svg"
OUT = "/Users/artem/Documents/Projects/jaam_server/design/ukraine_lowpoly.svg"

BEZIER_SAMPLES = 10  # dense sampling -> mapshaper has good detail to snap+simplify
SIMPLIFY_PCT = 4  # % of vertices kept (lower = lower poly)
SNAP = 0.18  # vertex snap interval (viewBox units) to merge shared borders

# districts.svg дає Києву district-id "14" — колізує з oblast id Київської
# області (теж 14). Живі тривоги Ukraine Alarm API шлють для м.Київ regionId
# 31 (звірено з data/uaapi.json: "regionId":"31","regionName":"м. Київ"), тому
# resolveRegionElements() у клієнтському JS (#raion-31 / [data-oblast="31"])
# нічого не знаходить і тривога на мапі не підсвічується. Ремапаємо id
# районів на реальний Ukraine Alarm regionId ПІСЛЯ симпліфікації.
RAION_ID_REMAP = {"14": "31"}


def flatten_rings(d):
    """path d -> list of closed coordinate rings (one per continuous subpath)."""
    path = parse_path(d)
    rings = []
    for sp in path.continuous_subpaths():
        cur = []
        for seg in sp:
            samp = (
                [seg.start, seg.end]
                if isinstance(seg, Line)
                else [seg.point(t / BEZIER_SAMPLES) for t in range(BEZIER_SAMPLES + 1)]
            )
            for p in samp:
                xy = (round(p.real, 3), round(p.imag, 3))
                if not cur or cur[-1] != xy:
                    cur.append(xy)
        if len(cur) >= 3:
            rings.append(cur)
    return rings


def extract(src, keep_class=None):
    txt = open(src, encoding="utf-8").read()
    out = []
    for m in re.finditer(r'<path\b([^>]*?)\bd="([^"]+)"', txt, re.S):
        attrs, d = m.group(1), m.group(2)
        idm = re.search(r'\bid="([^"]+)"', attrs)
        clm = re.search(r'\bclass="([^"]+)"', attrs)
        if not idm:
            continue
        if keep_class and keep_class not in (clm.group(1).split() if clm else []):
            continue
        out.append((idm.group(1), d))
    return out


def geom_for(paths):
    """id -> shapely geometry (union of its rings)."""
    by_id = {}
    for rid, d in paths:
        polys = []
        for ring in flatten_rings(d):
            p = Polygon(ring)
            if not p.is_valid:
                p = p.buffer(0)
            if not p.is_empty and p.area > 0:
                polys.append(p)
        if not polys:
            continue
        g = unary_union(polys) if len(polys) > 1 else polys[0]
        if rid in by_id:
            g = unary_union([by_id[rid], g])
        by_id[rid] = g
    return by_id


def rings_to_svg(geom, cls, rid, oblast=None):
    def poly_pts(poly):
        return " ".join(f"{round(x, 2)},{round(y, 2)}" for x, y in poly.exterior.coords)

    polys = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
    ob = f' data-oblast="{oblast}"' if oblast is not None else ""
    rows = [f'  <g class="{cls}" id="{cls}-{rid}" data-id="{rid}"{ob}>']
    for poly in polys:
        if not poly.is_empty:
            rows.append(f'    <polygon points="{poly_pts(poly)}"/>')
    rows.append("  </g>")
    return "\n".join(rows)


def to_featurecollection(data):
    feats = []
    for fid, geom in data.items():
        feats.append({"type": "Feature", "properties": {"fid": fid}, "geometry": mapping(geom)})
    return {"type": "FeatureCollection", "features": feats}


def mapshaper_layer(geoms):
    """Simplify one set of non-overlapping geoms as a single topological layer:
    neighbours share one arc per border. Returns {id: shapely geom}.
    (raions and oblasts must NOT be mixed — oblasts overlap raions and -clean
    would then delete raions.)"""
    fc = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {"fid": k}, "geometry": mapping(v)} for k, v in geoms.items()],
    }
    json.dump(fc, open("/tmp/ua_in.geojson", "w"))
    subprocess.run(
        [
            "mapshaper",
            "/tmp/ua_in.geojson",
            "-snap",
            f"interval={SNAP}",
            "-simplify",
            f"{SIMPLIFY_PCT}%",
            "keep-shapes",
            "weighted",
            "-clean",
            "-o",
            "format=geojson",
            "/tmp/ua_out.geojson",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    out = json.load(open("/tmp/ua_out.geojson"))
    return {f["properties"]["fid"]: shape(f["geometry"]) for f in out["features"] if f.get("geometry")}


def main():
    raions = geom_for(extract(SRC_DIST))
    oblasts_src = geom_for(extract(SRC_STATE, keep_class="stateObject"))  # incl 9999 = Крим

    # raion -> oblast via centroid containment (used to derive coincident borders)
    r2o = {}
    for rk, rg in raions.items():
        c = rg.representative_point()
        for ok, og in oblasts_src.items():
            if og.contains(c):
                r2o[rk] = ok
                break

    # areas with NO raions (occupied / Crimea) at FULL resolution = oblast minus
    # raion coverage. buffer(0.15) < SNAP eats thin slivers along controlled-raion
    # borders; feeding these into the SAME mapshaper layer as raions lets snap
    # merge their borders with neighbour raions -> coincident.
    raion_union_raw = unary_union(list(raions.values()))
    occupied_raw = {}
    for ok, og in oblasts_src.items():
        gap = og.difference(raion_union_raw.buffer(0.15)).buffer(0)
        pieces = [p for p in (gap.geoms if isinstance(gap, MultiPolygon) else [gap]) if p.area > 1.0]
        if pieces:
            occupied_raw[ok] = unary_union(pieces)

    # one shared layer: raions + occupied -> all borders snap & simplify together
    layer = dict(raions)
    layer.update({f"occ{ok}": g for ok, g in occupied_raw.items()})
    simp_all = mapshaper_layer(layer)

    simp = {k: v for k, v in simp_all.items() if not k.startswith("occ")}
    occupied = {k[3:]: v for k, v in simp_all.items() if k.startswith("occ")}

    # recover any raion mapshaper dropped (tiny city raions) — light independent simplify
    recovered = 0
    for rk, rg in raions.items():
        if rk not in simp:
            g = rg.simplify(0.25, preserve_topology=True)
            if not g.is_empty:
                simp[rk] = g
                recovered += 1

    # oblast borders by dissolving SIMPLIFIED raions + occupied -> coincident & complete
    ob = {}
    for rk, g in simp.items():
        ok = r2o.get(rk)
        if ok:
            ob.setdefault(ok, []).append(g)
    for ok, g in occupied.items():
        ob.setdefault(ok, []).append(g)
    oblasts = {ok: unary_union(gs) for ok, gs in ob.items()}

    rsvg, osvg, vcount = [], [], 0
    for rk, g in simp.items():
        rsvg.append(rings_to_svg(g, "raion", RAION_ID_REMAP.get(rk, rk), oblast=r2o.get(rk)))
        polys = g.geoms if isinstance(g, MultiPolygon) else [g]
        vcount += sum(len(p.exterior.coords) for p in polys)
    # occupied / no-raion areas: fillable + highlightable; oblast == own id
    for ok, g in occupied.items():
        rsvg.append(rings_to_svg(g, "raion", ok, oblast=ok))
    for ok, g in oblasts.items():
        osvg.append(rings_to_svg(g, "oblast", ok))

    doc = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 175" id="uaLowpoly">
<style>
  .raion polygon{{fill:var(--ua-fill,#d9d9d6);stroke:var(--ua-line,#b8b8b4);stroke-width:.15;stroke-linejoin:round}}
  .raion.alert polygon{{fill:var(--ua-alert,#F5601A);stroke:var(--ua-alert-line,#c24410)}}
  .oblast polygon{{fill:none;stroke:var(--ua-border,#7a7a76);stroke-width:.4;stroke-linejoin:round;pointer-events:none}}
</style>
<g id="raions">
{chr(10).join(rsvg)}
</g>
<g id="oblasts">
{chr(10).join(osvg)}
</g>
</svg>
"""
    open(OUT, "w", encoding="utf-8").write(doc)
    print(f"raions: {len(simp)}/124 (recovered {recovered}), avg verts " f"{vcount // max(len(simp), 1)}")
    print(f"oblasts: {len(osvg)}")
    print(f"out: {OUT} ({len(doc)} bytes)  SIMPLIFY={SIMPLIFY_PCT}% SNAP={SNAP}")


if __name__ == "__main__":
    main()
