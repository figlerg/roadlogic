# we create many variations of parameter combinations (for constants)

import os
from partition import partition, default_dict
from itertools import product
import click

import random

random.seed(42)

script_dir = os.path.dirname(os.path.abspath(__file__))
default_out_folder = os.path.join(script_dir, "variability_experiments_instances")


@click.command()
@click.option('--output-folder', type=click.Path(), required=True, default=default_out_folder)
@click.option('--n', type=int, default=10)
def vary_params(output_folder: str, n:int):
    """
    Main experiment:
    - Varies interval constants by partitioning their min/max range.
    - Varies certain scalar constants by ±2.
    - Keeps some constants fixed.
    """
    print(output_folder)
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # === Define constant categories ===

    interval_constants = [("min_change_speed", "max_change_speed")]
    scalar_constants = ["max_acceleration_while_turning","max_braking_speed_while_turning","safety_distance"]
    fixed_constants = ["max_lane", "max_segment","change_dur"]
    list_constants = [("init_distance", [11,18])]

    # === Prepare values to iterate ===

    # Build subranges for interval-like constants
    interval_variants = []
    for min_key, max_key in interval_constants:
        min_val = default_dict[min_key]
        max_val = default_dict[max_key]
        subranges = split_interval(min_val, max_val, parts=3)
        interval_variants.append([(min_key, max_key, lo, hi) for (lo, hi) in subranges])

    # Build value lists for scalar constants
    scalar_variants = []
    for key in scalar_constants:
        default = default_dict[key]
        scalar_variants.append([(key, val) for val in [default - 2, default, default + 2]])

    list_variants = []
    for key, vals in list_constants:
        list_variants.append((key, x) for x in vals)


    combos = product(*interval_variants, *scalar_variants, *list_variants)

    # === Combine all variants ===
    for combo in random.sample(list(combos),n):
        config = {}

        # Assign interval values
        for min_key, max_key, lo, hi in combo[:len(interval_constants)]:
            config[min_key] = lo
            config[max_key] = hi

        # Assign scalar values
        for key, val in combo[len(interval_constants):]:
            config[key] = val

        # Add fixed constants
        for const in fixed_constants:
            config[const] = default_dict[const]

        # Set the fixed lane flag to true
        # config['fix_car_lane'] = ('car1',)

        partition(config, output_folder)


def split_interval(min_val, max_val, parts=2):
    """Split [min_val, max_val] into `parts` intervals (inclusive)."""
    assert max_val >= min_val
    step = (max_val - min_val + 1) // parts
    ranges = []
    for i in range(parts):
        start = min_val + i * step
        end = start + step - 1 if i < parts - 1 else max_val
        ranges.append((start, end))
    return ranges


if __name__ == "__main__":
    # script_dir = os.path.dirname(os.path.abspath(__file__))
    # output_dir = os.path.join(script_dir, "variability_experiments_instances")
    # vary_params(output_dir, 10)
    vary_params()

