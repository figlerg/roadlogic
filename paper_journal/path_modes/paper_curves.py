"""The same first-k curve for the paper's variability runs, rerun with run_variability.sh (its similarity
matrices and timings are kept in paper_rerun/, the rest of out/ is not committed): the mean
similarity of the first k plans in their sampling order, and k times the mean planning time per plan
(the script only logs the total). Prints one JSON line per experiment.

    python paper_journal/path_modes/paper_curves.py
"""
import json, os
import numpy as np

for exp in ["exp_001_b", "exp_002_b", "exp_003_b", "exp_005_b", "exp_006_b", "exp_007_b"]:
    d = os.path.join("paper_journal", "path_modes", "paper_rerun")  # copied from out/<exp> by hand
    m = np.loadtxt(os.path.join(d, f"{exp}_similarity_matrix.txt"))
    per_plan = json.load(open(os.path.join(d, f"{exp}_times.json")))["planning_seconds"] / len(m)
    curve = {k: [round(float(m[:k, :k][~np.eye(k, dtype=bool)].mean()), 3), round(k * per_plan, 1)]
             for k in (5, 10, 20, 30, 40, 50) if len(m) >= k}
    print(json.dumps({"spec": exp[:-2], "method": "paper_restarts", "plans": len(m),
                      "mean_similarity": round(float(m[~np.eye(len(m), dtype=bool)].mean()), 3),
                      "seconds_per_plan": round(per_plan, 2), "curve": curve}))
