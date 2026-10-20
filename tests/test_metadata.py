"""HACS layout, translation coverage, and package hygiene."""

import json
import re
from pathlib import Path

from custom_components.bark_alerts.const import DEFAULTS, OUTCOMES

ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "custom_components" / "bark_alerts"


def test_metadata_and_translations():
    manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
    assert manifest["domain"] == "bark_alerts" and manifest["config_flow"] is True
    assert manifest["requirements"] == [] and manifest["version"] == "0.1.0"
    assert hacs["homeassistant"] == "2026.10.2"
    strings = json.loads((PACKAGE / "strings.json").read_text(encoding="utf-8"))
    assert strings == json.loads(
        (PACKAGE / "translations/en.json").read_text(encoding="utf-8")
    )
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
