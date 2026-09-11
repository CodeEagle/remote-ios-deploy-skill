# Remote iOS Deploy plugin

A skills-only plugin for local macOS development. It does not include an MCP server, automatic hooks, credentials or signed apps. Publication in a directory does not remove the prerequisites below.

## Use in Claude Code

From a local checkout of the repository, test this package with:

```bash
claude plugin validate ./plugins/remote-ios-deploy
claude --plugin-dir ./plugins/remote-ios-deploy
```

Then invoke `/remote-ios-deploy:remote-ios-deploy` or ask for a matching deployment workflow. Directory submission is separate from approval; do not assume this plugin is already listed in a marketplace.

## Use in Codex

This folder includes `.codex-plugin/plugin.json` and a standard `skills/` tree for plugin packaging. For standalone skill installation, see the [repository README](https://github.com/CodeEagle/remote-ios-deploy-skill). This package needs local Mac execution; uploading it does not enable cloud-only access to Xcode or the phone.

## Prerequisites and limits

- Compatible Xcode on macOS, Python 3, `socat`, and `dns-sd`.
- Correct signing certificate/private key and provisioning profile covering the intended phone.
- Valid pairing between the intended Mac and phone, Developer Mode, and phone-side unlock or confirmation when required.
- A network path to the actual phone developer service. Cross-network Wi-Fi installation was verified. Direct cellular installation failed in the recorded experiment; remote first-time pairing is unvalidated.
- Explicit permission before changing the installation Mac or publishing an IPA through an alternative distribution workflow.

Start with [the skill](skills/remote-ios-deploy/SKILL.md), [first-time setup](skills/remote-ios-deploy/references/first-time-setup.md), and [validation limits](skills/remote-ios-deploy/references/validation.md). Read the [privacy notice](PRIVACY.md) before sharing diagnostics.

The copies under `skills/` are generated from the standalone skill. Maintainers run `python3 scripts/package_plugin.py` from the repository root after editing the canonical skill files. `--check` verifies that the package is synchronized. Run the repository tests before publishing.
