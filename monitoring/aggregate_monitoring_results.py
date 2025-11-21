import os
import csv
import json
import click
import math


@click.command()
@click.argument("parent_folder", type=click.Path(exists=True, file_okay=False))
@click.argument("blueprint_folder", required=False, type=click.Path(file_okay=False))
def aggregate_monitoring_results(parent_folder: str, blueprint_folder: str | None):
    """
    Aggregate monitoring results in parent_folder.

    If blueprint_folder is given, it defines ALL expected experiment IDs.
    If omitted, the experiment IDs are taken from parent_folder itself.
    """
    # decide where to get the list of expected experiments
    source_folder = blueprint_folder if blueprint_folder is not None else parent_folder


    expected = sorted(
        d for d in os.listdir(source_folder)
        if not d.startswith('_')
        and d != "summary_log.json"
        and os.path.isdir(os.path.join(source_folder, d))
    )

    if blueprint_folder:
        expected = ["scenario_"+ entry for entry in expected]


    runs = {}  # name -> {"cost": float | None, "has_folder": bool, "has_csv": bool}

    for name in expected:
        gen_folder = os.path.join(parent_folder, name)
        result_path = os.path.join(gen_folder, "monitoring_results.csv")

        has_folder = os.path.isdir(gen_folder)
        has_csv = os.path.isfile(result_path)
        cost = None

        if has_folder and has_csv:
            print(f"Aggregating: {os.path.abspath(gen_folder)}")
            with open(result_path, mode="r", newline="") as f:
                reader = csv.DictReader(f)
                last_row = None
                for row in reader:
                    last_row = row
                if last_row is not None:
                    fin = reader.fieldnames[-1]
                    cost = float(last_row[fin])
        else:
            if not has_folder:

                print(f"Missing folder for experiment '{name}' under {parent_folder}")
            elif not has_csv:
                print(f"Missing monitoring_results.csv in {os.path.abspath(gen_folder)}")

        runs[name] = {"cost": cost, "has_folder": has_folder, "has_csv": has_csv}

    num_runs = len(expected)
    successful_costs = [r["cost"] for r in runs.values() if r["cost"] is not None]

    total_cost = sum(successful_costs)
    num_successful = len(successful_costs)
    num_perfect = sum(
        1
        for r in runs.values()
        if r["cost"] is not None and math.isclose(r["cost"], 0.0, abs_tol=1e-3)
    )
    num_timeout = num_runs-num_successful

    positive_traces = sorted(
        name for name, r in runs.items()
        if r["cost"] is not None and math.isclose(r["cost"], 0.0, abs_tol=1e-3)
    )
    negative_traces = sorted(
        name for name, r in runs.items()
        if r["cost"] is not None and not math.isclose(r["cost"], 0.0, abs_tol=1e-3)
    )
    no_monitoring_results = sorted(
        name for name, r in runs.items()
        if r["cost"] is None
    )

    assert(len(positive_traces) == num_perfect)
    assert(len(negative_traces) == num_successful-num_perfect)
    assert(len(no_monitoring_results) == num_timeout)

    summary = {
        "total_runs": num_runs,
        "num_positive_traces": num_perfect,
        "successful_runs": num_successful,
        "num_timeout":num_timeout,
        "percent_positive_traces": (num_perfect / num_runs * 100) if num_runs else float("nan"),
        "average_cost": total_cost / num_successful if num_successful else float("nan"),
        "positive traces": positive_traces,
        "negative traces": negative_traces,
        "no monitoring results": no_monitoring_results,
        "costs": {name: r["cost"] for name, r in runs.items()},
    }

    with open(os.path.join(parent_folder, "summary_log.json"), "w") as f:
        json.dump(summary, f, indent=2)

    return summary


if __name__ == "__main__":
    aggregate_monitoring_results()
