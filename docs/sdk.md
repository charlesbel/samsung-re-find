# Samsung Find Python SDK

The `samsung_find` package provides a typed, synchronous Python SDK facade for interacting with Samsung SmartThings Find devices, location lookups, and device management.

## Installation

```bash
pip install samsung-find
```

## Basic Usage

```python
from samsung_find import Device, FindConfig, LocationResult, SamsungFindClient
from samsung_find.exceptions import AuthError, DeviceNotFoundError

# Initialize client using default credentials and UTC timezone
config = FindConfig(timezone="UTC")

with SamsungFindClient.from_config(config) as client:
    # 1. List registered devices (IDs are masked by default)
    devices: list[Device] = client.list_devices()
    for dev in devices:
        print(f"Device: {dev.name} ({dev.model or 'Unknown'})")

    # Opt-in to internal device IDs when necessary
    devices_with_ids: list[Device] = client.list_devices(include_ids=True)

    # 2. Get device location (passive/cached or active refresh)
    location: LocationResult = client.get_last_location("Galaxy S24")
    if location.latitude is not None and location.longitude is not None:
        print(f"Coordinates: {location.latitude}, {location.longitude}")
        print(f"Accuracy: {location.accuracy_m}m, Fresh: {location.is_fresh}")

    # Request fresh active GPS fix from device
    fresh_loc: LocationResult = client.request_location("Galaxy S24", poll_seconds=180)

    # 3. Check connectivity & battery
    status = client.check_connection("SmartTag2")
    print(f"Reachable: {status.success}, Battery: {status.battery}%")

    # 4. Ring device or toggle tracking (active commands)
    ring_result = client.ring("SmartTag2", status="start")
    track_result = client.set_tracking("Galaxy S24", enabled=True)
```

## Legacy / Low-Level Transport

For legacy scripts that require direct dictionary responses from the raw SmartThings transport:

```python
from samsung_find.api import SamsungFindClient as TransportClient

raw_client = TransportClient.from_config(config)
raw_devices = raw_client.devices()
```

## Authentication Management

The SDK integrates directly with the shared Samsung Account master state (`master-state-v1` contract):

```python
from samsung_find import MasterStateStore

store = MasterStateStore()
if store.exists():
    master = store.load()
    print("Master state present and loaded.")
```

## Exception Hierarchy

All exceptions inherit from `SamsungFindError`:

- `SamsungFindError`
  - `AuthError` (re-authentication required, invalid tokens)
  - `SecurityError` (untrusted redirect/host, permission violation, symlinks)
  - `NetworkError` (network timeouts, remote server errors)
  - `StorageError` (corrupt local files, locking issues)
  - `DeviceNotFoundError` (device name/ID not matched)
  - `RateLimitError` (excessive polling or server backoff)
  - `OperationError` (device operation failed)
