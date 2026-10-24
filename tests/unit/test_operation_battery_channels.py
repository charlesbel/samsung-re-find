from samsung_find.api import SamsungFindClient as LegacyTransportClient


def test_sanitize_operation_preserves_earbud_battery_channels():
    client = LegacyTransportClient.__new__(LegacyTransportClient)

    operation = client._sanitize_operation(
        {
            "oprnType": "CHECK_CONNECTION",
            "status_code": "2800",
            "result_code": "1200",
            "extra": {
                "left": {"battery": "100"},
                "right": {"battery": "87"},
            },
        }
    )

    assert operation["left_battery_percent"] == 100
    assert operation["right_battery_percent"] == 87
    assert operation["result"] == "success"


def test_sanitize_operation_ignores_missing_or_invalid_battery_channels():
    client = LegacyTransportClient.__new__(LegacyTransportClient)

    operation = client._sanitize_operation(
        {
            "oprnType": "CHECK_CONNECTION",
            "extra": {
                "left": {"battery": "not-a-number"},
                "right": None,
            },
        }
    )

    assert operation["left_battery_percent"] is None
    assert operation["right_battery_percent"] is None
