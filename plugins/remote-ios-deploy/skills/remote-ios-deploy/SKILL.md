---
name: remote-ios-deploy
description: "Deploy and diagnose signed iOS apps from a Mac to a remote paired iPhone over a VPN or overlay network using a local Bonjour and TCP/UDP bridge. Use for cross-network Xcode/devicectl installation, network-switch recovery, and startup verification; distinguish direct deployment from consented IPA web distribution."
---

# Remote iOS Deploy

Deploy from the user's chosen Mac, prove the transport, and verify the app remains running. Do not silently move installation to a Mac near the phone.

## Choose the path

- **New phone, new deployment Mac, or uncertain pairing:** read [references/first-time-setup.md](references/first-time-setup.md) first. Explain the minimum phone-holder actions before starting. Remote first-time pairing is unvalidated; do not present this bridge as a way to bypass Trust or Developer Mode.
- **Direct development deployment:** read [references/direct.md](references/direct.md). The Mac needs its own pairing trust, compatible Xcode, signing assets, and a reachable phone developer service. Use the supplied bridge and build/deploy scripts.
- **Pure cellular / direct port unavailable:** distinguish overlay connectivity from developer-service availability. Our Wi-Fi → cellular → different Wi-Fi test failed on cellular and recovered on Wi-Fi. This is evidence about this bridge, not proof that all iOS distribution requires Wi-Fi. Do not keep retrying installation while the entry port is closed.
- **User accepts tapping an installation link:** read [references/web-distribution.md](references/web-distribution.md). This changes the workflow and may publish a signed IPA containing device metadata. Confirm that change and audience before hosting. Do not automatically create App Store records, upload to TestFlight, or change developer teams.

## Preserve these invariants

1. Obtain real Bonjour instance/TXT values and verify they belong to the intended phone. UDID, CoreDevice ID, hostname, and Bonjour instance are different identifiers. A hostname suffix is not evidence of another phone.
2. Probe the verified phone service address, not just its friendly domain or ping response. A device's advertised management address may differ from its reachable developer-service endpoint. Resolve this using device/network evidence; never guess an address suffix or scan unrelated hosts.
3. Bind relays to this Mac's trusted LAN IPv4 and publish Bonjour there. Forward the control port **and negotiated data ports** over TCP/UDP. The observed ranges are configurable, not a protocol guarantee.
4. Never copy entire Keychains, pairing databases, private keys, tokens, raw session logs, or signed apps into a public skill/repository. A remote helper Mac can collect discovery information; its pairing does not confer trust on a new deployment Mac.
5. Build current source before deploying unless the user deliberately selected an existing signed artifact. Record the artifact path and binary UUID. An old cached app can reproduce a crash already fixed in source.
6. `available`, a successful TCP probe, and a successful launch response are separate intermediate states. Success requires installation, a matching launch PID/executable still present after at least 35 seconds, and user confirmation of the relevant UI. Do not claim UI functionality from process survival alone.
7. Prove cross-network transport with a CoreDevice tunnel endpoint at the local relay address and contemporaneous relay output to the phone address. Interface names such as `en1` alone do not establish whether traffic was direct LAN or bridged.

## Helpers and stop conditions

- Copy [assets/bridge.env.example](assets/bridge.env.example) to a private location and replace its values. Only source a file you have reviewed; it is executable shell input.
- `python3 scripts/bridge.py --check` probes only the remote control port. `python3 scripts/bridge.py` checks listener conflicts, starts relays, and advertises only after startup checks. Ctrl-C stops this invocation's child process groups. It never kills unrelated listeners.
- On **iOS 27** the negotiated tunnel endpoint re-drifts every session (~33s, port counter incrementing by one), so a fixed `TUNNEL_PORTS` range is refused and installs fail with `RemotePairingError code 4`. Run `python3 scripts/bridge-dynamic.py` instead: it tails `log stream` for freshly negotiated endpoints, raises one relay per port, and prefetches the next `PREFETCH` ports (default 8) so a relay is listening before `remotepairingd` connects — that daemon connects within ~5-10ms, so a purely reactive relay is always too late. Same env vars (it ignores `TUNNEL_PORTS`) plus optional `PREFETCH`, `IDLE_TTL` (600s), `CLEAN_INTERVAL` (60s). Verified end to end on iOS 27: `Tunnel connection established`, zero refused, devicectl install succeeded.

  `bridge-dynamic.py` also refreshes itself across reconnects: it polls the remote control port every `POLL_INTERVAL`, retries `bootstrap_current_endpoint` for `BOOTSTRAP_RETRY` seconds when no tunnel endpoint is in the log, and sweeps the known iOS 27 port bands (`TUNNEL_BANDS`) to force `remotepairingd` to emit a tunnel-endpoint event. This breaks the self-lock where the port watcher only fires *after* the control channel is already up. Endpoint and busy-port regexes are derived from the actual `LOCAL_IP` rather than a hard-coded value, and `publish()` does not spawn duplicate `dns-sd -P` registrations.

  **A hard-coded `authTag` / `identifier` still expires whenever the phone changes Wi-Fi or `remotepairingd` restarts.** Refresh those values from the phone's live Bonjour TXT record before restarting the bridge; the script itself cannot rotate them.
- `python3 scripts/bridge-auto.py <overlay-ip>` is the resident form of the bridge — the only required input is the phone's overlay address (`PHONE` env or `argv[1]`); `LOCAL_IP` defaults to the IPv4 of the default-route interface. It probes the phone's control port, publishes the Bonjour proxy record, lays the control relay, and runs the same drift-following / prefetch / idle-reap loop as `bridge-dynamic.py` (`PREFETCH` 8, `IDLE_TTL` 600s, `CLEAN_INTERVAL` 60s), restarting `dns-sd` and the `log stream` watcher if either dies. One-time prerequisite it cannot create for you: the phone must already be Xcode-paired with **this** Mac (Trust tapped, passcode entered) — see [references/first-time-setup.md](references/first-time-setup.md).

  By default it *generates* a Bonjour identity (`RP_INSTANCE` UUID + random `authTag`). In testing a paired phone authenticated through a stale fabricated `authTag`, so the TXT may not be cryptographically bound for a paired peer; **if authentication fails with generated values, read `identifier` / `authTag` from the phone's live Bonjour TXT and set `RP_INSTANCE` / `RP_AUTHTAG`** — reusing the phone's real `identifier` also keeps Xcode from seeing it as a new device.

  Verified on this Mac (tested): `py_compile`; isolated run against a phone reachable over an IPv6 overlay — control-port probe OPEN, TCP+UDP relay bound and listening, Bonjour record `Name now registered and active`, and on SIGTERM a clean exit that leaves **no** orphaned `socat` / `dns-sd` / `log stream` children. The endpoint regex correctly parses the real `remotepairingd` line `Got tunnel endpoint: '<LOCAL_IP>%en1:<port>'` (zone suffix tolerated). socat's listener address family must follow the **local** bind, not the remote address (`TCP6-LISTEN` rejects an IPv4 `bind=` and exits immediately — this is why the family is derived from `LOCAL_IP`).

  Not tested this session: an end-to-end `devicectl` install *through* `bridge-auto.py`. This Mac already runs a launchd-managed resident bridge (`com.iris.remote-ios-bridge`) that owns `<LAN-IP>:49152` and auto-restarts when killed, so a live takeover needs that service suspended first. socat forks one child per accepted connection — child count tracks live connections (observed ~70 under active Xcode use), while the listener count is what the idle-reap keeps in the tens.
- `python3 scripts/build_deploy.py --help` describes explicit project/workspace, scheme, bundle ID and UDID inputs. The helper builds first, selects the matching device app from Xcode build settings, verifies signing, installs, launches, and checks its PID. It does not start a bridge or fix signing by changing accounts.
- A Wi-Fi switch may invalidate the control channel. Re-probe, wait for authentication to recover, and retry installation once. If the same stage fails again, diagnose that layer instead of repeatedly restarting daemons or clearing pairing.
- On an occupied local port, stop and resolve ownership. On missing pairing, signing, device unlock, or a necessary network change, request the specific user action. Do not disable SIP, erase trust, scan unrelated hosts, or make public firewall mappings.
- A new helper version must pass `python3 -m unittest discover -s tests -v`. These are local tests; they do not certify a new phone/OS/VPN combination. Do not redeploy to live devices merely to test skill packaging.

## Report precisely

State the network condition, chosen deployment Mac, installed artifact, path evidence, startup checks, and remaining uncertainty. See [references/validation.md](references/validation.md) for the anonymized evidence matrix and its limits. Explicitly distinguish “tested”, “inferred”, and “not tested”.
