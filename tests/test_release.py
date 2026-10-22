"""The command, the plugin and the skill must carry one version number.

Claude Code only hands out a new copy of a plugin when its version changes, and
the skill upgrades the command when it's older than the version the skill names.
So all three move together on every release.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from docpdf import __version__

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "claude-plugin"


def test_plugin_version_matches_package():
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["version"] == __version__


def test_skill_names_the_current_version():
    skill = (PLUGIN / "skills" / "docpdf" / "SKILL.md").read_text(encoding="utf-8")
    named = set(re.findall(r"docpdf (\d+\.\d+\.\d+) or newer", skill)) | set(
        re.findall(r"older than (\d+\.\d+\.\d+)", skill)
    )
    assert named == {__version__}, named
