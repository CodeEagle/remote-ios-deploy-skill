# Optional signed IPA web distribution

Use only after the user accepts a tap-to-install flow instead of direct CoreDevice deployment. It cannot provide remote debugger access or prove an app started. Do not silently publish an IPA because direct installation failed.

Confirm the host and audience: the iOS installer must fetch the manifest and IPA without an interactive login. A normal private web page login may not be shared with the installer. An IPA contains the provisioning profile, potentially including registered device IDs and signing identities, though not the signing private key. Ask before making this downloadable to a wider audience. Never upload certificates, private keys, entire build trees, or app data.

Use the user's installed Xcode help (`xcodebuild -help`) to confirm export methods. Newer Xcode uses `debugging` for development and `release-testing` for Ad Hoc; older names differ. An existing valid development profile may be sufficient for a development export. Do not claim it is an Ad Hoc distribution certificate. Verify the target UDID, certificate validity, Developer Mode requirements, and profile expiration.

1. Archive a small independent test app or the app the user selected. Preserve its bundle ID and signing team; do not overwrite an unrelated installed app for the test.
2. Export with an explicit ExportOptions plist. Choose automatic signing for an Xcode-managed profile; forcing it into a manual mapping failed in the recorded experiment. Do not automatically grant provisioning changes, register new devices, or create certificates to suppress errors.
3. Unpack the exported IPA, verify its signature and embedded profile, and record its SHA-256. Avoid publishing raw signed artifacts in this skill repository.
4. Serve the IPA over trusted HTTPS and a plist manifest with `items[].assets[]` containing `kind=software-package` and its absolute HTTPS URL. Metadata must match the package's bundle identifier and version, with `kind=software` and the app title.
5. Use an installation link `itms-services://?action=download-manifest&url=<URL-encoded HTTPS manifest URL>`. Serve the manifest as XML and IPA as binary; check status, redirects, and unauthenticated downloads. An HTML login page with HTTP 200 is not a manifest.
6. Compare the downloaded IPA hash with the local export. Ask the user to confirm the system installation prompt, new build marker, sustained startup, and interaction while the intended network condition remains active.

Use a new identifiable build marker when a previous app is already installed; otherwise the existing icon is not evidence of a successful update. Report web delivery and actual installation separately. Offer to remove/restrict temporary hosting after testing; downloaded copies cannot be recalled by unpublishing a URL.

The recorded test only proved export, signing, and HTTPS delivery; **pure-cellular web installation still needs device validation**. Consult [Apple distribution methods](https://help.apple.com/xcode/mac/current/en.lproj/dev31de635e5.html) and [registered-device distribution](https://developer.apple.com/documentation/xcode/distributing-your-app-to-registered-devices), plus the local Xcode CLI for its manifest export contract.
