'''
Example implementing an iclingo-like application.
Modified for OSC2Scenic and our incremental encoding.
'''
import time

import cProfile
import numpy as np
import os
import pickle
import pstats
import shutil
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clingo.control import Control
from clingo.symbol import Function, Number
from matplotlib import pyplot as plt, animation

from planning.asp.MyModel import MyModel
from typing import Sequence

def generate_plans(files, n, rules=None, imin=1, imax=20, override_files=False, save_path=None, verbose=False,
                   time_limit = None, deterministic=True):
    '''
    The main function implementing incremental solving.
    @param imin:
    @param imax:
    '''

    conf = Conf(imin, imax, "SAT")
    ctl = Control()
    seed = 42

    ctl.configuration.solve.models = n  # 0 for all models, or N (N > 0) for just at most N models

    if deterministic:
        ctl.configuration.solve.parallel_mode=1

    ## NONE OF THESE HELP WITH THE SEARCH TREE ORDER
    # ctl.configuration.solve.rand_freq = 1
    # ctl.configuration.solve.sign_def = "random"
    # ctl.configuration.solve.seed = seed
    # ctl.configuration.solve.restart_conflicts = 1
    # ctl.configuration.solve.restarts = "luby"

    if not override_files:
        base_dir = os.path.dirname(__file__)
        files = ([  os.path.join(base_dir, "encoding", "constants.lp"),
                    os.path.join(base_dir, "encoding", "facts.lp"),
                    os.path.join(base_dir, "encoding", "dynamics.lp")] +
                    files)

    if save_path:
        if not os.path.exists(save_path):
            raise FileNotFoundError(f"Provided save_path does not exist: {save_path}")

        asp_dir = os.path.join(save_path, 'asp')
        os.makedirs(asp_dir, exist_ok=True)
        for f in files:
            try:
                shutil.copy(f, asp_dir)
            except shutil.SameFileError:
                print(f"Skipped copying '{f}' — source and destination are the same.")

        if rules:
            added_rules_path = os.path.join(asp_dir, 'added_rules.lp')
            with open(added_rules_path, 'w') as f:
                f.write('#program check(t).\n\n')
                f.writelines(line.rstrip('\n') + '\n' for line in rules)
            files.append(added_rules_path)

    for file_ in files:
        ctl.load(file_)
    ctl.add("check", ["t"], "#external query(t).")

    step = 0
    models = []

    start_time = time.time()

    while ((conf.imax is None or step < conf.imax) and (len(models) < n)):

        # TODO this could take quite a bit longer than the limit as I don't interrupt any clingo runs. Should patch that
        elapsed = time.time() - start_time
        if time_limit and elapsed > time_limit:
            raise TimeoutError(f'Could not find a model within the time limit of {time_limit}s for files = {files}.')


        parts = []
        parts.append(("check", [Number(step)]))
        if step > 0:
            ctl.release_external(Function("query", [Number(step - 1)]))
            parts.append(("step", [Number(step)]))
        else:
            parts.append(("base", []))

        ctl.ground(parts)
        ctl.assign_external(Function("query", [Number(step)]), True)

        # if verbose:
        print(f'Solving... t = {step}')

        with ctl.solve(yield_=True) as handle:
            for model in handle:
                my_model = MyModel(model)
                models.append(my_model)
                if verbose:
                    print(f'\tGenerated model {len(models)}')
                if len(models) >= n:
                    break

        step += 1

    if len(models) == 0:
        raise NoModelException(f"Didn't find a model. Config: {conf}")

    return models


def visualize_plans(models, max_num=None, save=False, show=True, save_path=None, verbose=False, custom_names:Sequence[str]=None):
    # can visualize results in an animation and/or save gifs.

    if save_path and not os.path.exists(save_path):
        raise FileNotFoundError(f"Provided save_path does not exist: {save_path}")

    plan_filter_models = filter_occs(models, max_num=max_num).__iter__()

    # make them into strings for terminal print
    plan_strings = []
    if not max_num:
        max_num = 1

    for i in range(max_num):
        try:
            plan_strings.append(pred_str_helper(next(plan_filter_models)))
        except StopIteration:
            print(f'Exhausted models: {i} models generated.')
            break

    # print(f"Nr planning strings: {len(plan_strings)}")

    fluent_filter_models = filter_holds(models, max_num=max_num)

    # print(f"Nr fluent filter models: {len(fluent_filter_models)}")
    # print(f"max_num = {max_num}")
    # print(f"plan_strings = {plan_strings}")

    if save_path:
        save_dir_pkl = os.path.join(save_path, 'serialized_models')
        save_dir_anim = os.path.join(save_path, 'animations')
        save_dir_plans = os.path.join(save_path, 'plans')
    else:
        save_dir_pkl = os.path.join('generated', 'serialized_models')
        save_dir_anim = os.path.join('generated', 'animations')
        save_dir_plans = os.path.join('generated', 'plans')

    os.makedirs(save_dir_pkl, exist_ok=True)
    os.makedirs(save_dir_anim, exist_ok=True)
    os.makedirs(save_dir_plans, exist_ok=True)

    i = 0  # just needed for the print later
    for i, a in enumerate(fluent_filter_models):

        if i >= len(plan_strings):
            break
            # There are usually more answer sets, but I only generated this many occurs-plans.
            #  In any case, this is how many samples we want.

        # Printing the important predicates of each model
        print(f"Visualizing model {i + 1}:")

        # DEBUGGING THE MODELS
        model = models[i]
        model_dbg = list(model)

        # for debugging I save the plans as json
        if custom_names:
            model.to_json(os.path.join(save_dir_plans, f'{custom_names[i]}.json'))
        else:
            model.to_json(os.path.join(save_dir_plans, f'plan_{i + 1:04d}.json'))

        if verbose:
            print(*model_dbg)
            # print(f"occurs:\t{filter_preds(model_dbg, 'occurs')}")
            # print(f"holds:\t{filter_preds(model_dbg, 'holds')}")
            # print(f"poss:\t{filter_preds(model_dbg, 'possible')}")
            # print(f"time:\t{filter_preds(model_dbg, 'time')}")
            # print(f"action:\t{filter_preds(model_dbg, 'action')}")
            # print(f"inert:\t{filter_preds(model_dbg, 'inert')}")
            # print(f"can_move:\t{filter_preds(model_dbg, 'can_move')}")
            # print(f"print variable:\t{filter_preds(model_dbg, 'print')}")

            print(f"\tVisualizing the following plan:   {plan_strings[i]}.")
            print(f"\tIt has following fluents:         {pred_str_helper(a)}\n\n")

        # transform the clingo predicate objects to tuples TODO refactor with namedtuples?
        predicates = holds_plan_helper(a)

        if custom_names:
            pkl_file = os.path.join(save_dir_pkl, f'{custom_names[i]}.pkl')
        else:
            pkl_file = os.path.join(save_dir_pkl, f'{i + 1:04d}.pkl')
            # pkl_file = os.path.join(save_dir_pkl, f'scenario_{i + 1:04d}.pkl')
            # pkl_file = os.path.join(save_dir_pkl, f'model_{i + 1:04d}.pkl')

        with open(pkl_file, "wb") as f:
            pickle.dump(models[i], f)

        # Extract unique time points
        time_points = sorted(set(pred[3] for pred in predicates))
        lanes = sorted(set(pred[1][1] for pred in predicates))
        segments = sorted(set(pred[1][0] for pred in predicates))

        # Initialize a dictionary to store the text elements
        text_elements = {}

        # Function to update the plot for each frame of the animation
        def update_frame(frame):
            plt.clf()  # Clear the current figure
            # plt.gca().cla()

            # Get the predicates that are true at the current time point
            true_predicates = [pred for pred in predicates if pred[3] == frame]

            # Update the text elements for the true predicates
            for pred in true_predicates:
                # print(f"True predicates: {true_predicates}")
                name = pred[0]
                if name not in text_elements.keys():
                    # Create new text element
                    text = plt.text(pred[1][1], pred[1][0], name, fontsize=12, ha='center', va='center')

            y_min = min(segments) - 1
            y_max = max(segments) + 1
            x_min = min(lanes) - 1
            x_max = max(lanes) + 1

            plt.ylim(y_min, y_max)
            plt.xlim(x_min, x_max)

            x_ticks = np.arange(x_min, x_max, 1)
            y_ticks = np.arange(y_min, y_max, 1)

            ax = plt.gca()

            ax.set_xticks(x_ticks)
            ax.set_yticks(y_ticks, labels=[str(y) if y % 10 == 0 else '' for y in y_ticks])
            # ax.set_yticks([str(y) if y % 10 == 0 else '' for y in y_ticks])

            plt.xlabel("lane")
            plt.ylabel("segment")

            plt.grid(True)
            plt.title('Predicates at Time: {}'.format(frame))

        # Create the figure and animation
        fig = plt.figure()
        ani = animation.FuncAnimation(fig, update_frame, frames=len(time_points), interval=1000, repeat=False)

        # https://www.geeksforgeeks.org/how-to-save-matplotlib-animation/
        if save:
            # writervideo = animation.FFMpegWriter(fps=1)

            # Save animation
            if custom_names:
                ani.save(os.path.join(save_dir_anim, f'{custom_names[i]}.gif'))
            else:
                ani.save(os.path.join(save_dir_anim, f'anim_{i + 1:04d}.gif'))

        if show:
            plt.show()

        if max_num:
            if i > max_num:
                break

    print(f'Visualized {i + 1} samples. Save animations: {save}. Show animations: {show}')




class NoModelException(Exception):
    pass


class Conf:
    def __init__(self, imin, imax, istop):
        self.imin = imin
        self.imax = imax
        self.istop = istop

    def __str__(self):
        return f"imin = {self.imin}\timax = {self.imax}, \t istop = {self.istop}"


### SOME HELPERS ###
# TODO streamline some of this. too many helpers and not very clean


# TODO both of these do the same as filter_preds, just one level higher. Streamline this by writing a function which does filter_preds for lists of models
def filter_holds(models, max_num=None):
    # gives me each model as a list of 'holds' predicates
    out = list()
    for i, model in enumerate(models):
        out.append(tuple([pred for pred in model if pred.name == 'holds']))
        if max_num and i > max_num:
            break
    return out


def filter_occs(models, max_num=None):
    # utility: gives me each model as a list of 'occurs' predicates
    out = []
    for i, model in enumerate(models):
        out.append([pred for pred in model if pred.name == 'occurs'])
        if max_num and i > max_num:
            break
    return out


def pred_str_helper(preds):
    # utility: for making the strings look nicer, a list of predicates is printed really unreadably
    out = ''
    for occ in preds:
        out += str(occ) + ' '
    return out


def filter_preds(model_list, symbol):
    # takes a list of predicates generated by clingo and only returns a list of the chosen symbol (in a readable string)
    out = []
    n = 0
    for pred in model_list:
        if pred.name == symbol:
            out.append(pred)
            n += 1

    return n, pred_str_helper(out)


def holds_plan_helper(answer_set_list):
    # strips the predicates to a more readable tuple form

    out = []

    for pred in answer_set_list:
        out.append(holds_helper(pred))

    return out


def holds_helper(pred):
    assert pred.name == "holds", "This helper expects only hold predicates."

    fluent = pred.arguments[0]
    time = pred.arguments[1]

    predicate = (fluent.arguments[0].name,
                 (fluent.arguments[1].arguments[0], fluent.arguments[1].arguments[1]),  # loc
                 (fluent.arguments[2].arguments[0], fluent.arguments[2].arguments[1]),  # dyn
                 time)

    return predicate


if __name__ == '__main__':
    def experiment():
        # files = ["encoding/constants.lp", "encoding/dynamics.lp", "encoding/instance_experiments.lp"]
        # additional_files = ["../generated/instance.lp"]
        additional_files = ["encoding/instance_experiments.lp"]

        models = generate_plans(files=additional_files, n=50, save_path=r"../generated")

        print(models)

        # visualize_plans(models[0:5:], save=True, save_path="../generated/animations", show=False, max_num=10)
        visualize_plans(models[0:5:], save=True, save_path=r"../generated", show=False, max_num=2)


    pr = cProfile.Profile()

    pr.enable()
    experiment()

    pr.disable()
    profile_file = "tmp.prof"
    pr.dump_stats(profile_file)
    print(f"Profiling data saved to {profile_file}")
    p = pstats.Stats(profile_file)
    p.strip_dirs().sort_stats('cumulative').print_stats(10)
