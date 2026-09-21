#!/usr/bin/env python3
"""Auto-connect resident bridge: supply only the phone's overlay IP.

One hard prerequisite (Apple's trust model, not a bridge limitation):
the phone must have completed a one-time Xcode pairing with THIS Mac —
over USB or while on the same Wi-Fi, with Trust tapped and passcode entered.
This script cannot create that trust, and a pairing held by another Mac does
not transfer. A phone that has never paired anywhere cannot be reached this
way at all: its Developer Mode setting is not even shown until pairing is
initiated. See references/first-time-setup.md.

After that one-time step, this resident service needs only the overlay address
(Tailscale / tailnet or any routed IPv4/IPv6 that reaches the phone) and does
the rest itself:

  * probes the phone's control port to confirm it is alive
  * publishes the Bonjour proxy record with a self-generated identity
  * lays the control relay and follows iOS 27's per-session tunnel-port drift
    (endpoint re-drifts ~every 33s, port counter +1), prefetching the next
    few ports so a relay is listening before remotepairingd connects
  * reaps idle relays, so the process count stays in the low tens instead of
    the fixed 1006 that bridge.py's static port range spawns

Environment:
  PHONE        required — the phone's overlay address (IPv4 or IPv6)
  LOCAL_IP     optional — override the LAN IPv4 to bind and advertise on
  PREFETCH     optional — ports to pre-lay ahead of the drift (default 8)
  IDLE_TTL     optional — reap idle relays after N seconds (default 600)
  CLEAN_INTERVAL optional — reap sweep cadence (default 60)
  RP_INSTANCE / RP_AUTHTAG / RP_HOSTNAME
               optional — override the generated Bonjour identity with real
                          values captured from the phone if you have them

The generated identity is the empirically uncertain part: an already-paired
phone authenticated through a stale, fabricated authTag during testing, which
suggests the TXT values are not cryptographically bound for a paired peer. If
authentication fails with generated values, capture the phone's real TXT and
set RP_INSTANCE / RP_AUTHTAG.
"""
import asyncio
import ipaddress
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid


CONTROL_PORT = 49152
MIN_PORT, MAX_PORT = 49152, 65535
PREFETCH = int(os.environ.get("PREFETCH", "8"))
IDLE_TTL = float(os.environ.get("IDLE_TTL", "600"))
CLEAN_INTERVAL = float(os.environ.get("CLEAN_INTERVAL", "60"))
HEALTH_INTERVAL = 10.0
POLL_INTERVAL = 15.0
BOOTSTRAP_RETRY = 20.0
POLL_LOOKBACK_START = 30
POLL_LOOKBACK_MAX = 600
TUNNEL_BANDS = [(49800, 50000), (55000, 55300)]


def _local_lan_ipv4() -> str:
    """Primary IPv4 of the interface that carries the default route.

    The Bonjour proxy and the relays must be published on an address the Mac
    itself can listen on; the phone's overlay address is only the relay target.
    """
    route = subprocess.run(
        ["route", "-n", "get", "default"],
        capture_output=True, text=True).stdout
    match = re.search(r"interface:\s*(\S+)", route)
    iface = match.group(1) if match else "en0"
    out = subprocess.run(
        ["ifconfig", iface], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if "inet " in line and "inet6" not in line:
            return line.split()[1]
    raise SystemExit(f"No IPv4 on default-route interface {iface}; set LOCAL_IP")


def _random_auth_tag() -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(alphabet[b & 61] for b in os.urandom(8))


PHONE = os.environ.get("PHONE") or (sys.argv[1] if len(sys.argv) > 1 else "")
if not PHONE:
    raise SystemExit("Set PHONE to the phone's overlay address (or pass it as argv[1])")

LOCAL_IP = os.environ.get("LOCAL_IP") or _local_lan_ipv4()
LOCAL_VERSION = ipaddress.ip_address(LOCAL_IP).version
REMOTE_VERSION = ipaddress.ip_address(PHONE).version
SPOOF_HOSTNAME = os.environ.get("RP_HOSTNAME", f"phone-bridge-{uuid.uuid4().hex[:6]}.local")
RP_INSTANCE = os.environ.get("RP_INSTANCE") or str(uuid.uuid4())
RP_AUTHTAG = os.environ.get("RP_AUTHTAG") or _random_auth_tag()
RP_VER = os.environ.get("RP_VER", "26")
RP_MINVER = os.environ.get("RP_MINVER", "8")
RP_FLAGS = os.environ.get("RP_FLAGS", "0")

ENDPOINT_RE = re.compile(re.escape(LOCAL_IP) + r"(?:%[A-Za-z0-9]+)?:(\d+)")
LOCAL_PORT_RE = re.compile(re.escape(LOCAL_IP) + r":(\d+)->")


def relay_command(port: int, protocol: str) -> list[str]:
    # socat's listener address family must match the LOCAL bind, not the
    # remote target: TCP6-LISTEN rejects an IPv4 bind literal outright, so a
    # phone reached over an IPv6 overlay while the Mac advertises IPv4 would
    # fail to start any relay at all.
    target = f"[{PHONE}]:{port}" if REMOTE_VERSION == 6 else f"{PHONE}:{port}"
    if protocol == "TCP":
        target += ",connect-timeout=5"
    return [shutil.which("socat"), "-d", "-d",
            f"{protocol}{LOCAL_VERSION}-LISTEN:{port},bind={LOCAL_IP},reuseaddr,fork",
            f"{protocol}:{target}"]


def probe_control() -> bool:
    try:
        with socket.create_connection((PHONE, CONTROL_PORT), timeout=5):
            return True
    except OSError:
        return False


class Bridge:
    def __init__(self) -> None:
        self.relays: dict[tuple[int, str], subprocess.Popen] = {}
        self.last_seen: dict[int, float] = {}
        self.last_real = 0.0
        self.prefetched: set[int] = set()
        self.publisher: subprocess.Popen | None = None
        self.stopping = False
        self.control_ok = False
        self.lookback = POLL_LOOKBACK_START
        self.poll_due = 0.0
        self.bootstrap_retry = 0.0

    def _spawn(self, cmd: list[str]) -> subprocess.Popen:
        return subprocess.Popen(cmd, start_new_session=True)

    def up(self, port: int, *, warmup: bool = False) -> None:
        if not (MIN_PORT <= port <= MAX_PORT):
            return
        now = time.time()
        self.last_seen[port] = now
        if (port, "TCP") in self.relays:
            return
        for protocol in ("TCP", "UDP"):
            self.relays[(port, protocol)] = self._spawn(relay_command(port, protocol))
        print(f"[relay:{'warmup' if warmup else 'dynamic'}] up {port} "
              f"(TCP+UDP) -> [{PHONE}]:{port}", flush=True)
        if warmup:
            self.prefetched.add(port)
        elif port != CONTROL_PORT:
            self.last_real = now
            for nxt in range(port + 1, port + 1 + PREFETCH):
                self.up(nxt, warmup=True)

    def down(self, port: int) -> None:
        for protocol in ("TCP", "UDP"):
            child = self.relays.pop((port, protocol), None)
            if child is None:
                continue
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                child.wait()
        self.prefetched.discard(port)
        self.last_seen.pop(port, None)
        print(f"[relay] down {port} (idle)", flush=True)

    def publish(self) -> None:
        if self.publisher is not None and self.publisher.poll() is None:
            return
        self.publisher = self._spawn([
            "dns-sd", "-P", RP_INSTANCE, "_remotepairing._tcp", "local",
            str(CONTROL_PORT), SPOOF_HOSTNAME, LOCAL_IP,
            f"identifier={RP_INSTANCE}", f"authTag={RP_AUTHTAG}",
            f"ver={RP_VER}", f"minVer={RP_MINVER}", f"flags={RP_FLAGS}"])
        print(f"[publish] {RP_INSTANCE} authTag={RP_AUTHTAG} "
              f"@ {LOCAL_IP}:{CONTROL_PORT}", flush=True)

    def reap_dead(self) -> None:
        for key in list(self.relays):
            child = self.relays[key]
            if child.poll() is not None:
                self.relays.pop(key, None)
                print(f"[relay] {key} exited early (rc={child.returncode})", flush=True)

    def poll_endpoints(self) -> list[int]:
        try:
            out = subprocess.run(
                ["log", "show", "--last", f"{self.lookback}s", "--style", "compact",
                 "--predicate", 'eventMessage CONTAINS "tunnel endpoint"'],
                capture_output=True, text=True, timeout=30).stdout
        except (OSError, subprocess.SubprocessError):
            return []
        ports = [int(m.group(1)) for m in ENDPOINT_RE.finditer(out)]
        self.lookback = POLL_LOOKBACK_START if ports else min(self.lookback * 2,
                                                              POLL_LOOKBACK_MAX)
        return ports

    def sweep_tunnel_bands(self) -> None:
        """Probe known bands so remotepairingd emits a tunnel-endpoint event."""
        for start, end in TUNNEL_BANDS:
            for port in range(start, end + 1, 64):
                if port not in self.relays:
                    self.up(port, warmup=True)

    async def watch(self) -> None:
        while not self.stopping:
            proc = await asyncio.create_subprocess_exec(
                "log", "stream", "--style", "ndjson",
                "--predicate", 'eventMessage CONTAINS "tunnel endpoint"',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL)
            self.log_proc = proc
            assert proc.stdout
            async for raw in proc.stdout:
                for match in ENDPOINT_RE.finditer(raw.decode("utf-8", "replace")):
                    self.up(int(match.group(1)))
            if not self.stopping:
                print("[watch] log stream ended; restarting", flush=True)
                await asyncio.sleep(5)

    async def _busy_ports(self) -> set[int]:
        proc = await asyncio.create_subprocess_exec(
            "lsof", "-nP", "-iTCP", "-sTCP:ESTABLISHED",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        assert proc.stdout
        result: set[int] = set()
        async for raw in proc.stdout:
            match = LOCAL_PORT_RE.search(raw.decode("utf-8", "replace"))
            if match:
                result.add(int(match.group(1)))
        await proc.wait()
        return result

    async def cleanup_loop(self) -> None:
        while not self.stopping:
            await asyncio.sleep(CLEAN_INTERVAL)
            busy = await self._busy_ports()
            now = time.time()
            for port in list(self.last_seen):
                if port == CONTROL_PORT or port in busy:
                    continue
                base = self.last_real if port in self.prefetched else self.last_seen.get(port, now)
                if now - base > IDLE_TTL:
                    self.down(port)

    def stop(self) -> None:
        if self.stopping:
            return
        self.stopping = True
        if self.log_proc is not None and self.log_proc.returncode is None:
            self.log_proc.terminate()
        for child in [*self.relays.values(),
                      *([self.publisher] if self.publisher else [])]:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        for child in [*self.relays.values(),
                      *([self.publisher] if self.publisher else [])]:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                child.wait()


async def main() -> int:
    for tool in ("socat", "dns-sd", "log", "lsof"):
        if not shutil.which(tool):
            print(f"Missing tool: {tool}", file=sys.stderr)
            return 1

    bridge = Bridge()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, bridge.stop)

    bridge.control_ok = probe_control()
    print(f"[probe] [{PHONE}]:{CONTROL_PORT} "
          f"{'OPEN' if bridge.control_ok else 'CLOSED'}", flush=True)
    if not bridge.control_ok:
        print("Control port closed: phone may be offline, not associated with "
              "Wi-Fi, or the overlay route is down. Continuing to publish "
              "anyway; it will connect when the phone becomes reachable.",
              file=sys.stderr, flush=True)

    bridge.up(CONTROL_PORT)
    await asyncio.sleep(0.2)
    bridge.reap_dead()
    ports = bridge.poll_endpoints()
    if ports:
        bridge.up(ports[-1])
        print(f"[bootstrap] latest known endpoint {ports[-1]}", flush=True)
    else:
        bridge.bootstrap_retry = time.time() + BOOTSTRAP_RETRY
        print(f"[bootstrap] no endpoint yet; retry in {BOOTSTRAP_RETRY:.0f}s", flush=True)
    bridge.publish()

    tasks = [asyncio.create_task(bridge.watch()),
             asyncio.create_task(bridge.cleanup_loop())]
    try:
        while not bridge.stopping:
            now = time.time()
            await asyncio.sleep(HEALTH_INTERVAL)
            bridge.reap_dead()
            if bridge.publisher is not None and bridge.publisher.poll() is not None:
                print("[publish] dns-sd exited; restarting", flush=True)
                bridge.publish()

            if now >= bridge.poll_due:
                bridge.poll_due = now + POLL_INTERVAL
                alive = probe_control()
                if alive != bridge.control_ok:
                    print(f"[health] control {bridge.control_ok} -> {alive}", flush=True)
                    bridge.control_ok = alive
                    bridge.lookback = POLL_LOOKBACK_MAX
                if not alive:
                    for port in bridge.poll_endpoints():
                        bridge.up(port)
                    if not any(p != CONTROL_PORT for p in bridge.last_seen):
                        bridge.sweep_tunnel_bands()
                if bridge.bootstrap_retry and now >= bridge.bootstrap_retry:
                    bridge.bootstrap_retry = 0.0
                    found = bridge.poll_endpoints()
                    if found:
                        bridge.up(found[-1])
                        print(f"[bootstrap] late endpoint {found[-1]}", flush=True)
                    else:
                        bridge.bootstrap_retry = now + BOOTSTRAP_RETRY
    finally:
        for task in tasks:
            task.cancel()
        bridge.stop()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
