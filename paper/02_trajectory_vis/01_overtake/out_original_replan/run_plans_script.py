from pathlib import Path
from planning.asp.generate_plans import generate_plans, visualize_plans

# paths
base = Path("paper/02_trajectory_vis/01_overtake/out/asp")
out_path = "paper/02_trajectory_vis/01_overtake/out_test"

# parameters
diversity_step = 20
n = 3

# collect ASP files (clingo needs strings)
files = [str(f) for f in base.iterdir() if f.is_file()]

# generate models (override avoids constant redefinition)
models = generate_plans(
    files=files,
    n=diversity_step * n,
    save_path=out_path,
    deterministic=True,
    override_files=True,
)

# optional filtering for diversity
models_filtered = models[::diversity_step]

# visualize
visualize_plans(
    models_filtered,
    save=True,
    show=False,
    save_path=out_path,
    max_num=n,
)
