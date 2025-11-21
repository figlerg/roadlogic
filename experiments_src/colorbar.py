import matplotlib
matplotlib.use("Agg")  # non-GUI backend, no Tkinter

import matplotlib.pyplot as plt
import matplotlib as mpl


# ---- LaTeX-consistent text rendering ----
mpl.rcParams.update({
    "text.usetex": True,
    "font.family": "serif",
    "axes.titlesize": 8,
    "axes.labelsize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 7,
    "pdf.fonttype": 42,      # embed editable text
    "ps.fonttype": 42,
})

# ---- shared colormap + normalization ----
cmap = plt.cm.hot
norm = mpl.colors.Normalize(vmin=0.0, vmax=1.0)

# ---- Create a figure *taller* than the actual bar (adds whitespace) ----
fig = plt.figure(figsize=(1.66, 0.45))

# ---- Place a *thin* horizontal colorbar in the middle ----
ax = fig.add_axes([0.0, 0.4, 1.0, 0.20])   # [left, bottom, width, bar-height]

cb = mpl.colorbar.ColorbarBase(
    ax,
    cmap=cmap,
    norm=norm,
    orientation="horizontal"
)

# ---- Clean tick formatting ----
cb.set_ticks([0, 1])
cb.set_ticklabels([r"0", r"1"])   # use LaTeX text

cb.set_label(r"IoU similarity", fontsize=8, labelpad=2)
cb.ax.tick_params(labelsize=7, pad=1)

# ---- Save as high-quality PDF ----
fig.savefig(
    "experiments_src/vis/similarities/shared_colorbar.pdf",
    bbox_inches="tight",
    pad_inches=0,
    transparent=True
)

plt.close()

