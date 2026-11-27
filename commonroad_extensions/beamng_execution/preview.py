"""Export the BeamNG road and the BeamNG mapping of one plan as JSON, and draw both from the files.

    python -m commonroad_extensions.beamng.preview <plan.pkl> <out folder>
    python -m commonroad_extensions.beamng.preview paper_journal/benchmark/out/exp_004/serialized_models/0002.pkl demo_output/beamng

Writes road.json, plan_beamng.json and preview.png into the out folder. The figure shows the decal roads
and each car's script, a dot per second labelled with its time, and the spawn pose.
"""
import json
import os
import pickle
import sys
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CR_SCENARIO = os.path.join(ROOT, "cr_scenarios", "threelanes.xml")


def export(plan_pkl, out):
    """Generation: road.json and plan_beamng.json from a stored plan."""
    from commonroad.common.file_reader import CommonRoadFileReader
    from commonroad_extensions.beamng_execution.road import road_layout, save_layout
    from commonroad_extensions.plan_execution.map_plan import map_plan_beamng
    os.makedirs(out, exist_ok=True)
    scenario, _ = CommonRoadFileReader(CR_SCENARIO).open()
    save_layout(road_layout(scenario), os.path.join(out, "road.json"))
    with open(plan_pkl, "rb") as f:
        plan = pickle.load(f)
    map_plan_beamng(scenario, plan, anchor_lane_idx=1, save_path=os.path.join(out, "plan_beamng.json"))


def plot(out, xlim=(-20, 120)):
    """Plotting: reads the two JSON files only."""
    import matplotlib.pyplot as plt
    road = json.load(open(os.path.join(out, "road.json")))
    plan = json.load(open(os.path.join(out, "plan_beamng.json")))
    fig, ax = plt.subplots(figsize=(10, 2.6))
    for r in road["roads"]:
        x, y = [n[0] for n in r["nodes"]], [n[1] for n in r["nodes"]]
        if r["name"] == "asphalt":
            w = r["nodes"][0][3]
            ax.fill_between(x, [v - w / 2 for v in y], [v + w / 2 for v in y], color="0.85", lw=0)
        else:
            ax.plot(x, y, color="0.3", lw=1, ls="-" if r["material"].endswith("white") else "--")
    for k, (name, a) in enumerate(plan["agents"].items()):
        c = f"C{k}"
        ax.plot(a["spawn"]["x"], a["spawn"]["y"], "s", color=c, ms=8, label=f"{name}" + (" (static)" if a["static"] else ""))
        pts = [p for p in a["script"] if abs(p["t"] - round(p["t"])) < 1e-6]
        ax.plot([p["x"] for p in a["script"]], [p["y"] for p in a["script"]], color=c, lw=1.2)
        ax.plot([p["x"] for p in pts], [p["y"] for p in pts], "o", color=c, ms=3)
        last = None
        for p in pts:
            if p["t"] <= plan["plan_end"] and (last is None or abs(p["x"] - last) > 3):
                last = p["x"]
                ax.annotate(f"{p['t']:.0f}", (p["x"], p["y"]), textcoords="offset points",
                            xytext=(0, 5 if k == 0 else -10), ha="center", fontsize=7, color=c)
    ax.axvline(-10, color="0.6", lw=0.6, ls=":")
    ax.axvline(100, color="0.6", lw=0.6, ls=":")
    ax.set_xlim(*xlim)
    ax.set_aspect("equal")
    ax.set_xlabel("x [m] (dotted: end of the CommonRoad lanelets)")
    ax.set_ylabel("y [m]")
    ax.legend(loc="upper left", fontsize=7, ncol=3, bbox_to_anchor=(0, 1.35))
    fig.tight_layout()
    fig.savefig(os.path.join(out, "preview.png"), dpi=160, bbox_inches="tight")


if __name__ == "__main__":
    warnings.simplefilter("ignore")
    sys.path.insert(0, ROOT)
    export(sys.argv[1], sys.argv[2])
    plot(sys.argv[2])
    print("wrote", sys.argv[2])
