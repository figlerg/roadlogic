## NOTE this doesn't really work, comparing the hashes gives different results for equal plans it seems
#           (It is still useful to find the fitting simulations in old backups.)

import hashlib, os

def file_hash(path, chunk_size=8192):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()

target = "paper/bckp/01_overtake_executed_scenario.xml"
target_hash = file_hash(target)

path_to_experiments_repo = os.path.expanduser("/home/figlerg/dev/")


print("walking:", path_to_experiments_repo, "exists:", os.path.isdir(path_to_experiments_repo))

matches = []
for root, _, files in os.walk(path_to_experiments_repo):
    # print(root)  # uncomment if you want to see traversal
    for f in files:
        if f.endswith(".xml"):
            # print(f)
            p = os.path.join(root, f)
            if file_hash(p) == target_hash:
                matches.append(p)

print(matches)
