# Samsung Find Python SDK

The `samsung_find` package provides a typed, synchronous Python SDK for interacting with Samsung SmartThings Find devices, location lookups, and device management.

## Installation

```bash
pip install samsung-find
```

## Basic Usage

```python
from samsung_find import FindConfig, SamsungFindClient
from samsung_find.exceptions import AuthError, DeviceNotFoundError

# Initialize client using default credentials and UTC timezone
config = FindConfig(timezone="UTC")

with SamsungFindClient.from_config(config) as client:
    # 1. List registered devices
    devices = client.devices()
    for dev in devices:
        print(f"Device: {dev['name']} ({dev.get('model', 'Unknown')})")

    # 2. Get device location (passive/cached or active refresh)
    location = client.locate("Galaxy S24", active=False)
    print(f"Coordinates: {location['latitude']}, {location['longitude']}")
    print(f"Accuracy: {location.get('accuracy_m')}m, Fresh: {location.get('is_fresh')}")

    # 3. Check connectivity & battery
    status = client.check_connection("SmartTag2")
    print(f"Battery: {status.get('battery')}%")
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
