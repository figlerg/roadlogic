import numpy as np

# def project_to_polyline(xy, polyline):
#     """
#     Project a point onto a polyline and return the nearest point on the line.
#     """
#     diffs = polyline - xy
#     dists = np.linalg.norm(diffs, axis=1)
#     idx = np.argmin(dists)
#     return polyline[idx], idx  # nearest point and index


def project_to_polyline(xy, polyline):
    """
    Project a point xy onto a polyline (sequence of points) and return the closest point on any segment.
    Returns:
        projected_point: The closest point on the polyline
        segment_index: Index of the segment (start point) that gave the projection
    """
    closest_point = None
    min_dist = float('inf')
    best_idx = -1

    for i in range(len(polyline) - 1):
        a = polyline[i]
        b = polyline[i + 1]
        ab = b - a
        t = np.dot(xy - a, ab) / np.dot(ab, ab)
        t = np.clip(t, 0.0, 1.0)
        projection = a + t * ab
        dist = np.linalg.norm(xy - projection)

        if dist < min_dist:
            min_dist = dist
            closest_point = projection
            best_idx = i

    return closest_point, best_idx
