"""The YAMS scan selection should map cleanly to PLASMA's existing config."""

from yams.controller import _selected_records


def test_selection_preserves_saved_names_and_disables_unselected_devices():
    existing = [
        {"Name": "Left", "Nickname": "wrist", "UUID / MAC Address": "aa:01",
         "Enabled": True, "IMU Stream": True},
        {"Name": "Right", "Nickname": "", "UUID / MAC Address": "AA:02",
         "Enabled": True, "IMU Stream": False},
    ]
    scanned = {
        "AA:01": {"name": "MSense", "address": "AA:01"},
        "AA:03": {"name": "MSense", "address": "AA:03"},
        "AA:04": {"name": "MSense", "address": "AA:04"},
    }

    records = _selected_records(existing, scanned, ["AA:01", "AA:03", "AA:04"])
    by_address = {rec["UUID / MAC Address"]: rec for rec in records}

    assert by_address["AA:01"]["Name"] == "Left"
    assert by_address["AA:01"]["Nickname"] == "wrist"
    assert by_address["AA:01"]["IMU Stream"] is True
    assert by_address["AA:02"]["Enabled"] is False
    assert by_address["AA:03"]["Enabled"] is True
    assert by_address["AA:04"]["Enabled"] is True
    assert by_address["AA:03"]["Name"] == "MSense"
    assert by_address["AA:04"]["Name"] == "MSense"
