#!/usr/bin/env python3
"""Build current source, install a selected iOS app, verify its launched PID."""
import argparse
import json
import pathlib
import plistlib
import subprocess
import sys
import tempfile
import time


def checked(command, log_path=None):
    if log_path:
        with open(log_path, 'w') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)
    else:
        subprocess.run(command, check=True)


def select_app(settings, bundle_id):
    matches = []
    for target in settings:
        values = target.get('buildSettings', {})
        if (values.get('PRODUCT_BUNDLE_IDENTIFIER') == bundle_id
                and values.get('WRAPPER_EXTENSION') == 'app'
                and values.get('PLATFORM_NAME') == 'iphoneos'):
            matches.append(pathlib.Path(values['TARGET_BUILD_DIR']) / values['FULL_PRODUCT_NAME'])
    if len(set(matches)) != 1:
        raise ValueError('Build settings must identify exactly one matching iphoneos .app')
    return matches[0]


def validate_bundle(app, bundle_id):
    with open(app / 'Info.plist', 'rb') as stream:
        info = plistlib.load(stream)
    if info.get('CFBundleIdentifier') != bundle_id:
        raise ValueError('Built bundle ID differs from requested target')
    executable = info.get('CFBundleExecutable', '')
    if not executable or pathlib.Path(executable).name != executable:
        raise ValueError('Invalid CFBundleExecutable')
    return executable


def require_same_process(launch, processes):
    if launch.get('info', {}).get('outcome') != 'success':
        raise ValueError('Launch response was not successful')
    process = launch['result']['process']
    if not any(p.get('processIdentifier') == process['processIdentifier']
               and p.get('executable') == process['executable']
               for p in processes['result']['runningProcesses']):
        raise ValueError('Launched PID/executable disappeared; inspect crash logs and device state')
    return process['processIdentifier']


def device_json(device, command, path, timeout):
    checked(['xcrun', 'devicectl', 'device', *command, '--device', device,
             '--timeout', str(timeout), '--json-output', str(path)])
    with open(path) as stream:
        result = json.load(stream)
    if result.get('info', {}).get('outcome') != 'success':
        raise ValueError('devicectl did not report success')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    project = parser.add_mutually_exclusive_group(required=True)
    project.add_argument('--project', type=pathlib.Path)
    project.add_argument('--workspace', type=pathlib.Path)
    parser.add_argument('--scheme', required=True)
    parser.add_argument('--bundle-id', required=True)
    parser.add_argument('--device', required=True, help='intended phone UDID')
    parser.add_argument('--configuration', default='Debug')
    parser.add_argument('--derived-data', type=pathlib.Path)
    parser.add_argument('--team', help='explicit DEVELOPMENT_TEAM override; otherwise preserve project')
    parser.add_argument('--skip-macro-validation', action='store_true',
                        help='only for dependencies whose macros you trust')
    args = parser.parse_args()
    evidence = pathlib.Path(tempfile.mkdtemp(prefix='remote-ios-deploy-'))
    print(f'Evidence (may contain private device information): {evidence}', flush=True)
    try:
        kind = '-project' if args.project else '-workspace'
        source = (args.project or args.workspace).resolve(strict=True)
        derived = args.derived_data.resolve() if args.derived_data else evidence / 'DerivedData'
        base = ['xcodebuild', kind, str(source), '-scheme', args.scheme,
                '-configuration', args.configuration, '-sdk', 'iphoneos',
                '-destination', 'generic/platform=iOS', '-derivedDataPath', str(derived)]
        if args.team:
            base.append('DEVELOPMENT_TEAM=' + args.team)
        if args.skip_macro_validation:
            base.append('-skipMacroValidation')
        checked([*base, 'build'], evidence / 'build.log')
        # Only resolve/install an artifact after a successful build of this source.
        # Xcode warnings go to stderr; do not mix them into its JSON document.
        with open(evidence / 'settings.json', 'w') as output, open(evidence / 'settings.log', 'w') as errors:
            subprocess.run([*base, '-showBuildSettings', '-json'], stdout=output, stderr=errors, check=True)
        with open(evidence / 'settings.json') as stream:
            app = select_app(json.load(stream), args.bundle_id)
        executable = validate_bundle(app, args.bundle_id)
        checked(['codesign', '--verify', '--deep', '--strict', str(app)])
        checked(['xcrun', 'dwarfdump', '--uuid', str(app / executable)], evidence / 'binary-uuid.txt')
        debug = app / (executable + '.debug.dylib')
        if debug.exists():
            checked(['xcrun', 'dwarfdump', '--uuid', str(debug)], evidence / 'debug-dylib-uuid.txt')
        (evidence / 'artifact-path.txt').write_text(str(app) + '\n')
        device_json(args.device, ['install', 'app', str(app)], evidence / 'install.json', 90)
        launch = device_json(args.device, ['process', 'launch', args.bundle_id], evidence / 'launch.json', 30)
        started = time.monotonic()
        for elapsed in (5, 35):
            time.sleep(max(0, started + elapsed - time.monotonic()))
            processes = device_json(args.device, ['info', 'processes'],
                                    evidence / f'processes-{elapsed}s.json', 25)
            pid = require_same_process(launch, processes)
            print(f'PASS: same PID {pid} after at least {elapsed}s', flush=True)
        print('Startup smoke test passed. Confirm UI and bridge path separately.')
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f'Deployment stopped: {error}. Inspect {evidence}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
