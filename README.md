# Remote iOS Deploy Skill

English | [简体中文](README.zh-CN.md)

Deploy iOS apps from a Mac to a remote iPhone using local Bonjour proxy discovery and a TCP/UDP bridge, with fresh builds, signature checks, and sustained startup verification. For Codex and other coding agents that support `SKILL.md`.

## What has been verified

- Installation from a remote Mac succeeded with the phone on two different Wi-Fi networks over a VPN/overlay. Installation commands were not moved to a Mac near the phone.
- With the phone on cellular only and its VPN/overlay client reporting online, the developer-service endpoint refused connections. **Direct cellular deployment did not pass.**
- Switching back to a different Wi-Fi network restored connectivity with the same bridge configuration; installation succeeded on retry. Seamless roaming is not guaranteed.
- The IPA web-installation route was validated through export, signing, and HTTPS download only. Phone-side installation over cellular remains unverified.
- Each deployment Mac needs its own pairing trust and signing environment. Copying a configuration or another Mac's pairing records is not sufficient.

No personal device addresses, UDIDs, signing private keys, raw logs, or signed app packages are included. Hardware observations and local tests of these reusable helpers are recorded separately in [Evidence and limits](references/validation.md).

This skill is not tied to a particular VPN product. The network must let the Mac reach the phone's developer services through system TCP/UDP sockets. Provider-neutral configuration does not imply that every VPN, OS version, or network condition has been tested.

## Minimum setup for a new phone or Mac

The prerequisite is **valid pairing trust between this Mac and this phone**, not simply a past USB connection. For the supported first-time workflow:

1. **Mac operator, once per deployment Mac:** install compatible Xcode, Python 3 and `socat`; configure the project's signing team, certificate/private key and a profile covering the phone's UDID. Install and configure an overlay that provides the required TCP/UDP path.
2. **Phone holder, once per Mac–phone pairing:** connect the unlocked phone to that Mac with a data cable, accept Trust and enter the passcode when prompted; complete pairing in Xcode. Enable Developer Mode if needed, restart, and confirm on the phone. If the setting is absent, initiate pairing first. See [Apple's pairing workflow](https://help.apple.com/xcode/mac/current/en.lproj/devbc48d1bad.html) and [Developer Mode](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device).
3. **Agent/Mac operator:** capture the actual Bonjour identity and service address, configure the bridge, and verify signing. Before the phone leaves, recommend a successful run with the cable unplugged on local Wi-Fi, followed by a different-network test; these are acceptance tests, not additional trust prompts.
4. **For later deployments:** keep the phone on Wi-Fi with its developer service reachable through the overlay; unlock/respond to prompts when requested. The verified bridge workflow does not require an installation Mac near the phone. Pairing or discovery data may need repair after resets or changes; this is not a zero-touch guarantee.

| Existing state | Minimum next action |
|---|---|
| This Mac already has valid pairing | Reuse it; check signing, discovery data and network reachability. No repeat USB setup solely for this skill. |
| Phone has only paired with another Mac | Pair the intended Mac once. The same Apple ID or a copied configuration does not transfer trust. |
| Phone is already remote and has never paired with this Mac | No validated remote-first-pairing path is provided. Arrange the initial pairing, or explicitly choose another installer Mac / a suitable distribution flow. |
| Phone is cellular-only | Direct installation failed in the recorded test. Web distribution requires separate consent and device validation. |

Details and alternatives: [First-time setup](references/first-time-setup.md). Do not assume development-signed web installation avoids Developer Mode setup on a never-paired phone.

## Install and use

If the destination does not already exist:

```bash
git clone https://github.com/CodeEagle/remote-ios-deploy-skill.git ~/.codex/skills/remote-ios-deploy
```

If it already exists, inspect it first and preserve existing changes. Reload your agent's skills, then ask:

> Use $remote-ios-deploy to deploy the current project from this Mac to my remote iPhone, and verify the bridge path and startup.

Start with [SKILL.md](SKILL.md). Detailed procedures: [Direct cross-network deployment](references/direct.md) and [Optional web distribution](references/web-distribution.md).

The scripts require Python 3. Bridging also requires macOS `dns-sd` and `socat`; installation requires compatible Xcode and valid signing assets.

```bash
python3 scripts/bridge.py --help
python3 scripts/build_deploy.py --help
python3 -m unittest discover -s tests -v
```

The default port coverage starts approximately 1006 socat processes, prioritizing validation over resource efficiency. Configure port ranges, addresses, and Bonjour values from actual device observations. The scripts do not automatically configure a VPN, pairing, certificates, firewall rules, or startup services. Expose listeners only on trusted networks, and stop the bridge when testing is complete.

## Credits

The protocol-bridging approach was informed by [Kevin Paterson's original experiment](https://dev.to/kvnpt/how-to-remotely-iterate-deploy-your-sideloaded-ios-apps-over-tailnet-jak), with limitations refined through the documented iOS 27 cross-network tests. This repository does not copy that article's script; it provides independently implemented process supervision and deployment-verification helpers.
