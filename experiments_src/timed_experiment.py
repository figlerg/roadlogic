

import time

def timed_experiment(scenario_path: str, out_dir: str, max_time_sec: float = 60.0, max_models: int = 100, discard_steps: int = 0):
    """Standardized per-scenario experiment. Runs until a positive trace is found according to the spec monitor."""

    # TODO Setup experiment folders and result dict

    # TODO Initialize ASP control (keep alive)

    start_time = time.time()
    model_idx = 0

    while True:
        # TODO Check time and model limits

        # TODO Get next model from ASP

        # TODO Optionally skip N models according to discard_steps

        # TODO Extract plan from model

        # TODO Simulate plan in CommonRoad

        # TODO Monitor simulation results

        # TODO Save results, artifacts, logs

        # TODO Break if goal satisfied or timeout reached
        pass

    # TODO Compute summary stats, save JSON result


