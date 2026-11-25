"""The CommonRoad road as a BeamNG road: decal roads (a polyline of (x, y, z, width) nodes and a material)
on a BeamNG level, in the CommonRoad x, y coordinates, so a position means the same in both simulators.
Only the height differs: everything sits on the level's ground at z = LEVELS[level]["z"].

A layout is plain JSON: one asphalt decal under all lanes, a solid line on each outer edge and a dashed
line between neighbouring lanes (one short decal per dash). The road is extended straight beyond both
ends of the lanelets, so cars can keep driving after the plan ends. beamngpy is only imported when the
layout is added to a scenario.
"""
import json

import numpy as np

# Levels and the road materials that exist in them (BeamNG.tech 0.38.5). gridmap_v2 is flat at 56.23 m for
# x in [-400, 500], y in [-100, 300], with buildings in the background. Its terrain only exists with a
# renderer. smallgrid is a bare grid at z = 0 and crashes without a renderer.
LEVELS = {
    "gridmap_v2": {"z": 56.2347, "asphalt": "m_road_asphalt_rough_01", "line": "m_gm_line"},
    "smallgrid": {"z": 0.0, "asphalt": "a_asphalt_01_a", "line": "misc_markings_01"},
}
LEVEL = "gridmap_v2"
LINE_WIDTH = 0.15
DASH, GAP = 3.0, 6.0          # dashed lane lines, metres


def _extend(polyline, before, after):
    """A polyline extended straight by `before` metres at its start and `after` metres at its end."""
    p = np.asarray(polyline, float)
    d0 = (p[1] - p[0]) / np.linalg.norm(p[1] - p[0])
    d1 = (p[-1] - p[-2]) / np.linalg.norm(p[-1] - p[-2])
    return np.vstack([p[0] - before * d0, p, p[-1] + after * d1])


def _nodes(polyline, width, z):
    return [[float(x), float(y), z, float(width)] for x, y in polyline]


def _dashes(polyline):
    """The dashes of a dashed line along a polyline, each a two-point polyline."""
    p = np.asarray(polyline, float)
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    at = lambda d: np.array([np.interp(d, s, p[:, 0]), np.interp(d, s, p[:, 1])])
    return [np.array([at(d), at(d + DASH)]) for d in np.arange(0, s[-1] - DASH, DASH + GAP)]


def road_layout(scenario, level=LEVEL, before=50.0, after=300.0):
    """The decal roads of a CommonRoad scenario's lanelet network. Assumes the lanelets are side by side
    (one lanelet per lane, as in threelanes.xml)."""
    cfg = LEVELS[level]
    z = cfg["z"]
    lanelets = scenario.lanelet_network.lanelets
    left = [l for l in lanelets if l.adj_left is None][0]
    right = [l for l in lanelets if l.adj_right is None][0]
    centre = (left.left_vertices + right.right_vertices) / 2
    width = float(np.linalg.norm(left.left_vertices[0] - right.right_vertices[0]))
    roads = [{"name": "asphalt", "material": cfg["asphalt"], "nodes": _nodes(_extend(centre, before, after), width + 1.0, z)}]
    edges = [(f"edge_{left.lanelet_id}", left.left_vertices), (f"edge_{right.lanelet_id}", right.right_vertices)]
    for name, bound in edges:
        roads.append({"name": name, "material": cfg["line"], "nodes": _nodes(_extend(bound, before, after), LINE_WIDTH, z)})
    for l in lanelets:
        if l.adj_left is not None:
            for k, dash in enumerate(_dashes(_extend(l.left_vertices, before, after))):
                roads.append({"name": f"dash_{l.lanelet_id}_{k}", "material": cfg["line"],
                              "nodes": _nodes(dash, LINE_WIDTH, z)})
    return {"level": level, "z": z, "lane_width": width / len(lanelets), "roads": roads}


def save_layout(layout, path):
    with open(path, "w") as f:
        json.dump(layout, f, indent=1)


def add_to_scenario(bng_scenario, layout):
    """Add the decal roads of a layout to a beamngpy Scenario (before scenario.make). beamngpy sets each
    road's render priority to its index, and a lower priority is drawn on top, so the asphalt goes last
    (first, it covered every line). The lines are not drivable roads for BeamNG's AI."""
    from beamngpy import Road
    for r in sorted(layout["roads"], key=lambda r: r["name"] == "asphalt"):
        asphalt = r["name"] == "asphalt"
        road = Road(r["material"], rid=r["name"], interpolate=False, drivability=1 if asphalt else -1)
        road.add_nodes(*[tuple(n) for n in r["nodes"]])
        bng_scenario.add_road(road)
