"""Drive one plan in CARLA and record it. Runs under the Python that has the CARLA client (the pipeline's own,
or a Windows Python when the pipeline runs in WSL, see execute.py), needs only carla and numpy, and talks to the
rest of the pipeline through two JSON files:

    python carla_drive.py <job.json> <trace.json>

job.json: {"host", "port", "xodr": OpenDRIVE text, "agents": map_plan_beamng's agents, "plan_end", "dt"}.
trace.json: {"trace": {agent: [[step, x, y, heading, speed], ...]}}, in CommonRoad coordinates, a row
every dt seconds, the centre of each car's bounding box.

CARLA runs in synchronous mode with a fixed physics step (TICK), so a run is repeatable. Each moving car
follows its timed script with a small controller: steering aims at the script point LOOKAHEAD seconds ahead
(pure pursuit), throttle and brake track the script's speed plus a correction for being ahead or behind
the script's position. A static car keeps its hand brake on. CARLA's world is left-handed: CommonRoad
(x, y, heading) is CARLA (x, -y, -yaw).
"""
import json
import math
import os
import sys

import carla
import numpy as np

TICK = 0.05                 # physics step [s]
LOOKAHEAD = 0.8             # [s] along the script, at least MIN_AHEAD metres
MIN_AHEAD = 5.0
WHEELBASE = 2.9
K_POS, K_SPEED, K_INT = 0.8, 0.6, 0.05
SPAWN_Z = 0.5
MODEL = "vehicle.lincoln.mkz"
COLOURS = ["31,119,180", "255,127,14", "44,160,44", "214,39,40"]   # as in the plots and the BeamNG videos
# the server's view (spectator) follows the first car along the road: behind it, to the right of the road and
# above, aimed down the road, as the BeamNG videos. Only what the server window shows, no effect on physics.
BEHIND, RIGHT, UP, AHEAD = 15.0, 7.0, 6.5, 14.0


VIDEO_SIZE, VIDEO_FOV = (960, 540), 55      # every frame crosses the network, 1280 x 720 at 20 fps was too much for Wi-Fi


def chase(x, road_y):
    """The chase view behind a car at x along the road, as a CARLA transform."""
    cam = (x - BEHIND, road_y + RIGHT, UP)          # left of the road: CARLA puts trees and lamps on its right side
    look = (x + AHEAD, road_y + 0.5, 0.0)
    dx, dy, dz = look[0] - cam[0], look[1] - cam[1], look[2] - cam[2]
    yaw = math.degrees(math.atan2(dy, dx))
    pitch = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
    return carla.Transform(carla.Location(x=cam[0], y=-cam[1], z=cam[2]), carla.Rotation(yaw=-yaw, pitch=pitch))


def video_camera(world, transform):
    """An RGB camera that delivers one image per tick into a queue (synchronous mode)."""
    import queue
    bp = world.get_blueprint_library().find("sensor.camera.rgb")
    bp.set_attribute("image_size_x", str(VIDEO_SIZE[0]))
    bp.set_attribute("image_size_y", str(VIDEO_SIZE[1]))
    bp.set_attribute("fov", str(VIDEO_FOV))
    camera = world.spawn_actor(bp, transform)
    images = queue.Queue()
    camera.listen(images.put)
    return camera, images


def save_frame(images, frame, path):
    """The camera image of a simulation frame, saved as PNG. A frame that does not arrive within 10 s is skipped
    (it happened once, and lost the whole run), the video just misses it."""
    import queue
    while True:
        try:
            image = images.get(timeout=10)
        except queue.Empty:
            return False
        if image.frame >= frame:
            image.save_to_disk(path)
            return True


def to_carla(x, y, heading, z=SPAWN_Z):
    return carla.Transform(carla.Location(x=x, y=-y, z=z), carla.Rotation(yaw=-math.degrees(heading)))


def pose(actor):
    """(centre x, centre y, heading, speed) of an actor in CommonRoad coordinates."""
    t = actor.get_transform()
    c = t.transform(actor.bounding_box.location)
    v = actor.get_velocity()
    return c.x, -c.y, -math.radians(t.rotation.yaw), math.hypot(v.x, v.y)


class Follower:
    """Tracks a timed script [{x, y, t, v}] with steering, throttle and brake."""

    def __init__(self, actor, script):
        self.actor, self.integral = actor, 0.0
        self.t = np.array([p["t"] for p in script])
        self.x = np.array([p["x"] for p in script])
        self.y = np.array([p["y"] for p in script])
        self.v = np.array([p["v"] for p in script])
        wheels = actor.get_physics_control().wheels
        self.max_steer = math.radians(max(w.max_steer_angle for w in wheels))

    def at(self, t):
        return np.interp(t, self.t, self.x), np.interp(t, self.t, self.y), np.interp(t, self.t, self.v)

    def control(self, time):
        x, y, h, v = pose(self.actor)
        rx, ry, rv = self.at(time)
        fwd = np.array([math.cos(h), math.sin(h)])
        ahead = time + LOOKAHEAD
        while ahead < self.t[-1] and (np.array(self.at(ahead)[:2]) - (x, y)) @ fwd < MIN_AHEAD:
            ahead += 0.1
        px, py, _ = self.at(ahead)
        if (np.array([px, py]) - (x, y)) @ fwd < 1.0:
            # past the end of its script (pushed, or ran ahead): hold the script's last lane instead of steering
            # at a point behind the car, which turned it off the road
            px, py = x + MIN_AHEAD * fwd[0], self.y[-1]
        alpha = math.atan2(py - y, px - x) - h
        dist = max(math.hypot(px - x, py - y), 1.0)
        steer = math.atan2(2 * WHEELBASE * math.sin(alpha), dist) / self.max_steer
        target = max(rv + K_POS * ((rx - x) * fwd[0] + (ry - y) * fwd[1]), 0.0)
        e = target - v
        self.integral = float(np.clip(self.integral + e * TICK, -10, 10))
        u = K_SPEED * e + K_INT * self.integral
        # CARLA steers right for positive values, in CommonRoad positive alpha is to the left
        return carla.VehicleControl(throttle=float(np.clip(u, 0, 1)), brake=float(np.clip(-u, 0, 1)),
                                    steer=float(np.clip(-steer, -1, 1)))


def main(job_file, trace_file):
    job = json.load(open(job_file))
    client = carla.Client(job["host"], job["port"])
    client.set_timeout(120.0)
    params = carla.OpendriveGenerationParameters(vertex_distance=2.0, max_road_length=500.0, wall_height=0.0,
                                                 additional_width=0.6, smooth_junctions=True,
                                                 enable_mesh_visibility=True)
    world = client.generate_opendrive_world(job["xodr"], params)
    settings = world.get_settings()
    settings.synchronous_mode, settings.fixed_delta_seconds = True, TICK
    world.apply_settings(settings)
    blueprint = world.get_blueprint_library().find(MODEL)
    actors, followers = {}, {}
    try:
        for k, (name, a) in enumerate(job["agents"].items()):
            s = a["spawn"]
            if blueprint.has_attribute("color"):
                blueprint.set_attribute("color", COLOURS[k % len(COLOURS)])
            actors[name] = world.spawn_actor(blueprint, to_carla(s["x"], s["y"], s["heading"]))
            if a["static"]:
                actors[name].apply_control(carla.VehicleControl(hand_brake=True))
            else:
                followers[name] = Follower(actors[name], a["script"])
        for _ in range(int(0.5 / TICK)):          # settle on the wheels
            world.tick()
        dt = job["dt"]
        end = max([p["t"] for a in job["agents"].values() for p in a["script"]] + [job["plan_end"]])
        per_row = int(round(dt / TICK))
        trace = {name: [] for name in actors}
        spectator, focus = world.get_spectator(), "ego" if "ego" in actors else next(iter(actors))
        road_y = job.get("road_y", 3.0)
        video_dir = job.get("video_dir")
        camera, images = video_camera(world, chase(pose(actors[focus])[0], road_y)) if video_dir else (None, None)
        for k in range(int(round(end / TICK)) + 1):
            if k % per_row == 0:
                for name, actor in actors.items():
                    trace[name].append([k // per_row, *pose(actor)])
            view = chase(pose(actors[focus])[0], road_y)
            # the server window and the video camera follow the car. set_transform is fire and forget, over Wi-Fi it
            # sometimes arrived after the tick and the video jumped back and forth. apply_batch_sync waits for it.
            moves = [carla.command.ApplyTransform(spectator.id, view)]
            if camera:
                moves.append(carla.command.ApplyTransform(camera.id, view))
            client.apply_batch_sync(moves, False)
            for name, f in followers.items():
                actors[name].apply_control(f.control(k * TICK))
            frame = world.tick()
            if camera:
                save_frame(images, frame, os.path.join(video_dir, f"frame_{k:05d}.png"))
        json.dump({"trace": trace}, open(trace_file, "w"))
    finally:
        if video_dir and camera:
            camera.stop()
            camera.destroy()
        for actor in actors.values():
            actor.destroy()
        settings.synchronous_mode, settings.fixed_delta_seconds = False, None
        world.apply_settings(settings)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
