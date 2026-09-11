#!/usr/bin/env python3
"""Explicitly configured, fail-fast Bonjour + socat relay supervisor (macOS)."""
import argparse
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
    if len(result) > 2048:
        raise ValueError('More than 2048 ports; narrow to observed tunnel ranges')
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
    data['ports'] = sorted(set(control + parse_ports(env.get('TUNNEL_PORTS', '49800-50000,55000-55300'))))
    data['remote_version'] = remote.version
    return data


def probe(address, port):
    with socket.create_connection((address, port), timeout=5):
        pass


def check_listeners(address, ports):
    # Close probes promptly to fit macOS descriptor limits; child startup
    # checks catch a listener that loses the subsequent bind/start race.
    for port in ports:
        for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
            with socket.socket(socket.AF_INET, kind) as sock:
                if kind == socket.SOCK_STREAM:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((address, port))
                if kind == socket.SOCK_STREAM:
                    sock.listen(1)


def relay_commands(data, socat):
    for port in data['ports']:
        for protocol in ('TCP', 'UDP'):
            target = data['PHONE_ADDRESS']
            if data['remote_version'] == 6:
                target = f'[{target}]'
            remote = f'{protocol}{data["remote_version"]}:{target}:{port}'
            if protocol == 'TCP':
                remote += ',connect-timeout=5'
            yield [socat, '-d', '-d',
                   f'{protocol}4-LISTEN:{port},bind={data["LOCAL_IP"]},reuseaddr,fork', remote]


def stop_children(children):
    # Each child has a dedicated session, including any socat fork descendants.
    for child in children:
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for child in children:
        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()


def supervise(data, socat, dns_sd):
    children = []
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    previous = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        for command in relay_commands(data, socat):
            children.append(subprocess.Popen(command, start_new_session=True))
        time.sleep(1)
        if any(child.poll() is not None for child in children):
            raise RuntimeError('A relay exited during startup; Bonjour was not published')
        command = [dns_sd, '-P', data['RP_INSTANCE'], '_remotepairing._tcp', 'local',
                   str(data['control']), data['RP_HOSTNAME'], data['LOCAL_IP'],
                   f'identifier={data["RP_INSTANCE"]}', f'authTag={data["RP_AUTHTAG"]}',
                   f'ver={data["RP_VER"]}', f'minVer={data["RP_MINVER"]}', f'flags={data["RP_FLAGS"]}']
        children.append(subprocess.Popen(command, start_new_session=True))
        print(f'Bridge started ({len(children)-1} relays). Installation is NOT yet verified.', flush=True)
        while True:
            time.sleep(1)
            if any(child.poll() is not None for child in children):
                raise RuntimeError('A bridge child exited; stopping this bridge')
    finally:
        for sig in previous:
            signal.signal(sig, signal.SIG_IGN)
        stop_children(children)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='probe the phone control port only')
    args = parser.parse_args()
    try:
        data = settings(os.environ)
        probe(data['PHONE_ADDRESS'], data['control'])
        print('Phone control port reachable; pairing, tunnel and install remain unverified.', flush=True)
        if args.check:
            return 0
        socat, dns_sd = shutil.which('socat'), shutil.which('dns-sd')
        if not socat or not dns_sd:
            raise RuntimeError('Install socat; dns-sd must be available (macOS)')
        check_listeners(data['LOCAL_IP'], data['ports'])
        supervise(data, socat, dns_sd)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, RuntimeError) as error:
        print(f'Bridge stopped: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
