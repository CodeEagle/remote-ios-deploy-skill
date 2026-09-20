#!/usr/bin/env python3
"""Dynamic Bonjour + socat relay supervisor for iOS 27 tunnel-port drift (macOS).

The static `bridge.py` binds a fixed TUNNEL_PORTS range. On iOS 27 the CoreDevice
tunnel endpoint re-drifts every session (~33s, port counter incrementing by one),
so a fixed range is reliably refused and devicectl/Xcode fail with
RemotePairingError code 4. This variant instead:

- keeps the CONTROL_PORT relay (TCP+UDP) and the dns-sd advertisement resident;
- tails `log stream` for freshly negotiated tunnel endpoints and raises a
  TCP+UDP socat per port on demand;
- prefetches P+1..P+PREFETCH when a real endpoint P is negotiated, because
  remotepairingd connects within ~5-10ms of seeing the endpoint and any
  log-parsing relay starts strictly too late;
- reaps relays that have had no established connection and were not renegotiated
  within IDLE_TTL, so drifted sessions do not accumulate idle socats.

All device/network values must be set explicitly in the environment; there are
no baked-in defaults for phone address or pairing material.
"""
import argparse
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


def parse_ports(value):
    result = set()
    for part in value.split(','):
        limits = part.strip().split('-')
        if len(limits) not in (1, 2) or not all(x.isdigit() for x in limits):
            raise ValueError('Ports must be comma-separated integers or inclusive ranges')
        start, end = int(limits[0]), int(limits[-1])
        if not 1 <= start <= end <= 65535:
            raise ValueError('Invalid port range')
        result.update(range(start, end + 1))
    return sorted(result)


def settings(env):
    names = ('PHONE_ADDRESS', 'LOCAL_IP', 'RP_HOSTNAME', 'RP_INSTANCE', 'RP_AUTHTAG',
             'RP_VER', 'RP_MINVER', 'RP_FLAGS')
    data = {}
    for name in names:
        value = env.get(name, '')
        if not value or 'REPLACE_' in value or any(ord(c) < 32 for c in value):
            raise ValueError(f'Set {name} explicitly from verified device/network information')
        data[name] = value
    remote = ipaddress.ip_address(data['PHONE_ADDRESS'])
    local = ipaddress.IPv4Address(data['LOCAL_IP'])
    if any(ip.is_unspecified or ip.is_multicast for ip in (remote, local)):
        raise ValueError('Unspecified/multicast addresses are not relay endpoints')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*\.local\.?', data['RP_HOSTNAME']):
        raise ValueError('RP_HOSTNAME must be the discovered .local hostname')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', data['RP_INSTANCE']):
        raise ValueError('Invalid Bonjour instance identifier')
    for name in ('RP_VER', 'RP_MINVER', 'RP_FLAGS'):
        if not data[name].isdigit():
            raise ValueError(f'{name} must be an integer TXT value')
    control = parse_ports(env.get('CONTROL_PORT', '49152'))
    if len(control) != 1:
        raise ValueError('CONTROL_PORT must select exactly one port')
    data['control'] = control[0]
    data['remote_version'] = remote.version
    data['prefetch'] = int(env.get('PREFETCH', '8'))
    data['idle_ttl'] = float(env.get('IDLE_TTL', '600'))
    data['clean_interval'] = float(env.get('CLEAN_INTERVAL', '60'))
    # Tunnel endpoint logs look like: 192.168.6.141%en1:60852
    data['endpoint_re'] = re.compile(rf'{re.escape(data["LOCAL_IP"])}(?:%[A-Za-z0-9]+)?:(\d+)')
    return data


def probe(address, port):
    with socket.create_connection((address, port), timeout=5):
        pass


def relay_command(data, socat, port, protocol):
    target = data['PHONE_ADDRESS']
    if data['remote_version'] == 6:
        target = f'[{target}]'
    remote = f'{protocol}{data["remote_version"]}:{target}:{port}'
    if protocol == 'TCP':
        remote += ',connect-timeout=5'
    return [socat, '-d', '-d',
            f'{protocol}4-LISTEN:{port},bind={data["LOCAL_IP"]},reuseaddr,fork', remote]


class Bridge:
    def __init__(self, data, socat, dns_sd):
        self.data = data
        self.socat = socat
        self.dns_sd = dns_sd
        self.control = data['control']
        # (port, protocol) -> Popen
        self.relays = {}
        self.last_seen = {}
        # Prefetched ports are recharged against the last real negotiation time,
        # so the prefetch window survives idle reaping until the whole session
        # goes quiet; otherwise a resumed drift would hit a cold window.
        self.last_real = 0.0
        self.prefetched = set()
        self.publisher = None
        self.stopping = False

    def _spawn(self, cmd):
        return subprocess.Popen(cmd, start_new_session=True)

    def up(self, port, *, warmup=False):
        """Raise a TCP+UDP relay for port; refresh its negotiation time.

        A real (non-warmup) tunnel endpoint also prefetches the next PREFETCH
        ports, which covers the ~33s counter drift. The control channel does
        not drift and is never prefetched.
        """
        if not (1 <= port <= 65535):
            return
        now = time.time()
        self.last_seen[port] = now
        if (port, 'TCP') in self.relays:
            return
        for protocol in ('TCP', 'UDP'):
            self.relays[(port, protocol)] = self._spawn(
                relay_command(self.data, self.socat, port, protocol))
        kind = 'prefetch' if warmup else 'dynamic'
        print(f'[relay:{kind}] up {port} (TCP+UDP)', flush=True)
        if warmup:
            self.prefetched.add(port)
        elif port != self.control:
            self.last_real = now
            for nxt in range(port + 1, port + 1 + self.data['prefetch']):
                self.up(nxt, warmup=True)

    def down(self, port):
        for protocol in ('TCP', 'UDP'):
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
        print(f'[relay] down {port} (idle, no active connection)', flush=True)

    def publish(self):
        d = self.data
        self.publisher = self._spawn([
            self.dns_sd, '-P', d['RP_INSTANCE'], '_remotepairing._tcp', 'local',
            str(self.control), d['RP_HOSTNAME'], d['LOCAL_IP'],
            f'identifier={d["RP_INSTANCE"]}', f'authTag={d["RP_AUTHTAG"]}',
            f'ver={d["RP_VER"]}', f'minVer={d["RP_MINVER"]}', f'flags={d["RP_FLAGS"]}'])
        print(f'[publish] {d["RP_INSTANCE"]} @ {d["LOCAL_IP"]}:{self.control}', flush=True)

    def reap_dead(self):
        for key in list(self.relays):
            child = self.relays[key]
            if child.poll() is not None:
                self.relays.pop(key, None)
                print(f'[relay] {key} exited early (rc={child.returncode})', flush=True)

    async def watch(self):
        proc = await asyncio.create_subprocess_exec(
            'log', 'stream', '--style', 'ndjson',
            '--predicate', 'eventMessage CONTAINS "tunnel endpoint"',
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        assert proc.stdout
        async for raw in proc.stdout:
            for match in self.data['endpoint_re'].finditer(raw.decode('utf-8', 'replace')):
                self.up(int(match.group(1)))

    async def _busy_ports(self):
        proc = await asyncio.create_subprocess_exec(
            'lsof', '-nP', '-iTCP', '-sTCP:ESTABLISHED',
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        assert proc.stdout
        local_re = re.compile(rf'{re.escape(self.data["LOCAL_IP"])}:(\d+)->')
        result = set()
        async for raw in proc.stdout:
            match = local_re.search(raw.decode('utf-8', 'replace'))
            if match:
                result.add(int(match.group(1)))
        await proc.wait()
        return result

    async def cleanup_loop(self):
        while not self.stopping:
            await asyncio.sleep(self.data['clean_interval'])
            busy = await self._busy_ports()
            now = time.time()
            for port in list(self.last_seen):
                if port == self.control or port in busy:
                    continue
                base = self.last_real if port in self.prefetched else self.last_seen.get(port, now)
                if now - base > self.data['idle_ttl']:
                    self.down(port)

    def stop(self):
        if self.stopping:
            return
        self.stopping = True
        procs = list(self.relays.values())
        if self.publisher is not None:
            procs.append(self.publisher)
        for child in procs:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        for child in procs:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                child.wait()


def bootstrap_current_endpoint(bridge):
    """Raise the most recently negotiated endpoint at startup.

    Takes only the latest match (usually the phone's current port); older
    drifted ports are intentionally not preheated.
    """
    try:
        out = subprocess.run(
            ['log', 'show', '--last', '2m', '--style', 'compact',
             '--predicate', 'eventMessage CONTAINS "tunnel endpoint"'],
            capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return
    ports = [int(m.group(1)) for m in bridge.data['endpoint_re'].finditer(out)]
    if ports:
        bridge.up(ports[-1])
        print(f'[bootstrap] latest known endpoint {ports[-1]}', flush=True)


async def run(bridge):
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, bridge.stop)
    bridge.up(bridge.control)
    await asyncio.sleep(0.2)
    bridge.reap_dead()
    bootstrap_current_endpoint(bridge)
    bridge.publish()
    tasks = [
        asyncio.create_task(bridge.watch()),
        asyncio.create_task(bridge.cleanup_loop()),
    ]
    try:
        while not bridge.stopping:
            await asyncio.sleep(5)
            bridge.reap_dead()
            if bridge.publisher is not None and bridge.publisher.poll() is not None:
                print('[publish] dns-sd exited; restarting', flush=True)
                bridge.publish()
    finally:
        for task in tasks:
            task.cancel()
        bridge.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='probe the phone control port only')
    args = parser.parse_args()
    try:
        data = settings(os.environ)
        probe(data['PHONE_ADDRESS'], data['control'])
        print('Phone control port reachable; pairing, tunnel and install remain '
              'unverified.', flush=True)
        if args.check:
            return 0
        socat, dns_sd = shutil.which('socat'), shutil.which('dns-sd')
        for tool, name in ((socat, 'socat'), (dns_sd, 'dns-sd')):
            if not tool:
                raise RuntimeError(f'Install {name}; dns-sd must be available (macOS)')
        bridge = Bridge(data, socat, dns_sd)
        asyncio.run(run(bridge))
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, RuntimeError) as error:
        print(f'Bridge stopped: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
