#!/usr/bin/env python3
"""Install bridge-auto.py as a launchd LaunchAgent so it stays resident.

Runs bridge-auto.py at login and restarts it after any exit (crash, phone
unreachable, overlay drop) — the same supervision the Iris bridge had.

Usage:
  python3 scripts/bridge-auto-install.py             # interactive: asks first
  python3 scripts/bridge-auto-install.py --yes       # skip the confirmation
  python3 scripts/bridge-auto-install.py --uninstall # remove the agent

Configuration is resolved in this order:
  1. flags and this shell's environment
  2. the environment of a bridge-auto.py process already running (read via
     ps so a hand-started bridge is adopted with its exact identity)
  3. defaults / interactive prompt

Only the bridge's own whitelisted variables are written to the plist — the
running process's full environment is never dumped, because it can carry
unrelated credentials.
"""
from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import subprocess
import sys
import uuid

BRIDGE = "scripts/bridge-auto.py"
LABEL = "com.remote-ios-deploy.bridge-auto"
BRIDGE_ENVS = ("PHONE", "LOCAL_IP", "PREFETCH", "IDLE_TTL", "CLEAN_INTERVAL",
               "RP_INSTANCE", "RP_AUTHTAG", "RP_HOSTNAME", "RP_VER",
               "RP_MINVER", "RP_FLAGS")
# socat lives in /opt/homebrew/bin, which launchd's default PATH omits.
LAUNCHD_PATH = "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def running_bridge_pid() -> int | None:
    """A bridge-auto.py python process, or None. Excludes this installer."""
    try:
        out = subprocess.run(["pgrep", "-f", "bridge-auto.py"],
                             capture_output=True, text=True,
                             timeout=10).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return None
    self_pid = str(os.getpid())
    for pid in out:
        if pid == self_pid:
            continue
        try:
            cmd = subprocess.run(["ps", "-p", pid, "-o", "command="],
                                 capture_output=True, text=True,
                                 timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        if "bridge-auto.py" in cmd and "bridge-auto-install" not in cmd:
            return int(pid)
    return None


def process_env(pid: int) -> dict[str, str]:
    """Whitelisted env of a running process. ps splits tokens on spaces and
    its output can carry unrelated secrets, so only bridge keys are kept."""
    try:
        raw = subprocess.run(["ps", "eww", "-p", str(pid)],
                             capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    found: dict[str, str] = {}
    for token in raw.replace("\n", " ").split(" "):
        key, sep, value = token.partition("=")
        if sep and key in BRIDGE_ENVS and value:
            found[key] = value
    return found


def ask(question: str) -> bool:
    while True:
        answer = input(f"{question} [y/N] ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("", "n", "no"):
            return False


def launchctl(*args: str) -> tuple[int, str]:
    proc = subprocess.run(["launchctl", *args],
                          capture_output=True, text=True, timeout=60)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def random_auth_tag() -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(alphabet[b & 61] for b in os.urandom(8))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true",
                        help="skip the confirmation prompt")
    parser.add_argument("--uninstall", action="store_true",
                        help="remove the LaunchAgent")
    parser.add_argument("--phone", help="phone overlay address")
    parser.add_argument("--local-ip", help="LAN IPv4 to bind and advertise")
    parser.add_argument("--label", default=LABEL, help=f"label (default {LABEL})")
    args = parser.parse_args()

    uid = os.getuid()
    domain = f"gui/{uid}"
    plist_path = os.path.expanduser(
        f"~/Library/LaunchAgents/{args.label}.plist")

    if args.uninstall:
        launchctl("bootout", f"{domain}/{args.label}")
        if os.path.exists(plist_path):
            os.remove(plist_path)
        print(f"Removed {args.label} and {plist_path}")
        return 0

    # Adopt the config of a hand-started bridge so the resident one matches
    # exactly — same Bonjour identity, same phone address.
    existing = running_bridge_pid()
    resolved: dict[str, str] = {}
    if existing:
        resolved.update(process_env(existing))

    if args.phone:
        resolved["PHONE"] = args.phone
    if args.local_ip:
        resolved["LOCAL_IP"] = args.local_ip
    for key in BRIDGE_ENVS:
        env_val = os.environ.get(key)
        if env_val:
            resolved[key] = env_val

    identity_generated = not resolved.get("RP_INSTANCE")
    if not resolved.get("PHONE"):
        if sys.stdin.isatty():
            resolved["PHONE"] = input("Phone overlay address: ").strip()
        if not resolved.get("PHONE"):
            print("PHONE is required: pass --phone, set PHONE, or start a "
                  "bridge-auto.py first.", file=sys.stderr)
            return 1
    if identity_generated:
        resolved["RP_INSTANCE"] = str(uuid.uuid4())
        resolved["RP_AUTHTAG"] = random_auth_tag()
    if not resolved.get("RP_HOSTNAME"):
        resolved["RP_HOSTNAME"] = f"phone-bridge-{uuid.uuid4().hex[:6]}.local"

    script = os.path.join(repo_root(), BRIDGE)
    if not os.path.exists(script):
        print(f"Bridge script not found: {script}", file=sys.stderr)
        return 1
    python = shutil.which("python3") or sys.executable

    plist = {
        "Label": args.label,
        "ProgramArguments": [python, script],
        "WorkingDirectory": repo_root(),
        "EnvironmentVariables": {"PATH": LAUNCHD_PATH, **resolved},
        "RunAtLoad": True,
        "KeepAlive": True,
        # Crash-restart throttle, and time for old socat children to drain.
        "ThrottleInterval": 20,
        "ExitTimeOut": 30,
        "StandardOutPath": os.path.expanduser(
            f"~/Library/Logs/{args.label}.log"),
        "StandardErrorPath": os.path.expanduser(
            f"~/Library/Logs/{args.label}.log"),
    }

    print(f"\nInstalling LaunchAgent {args.label}")
    print(f"  program : {python} {script}")
    print(f"  plist   : {plist_path}")
    print("  env     : " +
          " ".join(f"{k}={v}" for k, v in sorted(resolved.items())))
    if identity_generated:
        print("  note    : generated Bonjour identity — if Xcode fails to "
              "authenticate, read identifier/authTag from the phone's live "
              "Bonjour TXT and reinstall with RP_INSTANCE/RP_AUTHTAG set.")
    if existing:
        print(f"  existing: a hand-started bridge (pid {existing}) is running "
              "and holds the control port; it must be stopped first.")

    if not args.yes:
        if not sys.stdin.isatty():
            print("--yes is required when stdin is not a tty.",
                  file=sys.stderr)
            return 1
        if not ask("\nCreate and start this LaunchAgent?"):
            print("Aborted; nothing was changed.")
            return 0

    os.makedirs(os.path.dirname(plist_path), exist_ok=True)
    os.makedirs(os.path.expanduser("~/Library/Logs"), exist_ok=True)
    with open(plist_path, "wb") as handle:
        plistlib.dump(plist, handle, fmt=plistlib.FMT_XML)
    os.chmod(plist_path, 0o600)

    # Two bridges on one control port fight over the listeners and publish
    # duplicate Bonjour records, so retire the hand-started one first.
    if existing:
        subprocess.run(["kill", "-TERM", str(existing)], timeout=30)
        for _ in range(20):
            try:
                os.kill(existing, 0)
            except ProcessLookupError:
                break
            import time
            time.sleep(1)

    launchctl("bootout", f"{domain}/{args.label}")  # tolerate absence
    rc, out = launchctl("bootstrap", domain, plist_path)
    if rc != 0:
        print(f"bootstrap failed: {out}", file=sys.stderr)
        return 1
    rc, out = launchctl("kickstart", "-k", f"{domain}/{args.label}")
    if rc != 0:
        print(f"kickstart failed: {out}", file=sys.stderr)
        return 1

    print(f"\nInstalled and started (pid via 'launchctl list | grep {args.label}').")
    print(f"Logs: ~/Library/Logs/{args.label}.log")
    print(f"Stop: launchctl stop {args.label}")
    print(f"Remove: {sys.argv[0]} --uninstall")
    return 0


if __name__ == "__main__":
    sys.exit(main())
