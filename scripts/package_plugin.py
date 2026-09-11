#!/usr/bin/env python3
"""Synchronize an explicit allowlist into the distributable plugin package."""
from pathlib import Path
import argparse
import shutil

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "remote-ios-deploy"
SKILL_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "assets/bridge.env.example",
    "references/direct.md",
    "references/first-time-setup.md",
    "references/validation.md",
    "references/web-distribution.md",
    "scripts/bridge.py",
    "scripts/build_deploy.py",
)


def synchronize(check=False):
    pairs = [(ROOT / name, PLUGIN / "skills" / "remote-ios-deploy" / name)
             for name in SKILL_FILES]
    pairs.append((ROOT / "PRIVACY.md", PLUGIN / "PRIVACY.md"))
    mismatches = []
    for source, destination in pairs:
        # Do not follow a replaced parent directory outside the package.
        if not destination.resolve().is_relative_to(PLUGIN.resolve()):
            raise ValueError(f"Destination escapes package: {destination}")
        if destination.is_symlink() or source.is_symlink():
            raise ValueError("Package sources and destinations must not be symlinks")
        if destination.is_file() and destination.read_bytes() == source.read_bytes():
            continue
        mismatches.append(str(destination.relative_to(ROOT)))
        if not check:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    return mismatches


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify without writing")
    args = parser.parse_args()
    changed = synchronize(args.check)
    if args.check and changed:
        parser.exit(1, "Package out of sync:\n" + "\n".join(changed) + "\n")
    print("Package synchronized" if not args.check else "Package is in sync")
