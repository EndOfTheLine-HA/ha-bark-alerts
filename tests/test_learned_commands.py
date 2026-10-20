"""Read-only, transmitter-scoped name discovery using synthetic storage."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from custom_components.bark_alerts.learned_commands import async_learned_commands


def directory_files(path):
    return set(path.iterdir()) if path.exists() else set()


async def test_names_only_sorted_scoped_and_storage_unchanged(
    hass, rig, learned_storage
):
    path = learned_storage(
        {
            "Zebra": {"second": "synthetic packet"},
            "alpha": {
                "Z": ["synthetic toggle A", "synthetic toggle B"],
                "beep": "synthetic packet",
                "empty": "",
                "empty list": [],
                "invalid list": [None],
                "invalid shape": {},
                "b64:not a name": "synthetic packet",
                " trailing ": "synthetic packet",
                "": "synthetic packet",
            },
            "empty": {},
            "not commands": [],
            " unaddressable ": {"beep": "synthetic packet"},
        }
    )
    learned_storage({"Other transmitter": {"other": "synthetic"}}, "000000000002")
    before = path.read_bytes()
    result = await async_learned_commands(hass, rig.device.id)
    assert list(result) == ["alpha", "Zebra"]
    assert result == {"alpha": ["beep", "Z"], "Zebra": ["second"]}
    assert "synthetic" not in repr(result)
    assert path.read_bytes() == before
    assert not rig.sends and not rig.learns


async def test_missing_storage_is_not_created(hass, rig):
    directory = Path(hass.config.path(".storage"))
    before = await hass.async_add_executor_job(directory_files, directory)
    assert await async_learned_commands(hass, rig.device.id) == {}
    assert await hass.async_add_executor_job(directory_files, directory) == before


@pytest.mark.parametrize("content", [b"not JSON", b"[", b"null", b"[]", b"\xff"])
async def test_malformed_storage_is_not_modified(hass, rig, learned_storage, content):
    path = learned_storage({})
    path.write_bytes(content)
    assert await async_learned_commands(hass, rig.device.id) == {}
    assert path.read_bytes() == content


@pytest.mark.parametrize(
    "change",
    [
        {"version": 2},
        {"key": "some_other_store"},
        {"data": []},
        {"data": None},
    ],
)
async def test_unknown_format_falls_back_without_migration(
    hass, rig, learned_storage, change
):
    path = learned_storage({"Example": {"beep": "synthetic"}})
    document = json.loads(path.read_bytes())
    document.update(change)
    path.write_text(json.dumps(document), encoding="utf-8")
    before = path.read_bytes()
    assert await async_learned_commands(hass, rig.device.id) == {}
    assert path.read_bytes() == before


async def test_unreadable_storage_does_not_expose_exception(hass, rig, learned_storage):
    learned_storage({"Example": {"beep": "synthetic"}})
    with patch.object(Path, "open", side_effect=PermissionError("private details")):
        assert await async_learned_commands(hass, rig.device.id) == {}


async def test_oversized_store_falls_back_without_modification(
    hass, rig, learned_storage
):
    path = learned_storage({"Example": {"beep": "synthetic"}})
    before = path.read_bytes()
    with patch("custom_components.bark_alerts.learned_commands.MAX_STORAGE_BYTES", 10):
        assert await async_learned_commands(hass, rig.device.id) == {}
    assert path.read_bytes() == before


@pytest.mark.parametrize("unique_id", ["../other", "ABCDEFABCDEF", "", "not-a-mac"])
async def test_invalid_remote_identifier_cannot_select_a_path(hass, rig, unique_id):
    rig.registry.async_update_entity(rig.remote.entity_id, new_unique_id=unique_id)
    with patch(
        "custom_components.bark_alerts.learned_commands._read_names",
        side_effect=AssertionError("Must not read an unvalidated path"),
    ):
        assert await async_learned_commands(hass, rig.device.id) == {}


async def test_catalog_refreshes_after_newly_learned_names(hass, rig, learned_storage):
    learned_storage({"Example": {"beep": "synthetic"}})
    assert await async_learned_commands(hass, rig.device.id) == {"Example": ["beep"]}
    learned_storage({"Example": {"new beep": "synthetic"}})
    assert await async_learned_commands(hass, rig.device.id) == {
        "Example": ["new beep"]
    }
