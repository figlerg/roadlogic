import re


def extract_goal_number(string):
    pattern = r"time_goal(\d+)"
    match = re.match(pattern, string)

    if match:
        return int(match.group(1))
    else:
        return None
