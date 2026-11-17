"""Typed entities are checked against the states Home Assistant recorded for the same devices.

Every entity class says what Home Assistant would show for it (`summary()`:
the state and attributes, under Home Assistant's names). Home Assistant's own
test snapshots hold exactly that for each fixture device, so the two can be
compared for all of them.
"""

import math
from typing import Any

import ha_snapshots
import pytest
from conftest import fixture_names, record
from tuya_device_handlers import TUYA_QUIRKS_REGISTRY

from libtuya import Device
from libtuya import device as device_module
from libtuya.entities import CLASSES, Entity, _tables


def same(ours: Any, theirs: Any) -> bool:
    """Whether a value of ours is what Home Assistant recorded (as text, for states)."""
    if ours is None:
        return theirs in (None, "unknown")
    if isinstance(ours, bool) or isinstance(theirs, bool):
        return ours is theirs
    if isinstance(ours, (int, float)):
        try:
            return math.isclose(ours, float(theirs), rel_tol=1e-3, abs_tol=0.01)
        except (TypeError, ValueError):
            return False
    if isinstance(ours, (list, tuple)):
        return (
            isinstance(theirs, (list, tuple))
            and len(ours) == len(theirs)
            and all(same(a, b) for a, b in zip(ours, theirs, strict=True))
        )
    return str(ours) == str(theirs)


@pytest.mark.parametrize("platform", sorted(CLASSES))
def test_summaries_match_home_assistant(platform, tuya, monkeypatch):
    if CLASSES[platform].summary is Entity.summary:
        pytest.skip("no behaviour of its own yet")
    # The snapshots were recorded without product quirks. Those patch a device
    # when it is set up, and the types of its datapoints when they are looked up.
    monkeypatch.setattr(device_module, "apply_quirks", lambda info: None)
    _tables()  # registers the quirks, so that only this test sees the registry empty
    monkeypatch.setattr(TUYA_QUIRKS_REGISTRY, "_quirks", {})
    recorded = ha_snapshots.states(platform)
    compared, differences = 0, []
    for name in fixture_names():
        for entity in Device(tuya, record(name)).entities:
            theirs = recorded.get((name, entity.key)) if entity.platform == platform else None
            if theirs is None or theirs["state"] == "unavailable":
                continue
            for key, value in entity.summary().items():
                if key != "state" and key not in theirs["attributes"]:
                    continue  # Home Assistant leaves out attributes that do not apply
                expected = theirs["state"] if key == "state" else theirs["attributes"][key]
                compared += 1
                if not same(value, expected):
                    differences.append(f"{name} {entity.id} {key}: {value!r} != {expected!r}")
    assert compared, "nothing was compared"
    assert not differences, f"{len(differences)} differences, e.g.\n" + "\n".join(differences[:15])
