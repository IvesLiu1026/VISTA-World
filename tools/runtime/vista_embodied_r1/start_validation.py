"""Launch only the dedicated offline validation game on display 120."""
import argparse
from pathlib import Path
import subprocess


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--project", required=True, type=Path)
    p.add_argument("--user-dir", required=True, type=Path)
    p.add_argument("--engine", type=Path, default=Path("/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Binaries/Linux/UnrealEditor"))
    a = p.parse_args()
    unit = "vista-embodied-review-test-r1.service"
    if subprocess.run(["systemctl", "--user", "is-active", "--quiet", unit]).returncode == 0:
        raise SystemExit("Validation game is already active; inspect and stop that unit first")
    if a.user_dir.exists():
        raise SystemExit("Use a fresh runtime directory")
    if not a.project.is_file() or not a.engine.is_file():
        raise SystemExit("Missing engine or project")
    subprocess.run(["systemd-run", "--user", "--unit=" + unit, "--collect",
        "--description=VISTA embodied native validation", "--setenv=DISPLAY=:120",
        "--setenv=XDG_RUNTIME_DIR=/run/user/1000021", "--setenv=XDG_CACHE_HOME=/data/sysx/cache",
        "/usr/bin/bwrap", "--unshare-net", "--die-with-parent", "--dev-bind", "/", "/", "--",
        str(a.engine), str(a.project), "/Game/VISTA/PhotorealHomeR1/Maps/Home", "-game",
        "-Windowed", "-ForceRes", "-ResX=1920", "-ResY=1080", "-WinX=0", "-WinY=0",
        "-graphicsadapter=0", "-UserDir=" + str(a.user_dir), "-Unattended", "-NoSplash",
        "-NOSOUND", "-NoAnalytics", "-NoVSync", "-notraceserver", "-ddc=InstalledNoZenLocalFallback",
        "-SaveToUserDir", "-ExecCmds=t.MaxFPS 30,r.ScreenPercentage 100,r.ExposureOffset -2.8",
        "-UDPMESSAGING_TRANSPORT_ENABLE=0",
        "-ini:Engine:[/Script/TcpMessaging.TcpMessagingSettings]:EnableTransport=False", "-VistaWholeHome"], check=True)


if __name__ == "__main__":
    main()
