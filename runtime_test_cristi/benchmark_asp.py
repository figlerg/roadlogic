import os
import time
from planning.Planner import generate_plans

# deine generate_plans(...) bleibt exakt wie sie ist
# hier nur der neue Code dazu

def _collect_lp_files(folder):
    """
    Sammle alle .lp-Dateien in einem Ordner, sortiert nach Name.
    """
    if not os.path.isdir(folder):
        raise NotADirectoryError(f"Not a directory: {folder}")
    files = []
    for name in sorted(os.listdir(folder)):
        if name.endswith(".lp"):
            files.append(os.path.join(folder, name))
    if not files:
        raise FileNotFoundError(f"No .lp files found in {folder}")
    return files


def benchmark_instances(folder_a,
                        folder_b,
                        n=1,
                        rules=None,
                        imin=1,
                        imax=20,
                        override_files=True,
                        time_limit=None,
                        deterministic=True,
                        verbose=False):
    """
    Vergleicht zwei ASP-Instanzen (Ordner mit .lp-Dateien) bzgl. Laufzeit.

    folder_a, folder_b: Ordner, die jeweils eine Instanz enthalten.
    n: Anzahl der Modelle, die du mit generate_plans suchst.
    override_files=True: benutzt NUR die Dateien aus den Ordnern
                         (keine zusätzlichen encodings/constants.lp etc.).
    Alle anderen Parameter werden direkt an generate_plans weitergereicht.
    """

    files_a = _collect_lp_files(folder_a)
    files_b = _collect_lp_files(folder_b)

    # Instanz A
    t0 = time.perf_counter()
    models_a = generate_plans(
        files=files_a,
        n=n,
        rules=rules,
        imin=imin,
        imax=imax,
        override_files=override_files,
        save_path=folder_a,
        verbose=verbose,
        time_limit=time_limit,
        deterministic=deterministic
    )
    t1 = time.perf_counter()
    time_a = t1 - t0

    # Instanz B
    t0 = time.perf_counter()
    models_b = generate_plans(
        files=files_b,
        n=n,
        rules=rules,
        imin=imin,
        imax=imax,
        override_files=override_files,
        save_path=folder_b,
        verbose=verbose,
        time_limit=time_limit,
        deterministic=deterministic,
    )
    t1 = time.perf_counter()
    time_b = t1 - t0

    if verbose:
        print(f"[A] {folder_a}: {time_a:.3f}s for {len(models_a)} models")
        print(f"[B] {folder_b}: {time_b:.3f}s for {len(models_b)} models")
        speedup = time_a / time_b if time_b > 0 else float("inf")
        print(f"Speedup B over A: {speedup:.3f}x")

    return {
        "folder_a": {
            "path": folder_a,
            "time": time_a,
            "models": models_a,
        },
        "folder_b": {
            "path": folder_b,
            "time": time_b,
            "models": models_b,
        },
        "speedup_b_over_a": time_a / time_b if time_b > 0 else float("inf"),
    }


# Optional: kleines CLI, falls du es direkt als Skript laufen lassen willst.
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Benchmark two ASP instances (folders with .lp files) using generate_plans."
    )
    parser.add_argument("folder_a")
    parser.add_argument("folder_b")
    parser.add_argument("-n", type=int, default=1, help="number of models")
    parser.add_argument("--imin", type=int, default=1)
    parser.add_argument("--imax", type=int, default=20)
    parser.add_argument("--no-override-files", action="store_true",
                        help="use base encodings from generate_plans (override_files=False)")
    parser.add_argument("--time-limit", type=float, default=None)
    parser.add_argument("--non-deterministic", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    result = benchmark_instances(
        folder_a=args.folder_a,
        folder_b=args.folder_b,
        n=args.n,
        imin=args.imin,
        imax=args.imax,
        override_files=not args.no_override_files,
        time_limit=args.time_limit,
        deterministic=not args.non_deterministic,
        verbose=True,
    )

    # Kurzsummary:
    a = result["folder_a"]["time"]
    b = result["folder_b"]["time"]
    print(f"\nResult:")
    print(f"  {args.folder_a}: {a:.3f}s")
    print(f"  {args.folder_b}: {b:.3f}s")
    print(f"  Speedup B over A: {result['speedup_b_over_a']:.3f}x")
