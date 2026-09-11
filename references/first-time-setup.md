# First-time setup and minimum human actions

Use this guide when the phone has never connected to the intended deployment Mac, has only trusted another Mac, or its pairing status is unknown. Distinguish prerequisites from recommended acceptance tests. Installing this skill configures neither trust nor signing.

## Decide whether bootstrap is needed

Check `xcrun devicectl list devices --timeout 20` on the **intended deployment Mac**, matching the actual phone UDID. A discovered name, an overlay-online indicator, or another Mac's paired status is not proof that this Mac is trusted. An absent device can also mean discovery or connectivity failure; absence alone does not prove pairing was lost.

- If this Mac already has valid pairing and can authenticate to the phone, retain it. No new cable session is required merely to install this skill.
- If the phone only trusted another Mac, prepare this Mac separately. Sharing an Apple ID, signing team, Bonjour TXT data or bridge configuration does not grant pairing trust.
- If no valid pairing exists and the phone is already remote, state that first pairing through this bridge is **not validated**. `devicectl manage pair` attempts pairing with a discovered device; its existence does not prove unattended pairing over a VPN works.

Do not export pairing databases, copy entire Keychains, reset trust, or enable broad network access as an automatic repair.

## One-time preparation

| Who | Required preparation | Completion evidence |
|---|---|---|
| Mac operator / agent | Compatible macOS and Xcode, selected Xcode developer directory, Python 3, `socat`, macOS `dns-sd` | Tools available; Xcode supports the phone OS and can prepare its developer support |
| Signing owner / Mac operator | Project access and correct team; usable certificate with private key and provisioning profile including the phone UDID | Device build signs successfully with the intended identity; profile is valid |
| Phone holder + Mac operator | Initial supported Xcode pairing with the intended Mac | Correct device is paired and authentication succeeds |
| Phone holder | Developer Mode enabled for Xcode development deployment; unlock when requested | Xcode no longer reports a Developer Mode / device-lock preparation blocker |
| Network operator / phone holder | A configured overlay on both endpoints allowing the required system TCP/UDP path; phone on Wi-Fi for the tested direct path | Mac reaches the verified phone developer endpoint, not merely its management address |
| Agent / Mac operator | Actual Bonjour instance, hostname and TXT values; phone address and deployment Mac LAN IPv4 | Private bridge configuration matches the intended device; local listeners are available |

New account sign-in, device registration, certificate creation and VPN enrollment may require their owner's action or approval. An agent can perform authorized setup, but must not silently switch teams or publish credentials. Do not store private configuration in this repository.

### Minimum phone-holder checklist

1. Have the phone and the intended deployment Mac together for the supported bootstrap, with a working **data** cable. Unlock the phone and connect it.
2. Open Xcode's device management UI (Device Hub or Devices and Simulators, depending on version). Select the intended phone and complete pairing; accept Trust and enter the phone passcode if prompted. Enable network connection if that Xcode version offers the option. Follow [Apple's iOS pairing procedure](https://help.apple.com/xcode/mac/current/en.lproj/devbc48d1bad.html); do not apply its separate Apple TV wireless PIN procedure to an iPhone.
3. For development deployment, enable Developer Mode if it is off, restart, then confirm and enter the passcode on the phone. If the setting is missing, initiate pairing first. These are phone-side actions, not something this bridge can bypass. See [Apple's Developer Mode instructions](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device).
4. Keep the phone unlocked as Xcode completes preparation. Configure/authorize its overlay client and connect Wi-Fi. Leave it available for any installation or launch prompt.

Already-completed steps need not be repeated. This is a supported bootstrap recipe, not a claim that every possible iOS pairing mechanism necessarily requires USB. Fully remote first pairing remains an open validation item for this repository.

### Recommended acceptance before separation

These checks reduce later troubleshooting; they are not additional phone trust permissions:

1. Build and run a small app using the chosen Mac and signing team. Confirm the expected UI opens.
2. Capture the device's real discovery information while locally reachable. Follow [Direct deployment: discovery](direct.md#discover-the-real-phone-identity); do not fabricate missing TXT values.
3. Disconnect the data cable and verify a wireless install/run on the same Wi-Fi. This separates pairing/signing problems from cross-network bridge problems.
4. Move the phone to a different Wi-Fi, start the configured bridge on the chosen Mac, and verify installation, relay/tunnel evidence, process survival and UI. No installation helper Mac near the phone should be used when validating this direct route.

Report which checks actually passed. Neither “paired” nor a successful local run alone certifies cross-network deployment.

## Phone is already remote and has never paired

Do not promise zero-touch direct bootstrap. Offer these alternatives with their changed requirements:

| Option | Phone-holder action | Important boundary |
|---|---|---|
| Arrange one-time access to the intended Mac | Complete the checklist above | Preserves the requested deployment endpoint; subsequent verified use can be remote |
| Explicitly choose another Mac as installer | Pair with that Mac if needed; assist with setup | Changes the deployment architecture. An existing trusted Mac can install, but does not confer trust on the original Mac |
| Appropriate Ad Hoc / registered-device distribution | Supply UDID through an agreed method and accept installation prompts | Requires suitable developer membership, registered device and matching distribution signing. No Xcode pairing with the build Mac is required on the installing phone; this repository has not validated that end-to-end route |
| TestFlight | Join the authorized test and install using TestFlight | Separate App Store Connect upload, processing and distribution workflow; not an automatic fallback or a capability of these scripts |

A development-signed IPA link is **not** a guaranteed bootstrap escape hatch: Developer Mode still applies, and Apple says its setting appears after pairing is initiated or was previously completed. Distinguish development signing from Ad Hoc signing. See [Web distribution](web-distribution.md) before offering a hosted artifact; confirm audience and publication permission. Export and HTTPS download success do not establish phone-side installation success.

For distribution eligibility and signing, consult [Apple's distribution methods](https://help.apple.com/xcode/mac/current/en.lproj/dev31de635e5.html) and [registered-device distribution](https://developer.apple.com/documentation/xcode/distributing-your-app-to-registered-devices).

## Minimum routine operation after bootstrap

The Mac needs its valid pairing, signing environment, current discovery/configuration values and active bridge. The phone needs the tested Wi-Fi + reachable overlay developer service, Developer Mode and any requested unlock/confirmation. The phone need not remain near this Mac or a helper Mac.

Do not require a new cable connection for every network switch. Recheck addresses, service reachability and discovery values first. Trust resets, expired signing, OS changes or rotated discovery data can require intervention; this workflow is not guaranteed unattended. Pure-cellular direct installation failed in the recorded experiment even with the overlay online. Web installation on cellular remains unverified.
