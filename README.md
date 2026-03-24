# Configuration Service (SVC-004)

[![Configuration Service CI](https://github.com/NSLS2/bluesky-remote-architecture/actions/workflows/configuration-service.yml/badge.svg)](https://github.com/NSLS2/bluesky-remote-architecture/actions/workflows/configuration-service.yml)

Device/PV registry for Bluesky Remote Architecture.

## Features

- **Device Registry**: Query available devices and their metadata (ophyd classes, PV mappings, labels)
- **PV Registry**: Query EPICS PVs with metadata (type, units, limits)
- **Nested Device Lookup**: Navigate device component hierarchies (ophyd-websocket compatible)
- **Multiple Profile Formats**: Supports IPython-style, Happi (LCLS/SLAC), and BITS (BCDA-APS) profiles
- **Auto-Detection**: Automatically detects profile format based on files present
- **Device Labels**: Filter devices by labels (e.g., "motors", "detectors", "baseline")
- **Device CRUD**: Runtime device management with persistent change history
- **Device Instantiation Specs**: Provides complete device constructor info for remote instantiation

## Profile Formats

The service supports three profile collection formats with **automatic detection**:

| Format | Detection Marker | Origin | Status |
|--------|------------------|--------|--------|
| **startup_scripts** | `startup/*.py` or `*.py` files | Traditional IPython/Bluesky | **Deprecated** (legacy support) |
| **happi** | `happi_db.json` | LCLS/SLAC | **Recommended** |
| **bits** | `configs/devices.yml` | BCDA-APS | Supported |

Just point to a profile directory and the service figures out the format:

```bash
# Auto-detects format based on files present
CONFIG_PROFILE_PATH=/path/to/any-profile bluesky-configuration-service
```

### IPython-Style Profiles (startup_scripts)

> **Deprecation Notice**: IPython-style profile collections are maintained for backwards compatibility but are **deprecated**. New beamlines should use **happi** or **BITS** format instead. Existing beamlines are encouraged to migrate when feasible. See [Configuration Loading Strategy](../../docs/architecture/configuration-loading-strategy.md) for migration guidance.

Traditional Bluesky profile collections with Python startup scripts.
Follows the **bluesky-queueserver pattern**: execute scripts → introspect namespace → discover devices/plans.

```
profile_collection/
├── startup/
│   ├── 00-base.py           # Base imports, RunEngine setup
│   ├── 01-devices.py        # Device definitions (ophyd)
│   └── 02-plans.py          # Plan definitions
```

> **Note**: `existing_plans_and_devices.yaml` is auto-generated OUTPUT from namespace introspection, not an input file. The service discovers devices and plans by executing the startup scripts and inspecting the resulting namespace.

**Why migrate?** IPython profiles require arbitrary code execution (`exec()`) and complex introspection to extract device configurations. Happi/BITS provide declarative, schema-validated configurations that are safer, easier to maintain, and produce meaningful version control diffs.

### Happi Profiles (LCLS/SLAC)

JSON database format with device class and constructor arguments:

```
happi-profile/
├── happi_db.json          # Device definitions
├── happi.cfg              # Happi configuration
└── plans/
    └── sim_plans.py       # Plan definitions
```

### BITS Profiles (BCDA-APS)

YAML-based configuration with device labels:

```
bits-profile/
├── configs/
│   ├── iconfig.yml        # Instrument configuration
│   └── devices.yml        # Device definitions with labels
└── plans/
    └── sim_plans.py       # Plan definitions
```

## Limitations of Startup Script Loading

The `startup_scripts` loader executes profile collection scripts in a subprocess and introspects the resulting namespace to discover devices. Because this runs **outside of IPython and without live EPICS IOC connections**, not all profile collections will load completely. The service uses `ignore_errors=True` so that individual script failures do not crash the service — it loads as many devices as it can and skips the rest.

### Common Reasons Scripts Fail

| Failure Category | Description | Example |
|------------------|-------------|---------|
| **Site-specific packages** | Scripts import packages that are only available at the facility (e.g., `nslsii`, custom beamline modules). | `import nslsii; nslsii.configure_base(...)` |
| **Live IOC connections** | Scripts attempt to connect to EPICS IOCs during import and block or fail when the IOCs are unreachable. | `EpicsMotor("XF:05IDA-OP{...}", name="...")` timing out |
| **Inter-script coupling** | Early scripts define globals (shared objects, helper functions) that later scripts depend on. If the early script fails, all downstream scripts cascade-fail. | `00-startup.py` sets up a shared namespace; `10-motors.py` references variables from it |
| **IPython features** | Scripts use IPython magics or interactive features beyond what the built-in mock covers. | `%run`, `%load_ext`, custom magics |

### Real-World Test Results

Testing against six NSLS-II beamline profile collections produced the following results when loaded **off-site** (no EPICS infrastructure, no beamline-specific IOCs):

| Profile | Devices Loaded | Notes |
|---------|---------------|-------|
| XPD | ~101 | Self-contained device scripts; loads well off-site |
| SRX | ~50 | Self-contained device scripts; loads well off-site |
| ISS | ~14 | Partial load; some scripts fail due to missing `ttime` and other dependencies |
| TST | ~6 | Test profile; loads fully |
| HEX | 0 | Tightly coupled to `nslsii.configure_base()`; cascade failure when it fails |
| CSX | 0 | Same tight coupling pattern as HEX |

**Key takeaway**: Profiles with self-contained device definition scripts (one device per script, minimal cross-script dependencies) load reliably. Profiles that rely heavily on site-specific initialization or shared globals may load partially or not at all.

### It Is the User's Responsibility to Configure the Environment

The Configuration Service does not install or manage beamline-specific dependencies. If a profile collection requires packages like `nslsii`, `hxntools`, or other facility-specific libraries, those must be installed in the Python environment before the service can load them. The service is designed to work at **any synchrotron facility** — it makes no assumptions about which packages are available.

### Building a Complete Device Registry

The Configuration Service is designed so that an incomplete initial load is not a dead end. There are several paths to a complete registry:

#### 1. Experiment Execution Service Sync (Recommended for First Run)

The Experiment Execution Service (SVC-001) can run with `--load-strategy profile_collection`, which executes startup scripts **with live IOC connections** in the full beamline environment. After loading, it automatically compares its discovered devices against the Configuration Service registry and pushes any missing or updated devices via the CRUD endpoints:

```bash
# First run: learn devices from profile collection and sync to config service
EXEC_LOAD_STRATEGY=profile_collection \
EXEC_PROFILE_COLLECTION_PATH=/opt/bluesky/profile_collection \
EXEC_CONFIG_SERVICE_URL=http://localhost:8004 \
  bluesky-experiment-execution
```

After this initial sync, the Configuration Service has a complete registry. Subsequent runs can use `--load-strategy config_service` to pull devices directly — no profile collection needed.

#### 2. Manual CRUD Entry

Users can add missing devices directly via the REST API:

```bash
curl -X POST http://localhost:8004/api/v1/devices \
  -H "Content-Type: application/json" \
  -d '{
    "metadata": {
      "name": "my_motor",
      "device_label": "motor",
      "ophyd_class": "EpicsMotor",
      "is_movable": true,
      "is_readable": true,
      "pvs": {"user_readback": "BL:MOT.RBV", "user_setpoint": "BL:MOT"}
    },
    "instantiation_spec": {
      "name": "my_motor",
      "device_class": "ophyd.EpicsMotor",
      "args": ["BL:MOT"],
      "kwargs": {"name": "my_motor"}
    }
  }'
```

Devices can also be enabled/disabled without removing them:

```bash
# Disable a device (remains in registry but excluded from active listings)
curl -X PATCH http://localhost:8004/api/v1/devices/my_motor/disable

# Re-enable it later
curl -X PATCH http://localhost:8004/api/v1/devices/my_motor/enable
```

#### 3. Persistence and Export

All devices — whether loaded from a profile, synced from Experiment Execution, or added via CRUD — are persisted in a SQLite database. **Once the registry is populated, the profile collection is no longer needed.** On subsequent restarts, the service loads directly from the database.

The registry can be exported in happi format for use with other tools or as a portable device listing:

```bash
curl http://localhost:8004/api/v1/registry/export?format=happi > devices.json
```

#### 4. Forced Refresh from Profile

If the profile collection has changed (new devices, updated PV prefixes, etc.), a user can force the service to wipe the database and re-seed from the profile:

```bash
curl -X POST http://localhost:8004/api/v1/registry/reset
```

This erases all CRUD changes (adds, updates, deletes) and re-runs the profile loader. Any devices that were manually added or synced from Experiment Execution will need to be re-added.

### Recommended Workflow

```
                     First Run
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
    Config Service    Experiment     Manual
    loads profile     Execution      CRUD
    (partial list)    syncs rest     adds rest
          │              │              │
          └──────┬───────┘──────────────┘
                 ▼
         Complete Registry
         (persisted in SQLite)
                 │
          ┌──────┼──────┐
          ▼      ▼      ▼
       Export  Restart  Experiment
       happi  (loads    Execution
              from DB)  (pulls from
                        config svc)
```

## Deployment

### Installation

```bash
# From the service directory
pip install -e .

# With dev dependencies
pip install -e ".[dev]"
```

### Running the Service

```bash
# Basic startup with auto-detection (requires CONFIG_PROFILE_PATH)
CONFIG_PROFILE_PATH=/opt/bluesky/profile_collection bluesky-configuration-service

# Mock mode for testing (no profile needed)
CONFIG_LOAD_STRATEGY=mock bluesky-configuration-service

# Explicit format specification
CONFIG_PROFILE_PATH=/path/to/happi-profile CONFIG_LOAD_STRATEGY=happi bluesky-configuration-service

# Development mode with auto-reload
bluesky-configuration-service --reload --log-level debug

# Custom port
bluesky-configuration-service --port 8004
```

### Docker

```bash
docker build -t bluesky-configuration-service .
docker run -p 8004:8004 \
  -v /opt/bluesky/profile_collection:/opt/bluesky/profile_collection \
  -e CONFIG_PROFILE_PATH=/opt/bluesky/profile_collection \
  bluesky-configuration-service
```

## Configuration

All settings use the `CONFIG_` environment variable prefix.

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `CONFIG_HOST` | `0.0.0.0` | Bind address |
| `CONFIG_PORT` | `8004` | HTTP port |
| `CONFIG_PROFILE_PATH` | - | Path to profile collection directory |
| `CONFIG_LOAD_STRATEGY` | `auto` | Loading strategy (see below) |
| `CONFIG_LOG_LEVEL` | `INFO` | Log level |

### Load Strategies

| Strategy | Description | Auto-Detected By |
|----------|-------------|------------------|
| `auto` | **Default** - Detect format automatically | N/A |
| `startup_scripts` | Execute Python startup scripts | `startup/*.py` or `*.py` files |
| `happi` | Load from happi JSON database | `happi_db.json` |
| `bits` | Load from BITS YAML configs | `configs/devices.yml` |
| `mock` | Use built-in mock data | N/A (explicit only) |

### Other Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `CONFIG_DB_PATH` | `/var/lib/bluesky/config_service.db` | SQLite database for device change history and standalone PVs |
| `CONFIG_DEVICE_CHANGE_HISTORY_ENABLED` | `true` | Enable runtime device CRUD endpoints |
| `CONFIG_CORS_ORIGINS` | `["*"]` | Allowed CORS origins |
| `CONFIG_METRICS_ENABLED` | `true` | Enable Prometheus metrics |
| `CONFIG_METRICS_PORT` | `9004` | Metrics endpoint port |

## API Endpoints

### Health & Status

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check (includes loaded counts) |
| GET | `/ready` | Readiness check |

### Device Registry

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/devices` | List devices (supports filtering) |
| POST | `/api/v1/devices` | Create a runtime device (persisted to SQLite) |
| GET | `/api/v1/devices-info` | Get full metadata for all devices |
| GET | `/api/v1/devices/classes` | List unique ophyd device class names |
| GET | `/api/v1/devices/types` | List device type categories |
| GET | `/api/v1/devices/instantiation` | List all device instantiation specs |
| GET | `/api/v1/devices/history` | List device change history (audit) |
| PATCH | `/api/v1/devices/{device_name}/enable` | Enable a device for remote instantiation |
| PATCH | `/api/v1/devices/{device_name}/disable` | Disable a device (excluded from active listings) |
| GET | `/api/v1/devices/{device_name}` | Get device metadata |
| PUT | `/api/v1/devices/{device_name}` | Update device metadata/instantiation spec |
| DELETE | `/api/v1/devices/{device_name}` | Remove device from registry |
| GET | `/api/v1/devices/{device_name}/instantiation` | Get device instantiation spec |
| GET | `/api/v1/devices/{device_name}/components` | List device components |
| GET | `/api/v1/devices/{device_path}/component` | Get nested component |
| GET | `/api/v1/labels` | List all device labels |

**Query Parameters for `/api/v1/devices`**:
- `device_label`: Filter by type (motor, detector, signal, etc.)
- `pattern`: Glob pattern matching (e.g., `det*`)
- `labels`: Filter by labels (e.g., `labels=motors&labels=baseline`)

### PV Registry

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/pvs` | List PVs (device-bound + standalone) |
| POST | `/api/v1/pvs` | Register a standalone PV |
| GET | `/api/v1/pvs/standalone` | List standalone PVs (supports label filtering) |
| GET | `/api/v1/pvs/labels` | List unique standalone PV labels |
| PUT | `/api/v1/pvs/standalone/{pv_name}` | Update a standalone PV |
| DELETE | `/api/v1/pvs/standalone/{pv_name}` | Delete a standalone PV |
| GET | `/api/v1/pvs/detailed` | Get PVs organized by device |
| GET | `/api/v1/pvs/{pv_name}` | Get PV metadata |

## Example Usage

### List All Devices

```bash
curl http://localhost:8004/api/v1/devices
```

### Filter Devices by Type

```bash
curl "http://localhost:8004/api/v1/devices?device_label=motor"
```

### Filter Devices by Labels

```bash
# Devices with "baseline" label
curl "http://localhost:8004/api/v1/devices?labels=baseline"

# Devices with both "motors" and "sample_stage" labels
curl "http://localhost:8004/api/v1/devices?labels=motors&labels=sample_stage"
```

### Get Device Metadata

```bash
curl http://localhost:8004/api/v1/devices/motor
```

Response includes labels and extended metadata:
```json
{
  "name": "motor",
  "device_label": "motor",
  "ophyd_class": "SynAxis",
  "module": "ophyd.sim",
  "is_movable": true,
  "is_readable": true,
  "labels": ["motors", "baseline"],
  "beamline": "SIM",
  "functional_group": "motors"
}
```

### List All Labels

```bash
curl http://localhost:8004/api/v1/labels
```

## Service Dependencies

| Dependency | Interface | Purpose |
|------------|-----------|---------|
| None (standalone) | - | Foundation service, reads from local profile collections |

**Services that depend on configuration_service:**
- `experiment_execution` - Queries devices for instantiation specs
- `direct_control` - Queries devices for validation
- `device_monitoring` - Queries PVs for metadata
- `adaptive_interface` - Queries devices for campaign setup

### Runtime CRUD and Experiment Safety

Device CRUD operations (POST, PUT, DELETE) can be performed at any time — the Configuration Service has no awareness of whether an experiment is currently running. It is intentionally a "dumb registry": it accepts changes, updates the in-memory registry, and persists them to the SQLite overlay.

The safety boundary lives on the consumer side. When the Experiment Execution Service is running a plan, it holds device locks that prevent environment reloads. This follows the same pattern as Direct Control, which is locked out of commanding devices during plan execution.

In short: changes are staged immediately in Configuration Service, but consumed between experiments — not during them.

## Mock Data Mode

For testing without a profile collection:

```bash
CONFIG_LOAD_STRATEGY=mock bluesky-configuration-service
```

Mock data includes:
- Motor: `sample_x` (EpicsMotor with instantiation spec)
- Detectors: `det1` (EpicsScaler), `cam1` (SimDetector) — both with instantiation specs
- Example PVs with realistic naming

## Testing

The service has comprehensive test coverage with 150+ tests:

```bash
# Run all tests
cd services/configuration_service
pytest tests/ -v

# Run only unit tests (fast, ~3 seconds)
pytest tests/test_config_models.py tests/test_config_api.py -v

# Run integration tests (~4 minutes, uses sim-profile-collection)
pytest tests/test_integration_sim.py -v

# Run with coverage
pytest tests/ --cov=configuration_service --cov-report=term-missing
```

### Test Categories

| Test File | Description |
|-----------|-------------|
| `test_config_models.py` | Domain model unit tests |
| `test_config_api.py` | Mock API endpoint tests |
| `test_device_crud.py` | Device CRUD endpoint tests (create, update, delete, persistence) |
| `test_standalone_pv_crud.py` | Standalone PV CRUD endpoint tests |
| `test_integration_sim.py` | Integration tests with sim-profile-collection |

### Profile Collections for Testing

| Profile | Location | Use Case |
|---------|----------|----------|
| **sim-profile-collection** | `tests/fixtures/profiles/` | CI testing (ophyd.sim devices, no EPICS) |
| **caproto-profile-collection** | `tests/fixtures/profiles/` | PV discovery testing (EpicsMotor with Caproto IOCs) |

See `tests/README.md` for detailed test documentation.

## Architecture

### Loader Classes

| Loader | Format | Key Files |
|--------|--------|-----------|
| `ProfileCollectionLoader` | startup_scripts | `startup/*.py` |
| `HappiProfileLoader` | happi | `happi_db.json` |
| `BitsProfileLoader` | bits | `configs/devices.yml`, `configs/iconfig.yml` |
| `MockProfileLoader` | mock | (built-in data) |

### Data Models

- `DeviceMetadata`: Device info with labels, PVs, capabilities
- `DeviceRegistry`: In-memory device index with label filtering

### Auto-Detection Flow

```
CONFIG_PROFILE_PATH=/path/to/profile
            │
            ▼
    detect_profile_type()
            │
    ┌───────┼───────┬───────────┐
    ▼       ▼       ▼           ▼
 happi?   bits?  startup?   error
    │       │       │
    ▼       ▼       ▼
 Happi    Bits   Profile
 Loader   Loader Collection
                  Loader
```

### Loader Isolation for Clean Deprecation

Each loader is implemented as an isolated class with a common interface. This ensures that when IPython profile collection support is eventually removed, it will be a simple deletion of one loader class—not untangling of intermingled code.

See [Configuration Loading Strategy](../../docs/architecture/configuration-loading-strategy.md) for:
- Detailed comparison of loading approaches
- Migration guide from profile collections to happi/BITS
- Deprecation timeline and phases
- Code organization for clean removal
