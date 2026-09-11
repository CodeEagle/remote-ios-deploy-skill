# Privacy notice

Effective date: 2026-09-11. Publisher: [CodeEagle](https://github.com/CodeEagle).

Remote iOS Deploy is a local skill and plugin, not a hosted deployment service. Its bundled helpers have no publisher-operated telemetry or analytics endpoint. They run commands on the deployment Mac and connect to the phone address explicitly configured by the operator.

## Information processed locally

The workflow uses project paths and source code, app identifiers, device identifiers and network addresses, Bonjour discovery data, and signing configuration. Xcode and Apple's signing tools access the signing assets required for the selected project. The bridge publishes the configured discovery records on the selected local interface and forwards developer-service traffic to the configured phone. Use only trusted networks and devices you are authorized to access.

Build/deployment evidence and optional bridge logs are written locally. They can contain paths, device information, process details, build settings and signing metadata. Generated app packages and provisioning profiles may also identify registered devices. Keep these files private and retain or delete them according to your own requirements; the helpers do not automatically anonymize or upload them to the publisher.

## Agent and third-party services

When you use the skill through an AI agent, files and tool outputs the agent reads may be processed by that agent provider according to your account settings and its policies. Xcode/Apple services, your chosen VPN or overlay provider, GitHub, and any separately selected artifact host have their own data practices. This notice does not replace those policies.

Web distribution is an optional, separately authorized workflow. A hosted signed IPA can reveal app and device metadata to people who can download it. Do not publish signing private keys, pairing records, credentials, private logs or user data. Unpublishing a URL does not recall downloaded copies.

## Support and reports

The publisher receives information you choose to submit through [GitHub issues](https://github.com/CodeEagle/remote-ios-deploy-skill/issues) or other agreed communication. GitHub issues are public: submit only redacted, non-sensitive descriptions. For security concerns, request a private reporting channel before sharing exploit details or sensitive diagnostics. Do not post private keys, device identifiers or network secrets. See [GitHub's privacy statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement) for information submitted to GitHub.
