"""Start and stop BeamNG.tech, from WSL (the Windows build, reached over the network) or on Linux.

Adapted from the COMMAND pipeline (git-service.ait.ac.at sct-dse-projects/commandsl,
command/simulation/beamng_launcher.py and beamng_client.py), without its drone mods and cluster setup.

    ROADLOGIC_BEAMNG_HOME   the BeamNG.tech folder (default C:\\Users\\<you>\\BeamNG\\BeamNG.tech.v0.38.5.0 seen from WSL)
    ROADLOGIC_BEAMNG_USER   BeamNG's userpath, caches and logs (default <home>/../userpath)
    ROADLOGIC_BEAMNG_GFX    the renderer, "vk" (default) or "dx11". "null" (none) loads no terrain and
                            crashes on smallgrid (0.38.5), so the cars have no ground
    ROADLOGIC_BEAMNG_WINDOW "1" opens a window to watch, else it runs without one

BeamNG.tech 0.38.5 needs exactly beamngpy 1.35.1.
"""
import glob
import os
import platform
import socket
import subprocess
import time
from pathlib import Path

PORT = 25252


def in_wsl():
    return "microsoft" in platform.release().lower()


def beamng_home():
    if os.environ.get("ROADLOGIC_BEAMNG_HOME"):
        return Path(os.environ["ROADLOGIC_BEAMNG_HOME"])
    found = sorted(glob.glob("/mnt/c/Users/*/BeamNG/BeamNG.tech.v0.38.5.0"))
    if not found:
        raise FileNotFoundError("BeamNG.tech not found, set ROADLOGIC_BEAMNG_HOME")
    return Path(found[0])


def user_path():
    return Path(os.environ.get("ROADLOGIC_BEAMNG_USER", beamng_home().parent / "userpath"))


def windows_host():
    """The address of the Windows side seen from WSL: this machine with mirrored networking, else the
    default gateway (NAT)."""
    if "loopback0:" in Path("/proc/net/dev").read_text():
        return "127.0.0.1"
    route = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True, check=True).stdout
    return route.split()[2]


def command(port, gfx):
    """(argv, working directory, host) of a BeamNG.tech process listening for beamngpy on `port`."""
    home, user = beamng_home(), user_path()
    headless = ["-headless"] if os.environ.get("ROADLOGIC_BEAMNG_WINDOW", "0") != "1" else []   # a window draws the world
    user.mkdir(parents=True, exist_ok=True)
    if in_wsl():
        win_user = subprocess.run(["wslpath", "-w", str(user)], capture_output=True, text=True, check=True).stdout.strip()
        argv = [str(home / "Bin64" / "BeamNG.tech.x64.exe"), "-nosteam", "-userpath", win_user, "-console",
                "-tcom-listen-ip", "0.0.0.0", "-batch", "-lua",
                f"extensions.load('tech/techCore');tech_techCore.openServer({port})", "-gfx", gfx] + headless
        return argv, home, windows_host()
    argv = [str(home / "BinLinux" / "BeamNG.tech.x64"), "-nosteam", "-tcom", "-tport", str(port),
            "-tcom-listen-ip", "127.0.0.1", "-headless", "-gfx", gfx, "-userpath", str(user)]
    return argv, home, "127.0.0.1"


def port_open(host, port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


class BeamNGServer:
    """A BeamNG.tech process for the duration of a with block. `host` and `port` are where beamngpy connects."""

    def __init__(self, port=PORT, log_path="beamng.log", gfx=None):
        self.port, self.log_path = port, Path(log_path)
        self.gfx = gfx or os.environ.get("ROADLOGIC_BEAMNG_GFX", "vk")
        self.host, self.proc = None, None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    def start(self, timeout=300):
        argv, cwd, self.host = command(self.port, self.gfx)
        if port_open(self.host, self.port):
            raise RuntimeError(f"port {self.port} on {self.host} already in use (a BeamNG still running?)")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.proc = subprocess.Popen(argv, cwd=cwd, stdout=open(self.log_path, "w"), stderr=subprocess.STDOUT,
                                     start_new_session=True)
        t0 = time.time()
        while not port_open(self.host, self.port):
            if self.proc.poll() is not None:
                raise RuntimeError(f"BeamNG exited early, see {self.log_path}")
            if time.time() - t0 > timeout:
                self.stop()
                raise TimeoutError(f"BeamNG did not open port {self.port} on {self.host} (Windows firewall?)")
            time.sleep(1)
        time.sleep(3)
        return self

    def stop(self):
        if self.proc is None:
            return
        if in_wsl():       # a Windows process, the WSL side only holds its launcher
            subprocess.run(["/mnt/c/Windows/System32/taskkill.exe", "/F", "/T", "/IM", "BeamNG.tech.x64.exe"], capture_output=True)
        else:
            self.proc.terminate()
        try:
            self.proc.wait(20)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.proc = None
