# creates a bunch of lp files which instantiate the constants used in the program. 
# target usecase is quickly generating a bunch of different parameter sets without loading any constants multiple times


import os

# Default values from constants.lp
default_dict = {
    'max_segment': 300,
    'max_velocity_change_lon': 8,
    'max_velocity_lon': 12,
    'max_velocity_lat': 1,
    'safety_distance': 1,
    'change_dur': 1,
    'max_lane': 1,
    'min_change_speed': 2,
    'max_change_speed': 8,
    'max_braking_speed_while_turning': 5,
    'max_acceleration_while_turning': 1,
    'safety_distance_back': 3,
    'init_distance': None,
    'fix_car_lane': None
}

def _truncate(val):
    """Truncate float values for readable filenames."""
    if isinstance(val, float):
        return f"{val:.2f}".rstrip("0").rstrip(".")
    return str(val)

def _param_value_repr(k, v):
    """For use in filenames: e.g. max_speed_10To12 or max_lane_2."""
    if isinstance(v, tuple) and k=='fix_car_lane':
        # NOTE I do not allow intervals anymore, as it was not supported to encode constants in an interval in clingo
        return f"fixed_lane{'_'.join(v)}"
    else:
        return f"{k}_{_truncate(v)}"

def partition(constants: dict, out_path: str, init_distance_actor='car1') -> str:
    """
    Create an .lp file with specified constant overrides and comments for default/varied values.
    """
    if not os.path.exists(out_path):
        os.makedirs(out_path)

    # Validate keys
    for k in constants:
        if k not in default_dict:
            raise ValueError(f"Unknown constant '{k}' provided. Valid keys: {list(default_dict.keys())}")

    # Filename from sorted varied params
    if constants:
        fname = "__".join(_param_value_repr(k, constants[k]) for k in sorted(constants)) + ".lp"
    else:
        fname = "constants_default.lp"    
    full_path = os.path.join(out_path, fname)

    added = []

    with open(full_path, "w") as f:
        f.write("#program base.\n\n")

        # Varied parameters section
        f.write("%%%%%%\n")
        f.write("%% Varied parameters\n")
        f.write("%%%%%%\n")
        for k in sorted(constants):
            val = constants[k]
            # print(k, type(val))
            if isinstance(val, tuple):
                # NOTE I do not allow tuples as intervals anymore
                continue
            elif val is None:
                continue
            else:
                # f.write(f"# {k} = {val}\n")
                f.write(f"#const {k} = {val}.\n")
                added.append(k)

            if val and k == 'init_distance':
                f.write(f"init(state({init_distance_actor}, loc(init_distance,0), dyn(1, 0))).\n\n")
        f.write("\n")

        # Default parameters section
        f.write("%%%%%%\n")
        f.write("%% Default parameters\n")
        f.write("%%%%%%\n")
        for k in sorted(default_dict):
            if default_dict[k] is None:
                continue
            if k in added:
                continue # TODO I have no clue why this is necessary, all a bit messy
            if k not in constants or k!= 'fix_car_lane':
                val = default_dict[k]
                # f.write(f"# {k} = {val}\n")
                assert((k,val) not in added), "This should not happen."
                f.write(f"#const {k} = {val}.\n")
                added.append(k)



        try:
            actors = constants['fix_car_lane']

            # Default parameters section
            f.write("%%%%%%\n")
            f.write("%% Special flags\n")
            f.write("%%%%%%\n")

            f.write("\n#program step(t).\n")

            for actor in actors:
                f.write(f":- occurs(change_dynamics(V,_,VLAT),t), V={actor}, VLAT != 0.\n\n")
        except:
            pass


    return full_path





if __name__ == '__main__':
    import os
    
    script_dir = os.path.dirname(os.path.abspath(__file__))


    out_path = os.path.join(script_dir,'variability_experiments_instances')
    part_dict = {'change_dur':3,'min_change_speed':(1,4)}
    partition(part_dict,out_path)

    out_path = os.path.join(script_dir,'variability_experiments_instances')
    part_dict = dict()
    partition(part_dict,out_path)

