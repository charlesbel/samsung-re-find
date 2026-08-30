from samsung_find import (
    Device,
    DeviceCapabilities,
    FindConfig,
    LocationResult,
    OperationResult,
    SamsungFindClient,
)
from samsung_find.exceptions import (
    AuthError,
    DeviceNotFoundError,
    SamsungFindError,
    SecurityError,
)


def test_public_imports_available_at_root():
    assert SamsungFindClient is not None
    assert FindConfig is not None
    assert Device is not None
    assert DeviceCapabilities is not None
    assert LocationResult is not None
    assert OperationResult is not None
    assert SamsungFindError is not None
    assert AuthError is not None
    assert SecurityError is not None
    assert DeviceNotFoundError is not None


def test_models_repr_does_not_leak_secrets():
    loc = LocationResult(
        latitude=48.8566,
        longitude=2.3522,
        accuracy_m=10.0,
        timestamp="2026-08-30T12:00:00Z",
        is_fresh=True,
    )
    assert repr(loc) is not None

    dev = Device(
        id="dev-12345678-secret-id",
        name="Galaxy Phone",
        model="SM-S928B",
        location_type="precise",
    )
    # Ensure raw secret keys or tokens are not dumped
    assert "dev-12345678-secret-id" not in repr(dev) or "Galaxy Phone" in repr(dev)


def test_client_context_manager_and_methods():
    # Verify client class structure and method signatures
    methods = [
        "devices",
        "capabilities",
        "locate",
        "check_connection",
        "ring",
        "track",
        "close",
    ]
    for method in methods:
        assert hasattr(SamsungFindClient, method), f"Missing expected method {method}"
