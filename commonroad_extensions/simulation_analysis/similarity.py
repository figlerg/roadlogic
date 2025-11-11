import os
import pickle
import click
import numpy as np
import matplotlib.pyplot as plt

from commonroad_extensions.plan_execution.map_plan import compute_similarity_matrix, get_covered_cell



@click.command()
@click.option(
    "--plans-folder",
    type=click.Path(exists=True, file_okay=False),
    required=True,
    help="Folder containing pickled plan models (.pkl).",
)
@click.option(
    "--output-folder",
    type=click.Path(file_okay=False),
    required=True,
    help="Folder where similarity matrix and plot will be saved.",
)
def main(plans_folder: str, output_folder: str):
    """Compute and visualize pairwise similarity matrix for all plans in a folder."""
    os.makedirs(output_folder, exist_ok=True)

    plan_files = sorted(f for f in os.listdir(plans_folder) if f.endswith(".pkl"))
    if not plan_files:
        click.echo(f"No .pkl plans found in {plans_folder}")
        return

    plans = []
    for name in plan_files:
        with open(os.path.join(plans_folder, name), "rb") as f:
            plans.append(pickle.load(f))

    click.echo(f"Loaded {len(plans)} plans from {plans_folder}")

    matrix = compute_similarity_matrix(plans, up_to_time=float("inf"))

    matrix_txt = os.path.join(output_folder, "similarity_matrix.txt")
    np.savetxt(matrix_txt, matrix, fmt="%.3f")

    matrix_png = os.path.join(output_folder, "similarity_matrix.png")
    plt.imshow(matrix, vmin=0.0, vmax=1.0, cmap="hot", interpolation="nearest")
    plt.colorbar(label="IoU Similarity")
    plt.title("Plan Similarity Matrix")
    plt.tight_layout()
    plt.savefig(matrix_png, dpi=200)
    plt.close()

    click.echo(f"Saved similarity matrix to {matrix_txt}")
    click.echo(f"Saved heatmap to {matrix_png}")


if __name__ == "__main__":
    main()
