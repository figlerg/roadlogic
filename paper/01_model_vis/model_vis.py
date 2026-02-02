import pickle
import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import animation

import matplotlib as mpl

mpl.rcParams.update({
    "text.usetex": True,
    "font.family": "serif",
    "font.serif": ["Computer Modern Roman"],
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})


plots_folder = "paper/01_model_vis/model_vis_plots"
# plan_path = "paper/01_model_vis/predicates.pkl"
plan_path = "paper/01_model_vis/overtake/out/serialized_models/0001.pkl"




# manual renaming of agents so that our plots line up nicely
actor_renaming = {'ego':'v1','car1':'v2'}
# actor_renaming = None


# Load predicates only
with open(plan_path, "rb") as f:  
    predicates = pickle.load(f)

predicates = predicates.holds

print(predicates)


for p in predicates:
    # holds(state(npc1,loc(17,0),dyn(1,0)),0)
    # print(f"holds(state({p[0][0]},{p[0][1]},{p[0][2]})")
    pass

# Reconstruct from predicates
time_points = sorted(set(pred[-1] for pred in predicates))
segments = sorted(set(pred[0][1][0] for pred in predicates))
lanes = sorted(set(pred[0][1][1] for pred in predicates))

text_elements = {}


os.makedirs(plots_folder, exist_ok=True)

# NOTE: the 90 degree turn is super confusing.
# I have to do a couple of flips for this to make sense

def update_frame(frame):
    plt.clf()
    plt.tight_layout()

    fig = plt.gcf()
    fig.set_size_inches(424.58624 / 72, 1)

    true_predicates = [pred for pred in predicates if pred[-1] == frame]

    for pred in true_predicates:
        
        if actor_renaming:
            name = actor_renaming[str(pred[0][0])]
        else:
            name = pred[0][0]



        if name not in text_elements:
            plt.text(pred[0][1][0], -pred[0][1][1], name, fontsize=12, ha='center', va='center', bbox=dict(boxstyle="round,pad=0.3", edgecolor="black", facecolor="white", linewidth=0.8, alpha=1.0))

    x_min = min(segments) - 1
    x_max = max(segments) + 1
    y_max = -min(lanes) + 1
    y_min = -max(lanes) - 1

    plt.xlim(x_min, x_max)
    plt.ylim(y_min, y_max)

    ax = plt.gca()
    ax.set_xticks(np.arange(x_min, x_max))
    ax.set_xticklabels([str(x) if x % 10 == 0 else '' for x in range(x_min, x_max)])
    # ax.set_xticks(np.arange(x_min, x_max,5))


    # stupid flipping
    yticks = np.arange(y_min, y_max+1, 1)
    ax.set_yticks(yticks)
    ax.set_yticklabels([-y for y in yticks])
    ax.tick_params(axis='y', pad=5)

    plt.xlabel("segment")
    plt.ylabel("lane")
    plt.grid(True)
    plt.title(f"Fluents at time: {frame}")

    plt.savefig(os.path.join(plots_folder, f"{frame:04d}.pdf"), format="pdf", bbox_inches='tight')
    plt.savefig(os.path.join(plots_folder, f"{frame:04d}.jpg"), format="jpg", bbox_inches='tight',dpi=300)
    # plt.savefig(os.path.join(plots_folder, f"{frame:04d}_original_names.pdf"), format="pdf", bbox_inches='tight')
    # plt.savefig(os.path.join(plots_folder, f"{frame:04d}_original_names.jpg"), format="jpg", bbox_inches='tight',dpi=300)


# Create the figure and animation
fig = plt.figure()
ani = animation.FuncAnimation(fig, update_frame, frames=len(time_points), interval=1000, repeat=False)

# https://www.geeksforgeeks.org/how-to-save-matplotlib-animation/
writervideo = animation.FFMpegWriter(fps=1)
ani.save(os.path.join(plots_folder, f'anim.gif'))

from matplotlib.animation import PillowWriter

writervideo = PillowWriter(fps=1)

ani.save(
    os.path.join(plots_folder, "anim_tight.gif"),
    writer=writervideo,
    dpi=300,
    savefig_kwargs=dict(bbox_inches="tight", pad_inches=0.0)
)

##

# import imageio.v3 as iio
# import os, re

# pattern = re.compile(r"^\d{4}\.jpg$")  # only 0000.jpg, 0001.jpg, ...
# frame_files = sorted(f for f in os.listdir(plots_folder) if pattern.match(f))

# frames = [iio.imread(os.path.join(plots_folder, f)) for f in frame_files]
# iio.imwrite(os.path.join(plots_folder, "anim_stitched.gif"), frames, duration=1.0, loop=0)

import imageio.v3 as iio
import os, re
import numpy as np

pattern = re.compile(r"^\d{4}\.jpg$")
frame_files = sorted(f for f in os.listdir(plots_folder) if pattern.match(f))

frames = [iio.imread(os.path.join(plots_folder, f)) for f in frame_files]

# pad all frames to the same size (max H,W)
max_h = max(im.shape[0] for im in frames)
max_w = max(im.shape[1] for im in frames)

padded = []
for im in frames:
    h, w = im.shape[:2]
    out = np.full((max_h, max_w, im.shape[2]), 255, dtype=im.dtype)  # white background
    out[:h, :w] = im
    padded.append(out)

iio.imwrite(os.path.join(plots_folder, "anim_stitched.gif"), padded, duration=750.0, loop=0,plugin="pillow")