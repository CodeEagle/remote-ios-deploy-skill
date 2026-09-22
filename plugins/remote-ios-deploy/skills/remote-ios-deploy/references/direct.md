# Direct cross-network deployment

## Prepare a different Mac

For a never-paired phone or a new deployment Mac, follow [First-time setup](first-time-setup.md) before using this procedure. An already valid pairing need not be repeated merely because the skill was installed.

Use macOS, an Xcode version supporting the phone OS, Python 3, `socat` (`brew install socat`), and the macOS `dns-sd` utility. Set `DEVELOPER_DIR` to the intended Xcode installation if several exist. The phone must be in Developer Mode; unlock it when preparing developer support or launching.

Pair **each deployment Mac** with the phone before it leaves, preferably with a one-time USB connection and a successful device build/run. A helper Mac's trust and a copied skill are not a substitute. Remote first-time pairing through this bridge has not been validated. Use the supported Xcode pairing workflow; do not export an entire Keychain or silently erase trust to repair a connection.

Configure the correct team's signing assets on this Mac and include the phone UDID in its provisioning profile. Preserve the user's team; do not switch to an unrelated available identity. Do not disable code signing to make a device build appear successful.

The VPN/overlay must support system TCP/UDP socket access to the phone's service endpoint. A working web page, VPN icon, or outbound Internet access does not prove inbound developer-service reachability. An application-level HTTP proxy is not a substitute for the required TCP/UDP routing. Check the selected client's routing, inbound-access, and background-execution behavior; do not assume different VPN products behave identically.

## Discover the real phone identity

On a trusted Mac on the phone's current Wi-Fi, or during USB setup:

```bash
dns-sd -B _remotepairing._tcp local.
dns-sd -L '<real-instance>' _remotepairing._tcp local.
xcrun devicectl list devices
```

These discovery commands run continuously; stop after collecting the needed record. Verify instance-to-UDID mapping if multiple devices exist:

```bash
/usr/bin/log show --last 5m --style compact --predicate 'process == "remotepairingd"'
```

Capture hostname, service port, identifier, authTag, ver, minVer, and flags. UUID/TXT values may rotate. Previously captured values survived one observed switch, not all future sessions. No helper here auto-discovers a fresh remote Bonjour record after rotation.

When the phone is already remote and no trusted Mac sits on its current LAN, the real Bonjour instance can still be recovered from the deployment Mac's own `remotepairingd` history — it logs which adverts resolved to a known paired identity:

```bash
/usr/bin/log show --last 3d --style compact --predicate 'process == "remotepairingd"' \
  | grep 'Resolved bonjour advert'
```

An advert that resolved `to identity associated with udid <phone-udid>` is a real, still-trusted instance for this Mac. Do **not** substitute the CoreDevice identifier that `devicectl list devices` prints (the `…coredevice.local` hostname component) for the Bonjour instance — they are separate identifiers, and an advert carrying it resolves to `identity nil` and is tracked as an unauth device, surfacing as CoreDevice error 4016. A value that authenticates once stays valid until the pairing rotates; re-verify against this log before changing `RP_INSTANCE`.

Resolve the phone's overlay endpoint from its device/network information. Probe known candidates belonging to this phone only. Verify that a friendly hostname resolves to the actual developer-service endpoint; do not derive another address by changing an IP suffix without evidence.

## Configure and run

Copy `assets/bridge.env.example` to a private location and replace every value. Source it in the bridge terminal. `LOCAL_IP` is this deployment Mac's **LAN IPv4**, not the phone IP, a remote helper's IP, the VPN interface, or `0.0.0.0`. Use a trusted interface that supports local discovery. Get interface names with `networksetup -listallhardwareports` and addresses with `ifconfig`.

```bash
source /private/path/bridge.env
python3 /path/to/remote-ios-deploy/scripts/bridge.py --check
# Static supervisor: pinned TUNNEL_PORTS (pre-iOS-27 environments)
python3 /path/to/remote-ios-deploy/scripts/bridge.py > /private/path/bridge.log 2>&1
# Dynamic supervisor: iOS 27 re-drifts the tunnel endpoint every session
python3 /path/to/remote-ios-deploy/scripts/bridge-dynamic.py > /private/path/bridge.log 2>&1
```

The check only probes the control port. Starting **bridge.py** also checks all TCP/UDP listener bindings; the default data ranges plus the control port create **1006 relay processes**, favoring compatibility with observed ports over resource efficiency. Narrow the ranges only with evidence, expand if the phone negotiates outside them.

On **iOS 27** the CoreDevice tunnel endpoint re-drifts every session (~33s, the port counter incrementing by one), so any fixed range is refused and installs fail with `RemotePairingError code 4`. Prefer **bridge-dynamic.py**: it tails `log stream` for freshly negotiated endpoints, raises one TCP+UDP relay per port, and prefetches the next `PREFETCH` ports (default 8) so a relay is already listening before `remotepairingd` connects — that daemon connects within ~5-10ms of seeing an endpoint, so a purely reactive relay is always too late. Relays with no established connection are reaped after `IDLE_TTL` (600s). Verified outcome: `Tunnel connection established` with zero refused after switching, where the static bridge refused every drift cycle. Neither variant is a promise that a given iOS version uses these ports.

Keep the foreground bridge running; Ctrl-C terminates only its own process groups, including relay children. Never start duplicates or use `killall socat`. No LaunchAgent, automatic network reconfiguration, or firewall changes are installed by this skill. The script can be run from anywhere; it does not read a config file implicitly.

In a second terminal, verify the target is `available (paired)` or connected, then build and deploy:

```bash
xcrun devicectl list devices --timeout 20
python3 /path/to/remote-ios-deploy/scripts/build_deploy.py \
  --project /path/to/App.xcodeproj --scheme App \
  --bundle-id com.example.App --device '<phone-udid>' \
  --derived-data /private/path/DeviceBuild
```

Use `--workspace` instead of `--project` when appropriate. Configure team/signing in the project, or deliberately pass `--team`. `--skip-macro-validation` is optional and only for trusted macro dependencies; do not bypass validation by default.

The helper builds current source and resolves the exact `.app` using build settings. Build failure stops before installation. It records both executable and debug-dylib UUID when present, verifies signing, and checks the same launched PID/path at 5 and 35 seconds. A connection failure is not automatically an app crash; read the diagnostic files.

## Prove the route and runtime

```bash
/usr/bin/log show --last 5m --style compact \
  --predicate 'process == "remotepairingd"' \
  | rg 'tunnel endpoint|Tunnel connection established|authenticated'
rg 'opening connection|successfully connected|starting data transfer' /private/path/bridge.log
```

Require a tunnel destination matching the Mac's relay address and matching relay transfer to the phone endpoint, plus successful installation. A Wi-Fi interface label alone is insufficient. Ask the user to open/operate the relevant UI; do not claim camera or interaction correctness from PID survival.

For crashes, use `devicectl device info files --domain-type systemCrashLogs --search '<AppName>' --device '<udid>'` and `device copy from` for the selected IPS. Compare its binary UUID with the installed artifact. IPS may contain a header JSON object followed by a second JSON object, not one standard JSON document.

## Diagnose by layer

| Failure | Next check |
|---|---|
| Control port refused or timed out | Actual service address, overlay routes/mode, phone Wi-Fi association and developer-service state; not just VPN online |
| Local bind fails | Existing listener ownership; stop only the identified duplicate bridge |
| Bonjour maps to no identity | Actual instance and target phone; deployment Mac's own pairing trust |
| Control authentication passes but no tunnel | Negotiated data ports, TCP/UDP connectivity, network switch recovery |
| CoreDevice 4000/4016 | Preserve error detail, re-probe, await authentication recovery; retry install once |
| Signing failure | Correct team/certificate/private key/profile/UDID, not networking |
| Launch succeeds but PID disappears | Crash logs, artifact freshness and UUID; launch response alone is not success |

LAN listeners expose forwarded developer endpoints to hosts able to reach that LAN IP. Use trusted networks and appropriate source restrictions; do not publish these ports on a public router. Stop the bridge when not needed. Keep logs private.

Sources: [Apple device management](https://developer.apple.com/documentation/xcode/managing-your-simulated-and-physical-devices-in-device-hub), [original bridge author's experiment](https://dev.to/kvnpt/how-to-remotely-iterate-deploy-your-sideloaded-ios-apps-over-tailnet-jak). Consult current official documentation for the selected VPN client and Xcode version; these scripts do not freeze those external contracts.
