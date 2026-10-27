"""HACS layout, translation coverage, and package hygiene."""

import json
import re
import struct
import tomllib
from pathlib import Path

import pytest

from custom_components.bark_alerts.const import DEFAULTS, OUTCOMES, VERSION

ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "custom_components" / "bark_alerts"


def test_metadata_and_translations():
    manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
    assert manifest["domain"] == "bark_alerts" and manifest["config_flow"] is True
    assert manifest["requirements"] == [] and manifest["version"] == VERSION == "0.2.4"
    assert manifest["integration_type"] == "service"
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["version"] == VERSION
    assert hacs["homeassistant"] == "2026.10.2"
    strings = json.loads((PACKAGE / "strings.json").read_text(encoding="utf-8"))
    assert strings == json.loads(
        (PACKAGE / "translations/en.json").read_text(encoding="utf-8")
    )
    assert "\u00e2\u20ac" not in str(strings)
    assert set(strings["entity"]["sensor"]["outcome"]["state"]) == set(OUTCOMES)
    assert set(strings["config"]["step"]["behavior"]["data"]) == set(DEFAULTS)
    assert (
        len(
            [
                path
                for path in (ROOT / "custom_components").iterdir()
                if path.is_dir() and not path.name.startswith("_")
            ]
        )
        == 1
    )


def test_no_embedded_network_addresses_or_real_rf_payloads():
    for path in PACKAGE.rglob("*"):
        if path.suffix not in (".py", ".json"):
            continue
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\b192\.168\.\d+\.\d+\b", text)
        assert not re.search(r"b64:[A-Za-z0-9+/]{32,}", text)
    assert not (PACKAGE / "services.yaml").exists()


def test_integration_does_not_access_broadlink_private_storage():
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in PACKAGE.rglob("*.py")
    )
    assert "broadlink_remote_" not in source
    assert not (PACKAGE / "learned_commands.py").exists()


@pytest.mark.parametrize("filename,size", [("icon.png", 256), ("icon@2x.png", 512)])
def test_local_brand_assets(filename, size):
    # Home Assistant reads only these two PNGs; the icon has no SVG source since
    # the camera and RF collar artwork replaced it.
    content = (PACKAGE / "brand" / filename).read_bytes()
    assert content[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", content[16:24]) == (size, size)


def test_no_frigate_private_client_or_config_access():
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in PACKAGE.rglob("*.py")
    )
    assert 'hass.data.get("frigate"' not in source
    assert 'hass.data["frigate"' not in source
    assert "get_auth_headers" not in source
    assert "from custom_components.frigate" not in source
    assert "config_entries.async_get_entry(camera.config_entry_id)" not in source
