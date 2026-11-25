"""Record a BeamNG run as an mp4: a frame per recorded step from a free camera above and behind the cars,
following the point between them. Needs a renderer (ROADLOGIC_BEAMNG_GFX=vk or dx11).

Frames come from beamngpy's Camera sensor (not attached to a vehicle, moved before each frame), are
saved as JPEG next to the mp4 and joined with ffmpeg at real-time speed.
"""
import os
import subprocess
import time

import numpy as np

# camera offset from the point between the cars: behind (-x), to the right (-y), up
OFFSET, LOOK_AHEAD = np.array([-16.0, -14.0, 11.0]), 6.0


class Recorder:
    def __init__(self, bng, frames_dir, size=(1280, 720), fov=50):
        self.bng, self.frames_dir, self.size, self.fov = bng, frames_dir, size, fov
        os.makedirs(frames_dir, exist_ok=True)
        for f in os.listdir(frames_dir):
            os.remove(os.path.join(frames_dir, f))
        self.camera = None
        self.saved = 0

    def _open(self, pos, direction):
        """Opened at the first frame, after the level is loaded."""
        from beamngpy.sensors import Camera
        self.camera = Camera("roadlogic_video", self.bng, pos=tuple(pos), dir=tuple(direction), up=(0, 0, 1),
                             resolution=self.size, field_of_view_y=self.fov, near_far_planes=(0.1, 600.0),
                             is_render_annotations=False, is_render_depth=False, is_static=True,
                             is_dir_world_space=True, requested_update_time=-1.0)

    def frame(self, k, positions, ground_z=0.0):
        """One frame at step k, positions: [(x, y), ...] of the cars on ground at height ground_z."""
        mid = np.array([np.mean([p[0] for p in positions]), np.mean([p[1] for p in positions]), ground_z])
        pos = mid + OFFSET
        direction = mid + np.array([LOOK_AHEAD, 0.0, 0.5]) - pos
        direction = direction / np.linalg.norm(direction)
        if self.camera is None:
            self._open(pos, direction)
        else:
            self.camera.set_position(tuple(pos))
            self.camera.set_direction(tuple(direction))
        request = self.camera.send_ad_hoc_poll_request()     # poll() returns no image in 0.38.5
        t0 = time.time()
        while not self.camera.is_ad_hoc_poll_request_ready(request) and time.time() - t0 < 10:
            time.sleep(0.02)
        image = self.camera.collect_ad_hoc_poll_request(request).get("colour")
        if image is not None:
            image.convert("RGB").save(os.path.join(self.frames_dir, f"frame_{k:05d}.jpg"), quality=90)
            self.saved += 1

    def finish(self, mp4, fps=10):
        """Join the frames into an mp4 at real-time speed (one frame per 0.1 s of simulation)."""
        if self.camera is not None:
            self.camera.remove()
        if not self.saved:
            raise RuntimeError("no frames, is a renderer running (ROADLOGIC_BEAMNG_GFX)?")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-pattern_type", "glob",
                        "-i", os.path.join(self.frames_dir, "frame_*.jpg"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", str(mp4)], check=True)
        return self.saved
