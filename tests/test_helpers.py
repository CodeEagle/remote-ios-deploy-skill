import importlib.util
import json
import os
import pathlib
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


bridge = module('bridge')
deploy = module('build_deploy')


def sample_env():
    return dict(PHONE_ADDRESS='127.0.0.2', LOCAL_IP='127.0.0.1',
                RP_HOSTNAME='test-phone.local', RP_INSTANCE='unit-test',
                RP_AUTHTAG='unit-test', RP_VER='26', RP_MINVER='8', RP_FLAGS='0')


class ConfigurationTests(unittest.TestCase):
    def test_port_ranges_and_deduplication(self):
        self.assertEqual(bridge.parse_ports('50001-50003,50002,49152'), [49152, 50001, 50002, 50003])

    def test_invalid_or_oversized_ranges_rejected(self):
        for value in ('0', '65536', '5-1', '1-2-3', '1,', 'x', '1-5000'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bridge.parse_ports(value)

    def test_missing_identity_fails_before_network(self):
        with self.assertRaisesRegex(ValueError, 'PHONE_ADDRESS'):
            bridge.settings({})

    def test_rejects_unconfigured_template_and_wildcard_binding(self):
        for value in ('REPLACE_THIS_MAC_LAN_IPV4', '0.0.0.0'):
            env = sample_env()
            env['LOCAL_IP'] = value
            with self.assertRaises(ValueError):
                bridge.settings(env)

    def test_socat_endpoint_cannot_inject_options(self):
        env = sample_env()
        env['PHONE_ADDRESS'] = '127.0.0.2,exec=bad'
        with self.assertRaises(ValueError):
            bridge.settings(env)

    def test_ipv6_relay_commands(self):
        env = sample_env()
        env.update(PHONE_ADDRESS='2001:db8::1', TUNNEL_PORTS='49941')
        commands = list(bridge.relay_commands(bridge.settings(env), '/usr/bin/socat'))
        self.assertEqual(len(commands), 4)
        self.assertIn('TCP6:[2001:db8::1]:49941,connect-timeout=5', commands[-2])
        self.assertIn('UDP6:[2001:db8::1]:49941', commands[-1])

    def test_tcp_and_udp_listener_conflicts_are_not_ignored(self):
        for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
            with socket.socket(socket.AF_INET, kind) as listener:
                listener.bind(('127.0.0.1', 0))
                if kind == socket.SOCK_STREAM:
                    listener.listen(1)
                with self.assertRaises(OSError):
                    bridge.check_listeners('127.0.0.1', [listener.getsockname()[1]])


class DeploymentTests(unittest.TestCase):
    def settings(self, platform='iphoneos', bundle='com.example.Probe', path='/tmp/device-build'):
        return {'buildSettings': dict(PRODUCT_BUNDLE_IDENTIFIER=bundle,
                WRAPPER_EXTENSION='app', PLATFORM_NAME=platform,
                TARGET_BUILD_DIR=path, FULL_PRODUCT_NAME='Probe.app')}

    def test_selects_only_intended_device_product(self):
        rows = [self.settings(platform='iphonesimulator'), self.settings(bundle='com.example.Other'), self.settings()]
        self.assertEqual(deploy.select_app(rows, 'com.example.Probe'), pathlib.Path('/tmp/device-build/Probe.app'))

    def test_ambiguous_product_stops(self):
        with self.assertRaises(ValueError):
            deploy.select_app([self.settings(), self.settings(path='/tmp/other')], 'com.example.Probe')

    def test_launch_response_is_not_runtime_success(self):
        launch = {'info': {'outcome': 'success'}, 'result': {'process': {'processIdentifier': 123, 'executable': 'file:///Probe.app/Probe'}}}
        for processes in ([], [{'processIdentifier': 124, 'executable': 'file:///Probe.app/Probe'}],
                          [{'processIdentifier': 123, 'executable': 'file:///Other.app/Other'}]):
            with self.assertRaises(ValueError):
                deploy.require_same_process(launch, {'result': {'runningProcesses': processes}})
        self.assertEqual(deploy.require_same_process(launch, {'result': {'runningProcesses': [launch['result']['process']]}}), 123)

    def test_failed_build_never_installs_cached_app(self):
        with tempfile.TemporaryDirectory() as temp:
            project = pathlib.Path(temp) / 'Probe.xcodeproj'
            project.mkdir()
            args = ['build_deploy.py', '--project', str(project), '--scheme', 'Probe',
                    '--bundle-id', 'com.example.Probe', '--device', 'unit-test']
            with mock.patch.object(sys, 'argv', args), \
                 mock.patch.object(deploy.tempfile, 'mkdtemp', return_value=temp), \
                 mock.patch.object(deploy.subprocess, 'run', side_effect=subprocess.CalledProcessError(65, 'xcodebuild')) as run:
                self.assertEqual(deploy.main(), 1)
                self.assertEqual(run.call_count, 1)
                self.assertEqual(run.call_args.args[0][0], 'xcodebuild')


@unittest.skipUnless(shutil.which('socat'), 'socat not installed; install it for relay integration coverage')
class RelayIntegrationTests(unittest.TestCase):
    def test_tcp_transfer_and_signal_cleanup_without_bonjour(self):
        # No real phone or multicast advertisement: replace only discovery with sleep.
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            server.bind(('::1', 0))
            server.listen(4)
            server.settimeout(8)
            port = server.getsockname()[1]
            env = sample_env()
            env.update(PHONE_ADDRESS='::1', CONTROL_PORT=str(port), TUNNEL_PORTS=str(port))
            data = bridge.settings(env)
            code = '''import sys,subprocess
sys.path.insert(0,sys.argv[1])
import bridge,json
real=bridge.subprocess.Popen
def spawn(command,**kwargs):
    return real(['/bin/sleep','60'] if command[0]=='fake-discovery' else command,**kwargs)
bridge.subprocess.Popen=spawn
bridge.supervise(json.loads(sys.argv[2]),sys.argv[3],'fake-discovery')
'''
            errors = []
            def echo():
                try:
                    with server.accept()[0] as peer:
                        peer.settimeout(5)
                        peer.sendall(peer.recv(64))
                except OSError as error:
                    errors.append(error)
            worker = threading.Thread(target=echo, daemon=True)
            worker.start()
            child = subprocess.Popen([sys.executable, '-c', code, str(ROOT/'scripts'), json.dumps(data), shutil.which('socat')],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                time.sleep(1.5)
                self.assertIsNone(child.poll())
                with socket.create_connection(('127.0.0.1', port), timeout=3) as client:
                    client.sendall(b'bridge-test')
                    client.settimeout(3)
                    self.assertEqual(client.recv(64), b'bridge-test')
                worker.join(timeout=5)
                self.assertFalse(errors)
            finally:
                if child.poll() is None:
                    child.send_signal(signal.SIGTERM)
                child.communicate(timeout=10)
            bridge.check_listeners('127.0.0.1', [port])


if __name__ == '__main__':
    unittest.main()
