# Configuration Service — API Reference

Condensed endpoint reference for the Configuration Service (SVC-004).
For full request/response schemas, see
[configuration-service-openapi.yaml](configuration-service-openapi.yaml).

## Health & Readiness

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/ready` | Readiness check |

## Devices

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/devices` | List device names. Filter by `device_label`, `pattern` (glob), or `ophyd_class`. |
| POST | `/api/v1/devices` | Create a runtime device (metadata + instantiation spec). Persists to SQLite. |
| GET | `/api/v1/devices-info` | Get full metadata for every device in a single response. |
| GET | `/api/v1/devices/classes` | List unique ophyd device class names (e.g., `EpicsMotor`, `EpicsScaler`). |
| GET | `/api/v1/devices/types` | List device type categories (e.g., `motor`, `detector`, `flyer`). |
| GET | `/api/v1/devices/instantiation` | List all device instantiation specs. Optional `active_only` filter. |
| GET | `/api/v1/devices/history` | List device change history (adds, updates, deletes) for audit. |
| PATCH | `/api/v1/devices/{device_name}/enable` | Enable a device for remote instantiation. Idempotent. |
| PATCH | `/api/v1/devices/{device_name}/disable` | Disable a device (stays in registry but excluded from active listings). Idempotent. |
| GET | `/api/v1/devices/{device_name}` | Get detailed metadata for a single device including PV mappings. |
| PUT | `/api/v1/devices/{device_name}` | Update a device's metadata and/or instantiation spec (partial merge). |
| DELETE | `/api/v1/devices/{device_name}` | Remove a device. Profile devices get a delete marker; runtime devices are hard-deleted. |
| GET | `/api/v1/devices/{device_name}/instantiation` | Get instantiation spec for a single device. |
| GET | `/api/v1/devices/{device_name}/components` | List device components (PV signals). Optional `max_depth` to limit nesting. |
| GET | `/api/v1/devices/{device_path}/component` | Look up a single nested component by dot-separated path. |

## Standalone PVs

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/pvs` | Register a standalone PV (not bound to any ophyd device). 409 if name exists. |
| GET | `/api/v1/pvs/standalone` | List standalone PVs. Optional `labels` query (comma-separated) for filtering. |
| GET | `/api/v1/pvs/labels` | List unique labels across all registered standalone PVs. |
| PUT | `/api/v1/pvs/standalone/{pv_name}` | Update a standalone PV (partial merge). 404 if not found. |
| DELETE | `/api/v1/pvs/standalone/{pv_name}` | Delete a standalone PV. Removes from registry and persistent store. 404 if not found. |

## PVs

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/pvs` | List all PVs (device-bound + standalone). Optional `pattern` (glob) for name matching. |
| GET | `/api/v1/pvs/detailed` | Get PVs organized by device with signal path information. |
| GET | `/api/v1/pvs/{pv_name}` | Get detailed metadata for a specific PV (dtype, units, limits, owning device). Standalone PVs have `device_name: null`. |
