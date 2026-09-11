# Evidence and limits

Anonymized hands-on test, 2026-09-11: macOS with Xcode 27 beta 6; iPhone 15 Pro Max running iOS 27 beta; a VPN/overlay network. Results describe that particular setup, not compatibility certification for every VPN provider. Original device identifiers, team IDs, IPs, TXT secrets, raw logs, crash reports, and signed binaries are deliberately excluded.

| Scenario | Observed result |
|---|---|
| Phone on remote helper's Wi-Fi; deployment Mac on another LAN | Direct bridged installation succeeded; app rebuilt from corrected source started and survived 35 seconds; user confirmed startup |
| Phone switched to pure cellular, overlay reported online | Control port refused; direct installation failed; no test app installed |
| Phone switched to another Wi-Fi | Same bridge configuration authenticated again; first install failed during transition, retry succeeded; user confirmed installation; same launched PID/path remained after 35 seconds |
| Signed IPA web-download route | Export and signature validation succeeded; public HTTPS manifest and byte-identical IPA download verified; phone-side cellular installation NOT verified |
| Different newly configured Mac | Reusable procedure documented, NOT independently device-tested |
| Fresh remote pairing | NOT verified |

No installation command was moved to the nearby helper Mac. Tunnel logs pointed to the deployment Mac's LAN relay; relay logs showed the phone's overlay destination and negotiated ports (including 49927, 49929, 49941).

The first stale app launched and immediately crashed in Auto Layout initialization. The source already had a fix; the installed cached artifact predated it. A fresh build plus sustained process verification resolved this. This is why artifact provenance and runtime checks are separate from transport verification.

The original author's iOS 26 test similarly reports a Wi-Fi association requirement in “Known fragilities”, item 6. That corroborates the observed Wi-Fi/cellular contrast; it does not establish a universal prohibition on all cellular app distribution.

These sanitized helper versions have local automated coverage, not a new live-device certification. Do not present changes in Python supervision, another OS/VPN, a different port range, or another Mac as already proven on hardware. Test each requested scenario and update evidence only after completion.
