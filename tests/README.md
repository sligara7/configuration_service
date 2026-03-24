# Configuration Service Tests

## Overview

Comprehensive test suite for the Configuration Service (SVC-004), which provides device/PV registry functionality.

## Test Categories

### Unit Tests (Fast)
- `test_config_models.py` - Domain model tests (DeviceRegistry, DeviceMetadata)
- `test_config_api.py` - API endpoint tests with mock data

### Integration Tests (Comprehensive)
- `test_integration_sim.py` - Full integration tests using sim-profile-collection

## Test Fixtures

Tests are configured in `conftest.py` with the following fixtures:

| Fixture | Description | Profile | Has PVs |
|---------|-------------|---------|---------|
| `mock_client` | Fast testing with mock data | N/A | No |
| `sim_client` | Integration with ophyd.sim devices | sim-profile-collection | No |
| `caproto_client` | Integration with Caproto IOC devices | caproto-profile-collection | Yes |

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run only unit tests (fast)
pytest tests/test_config_models.py tests/test_config_api.py -v

# Run integration tests
pytest tests/test_integration_sim.py -v

# Run with coverage
pytest tests/ --cov=configuration_service --cov-report=term-missing
```

## Test Results Summary

**Total: 70 tests**

| Test File | Tests | Description |
|-----------|-------|-------------|
| test_config_models.py | 13 | Domain model unit tests |
| test_config_api.py | 10 | Mock API endpoint tests |
| test_integration_sim.py | 47 | Comprehensive integration tests |

### Integration Test Coverage

The integration tests (`test_integration_sim.py`) cover all major endpoints:

#### Health Endpoints
- `GET /health` - Service health status
- `GET /ready` - Service readiness

#### Device Endpoints
- `GET /api/v1/devices` - List devices (with filters)
- `GET /api/v1/devices-info` - All device metadata
- `GET /api/v1/devices/classes` - Unique device classes
- `GET /api/v1/devices/types` - Device type categories
- `GET /api/v1/devices/{device_name}` - Device metadata
- `GET /api/v1/devices/{device_name}/components` - Device components
- `GET /api/v1/devices/{device_path}/component` - Nested component

#### PV Endpoints
- `GET /api/v1/pvs` - List PVs (with pattern filter)
- `GET /api/v1/pvs/detailed` - PVs organized by device

## Profile Collections

### sim-profile-collection (Default for CI)
Uses ophyd.sim devices (SynAxis, SynGauss, SynSignal):
- **No PVs** - Pure Python simulation
- **Devices**: motor, motor1-3, det, det1-2, flyer1-2, etc.
- **Plans**: simple_count, motor_scan, grid_scan_2d, etc.

Good for:
- Device/plan introspection testing
- API endpoint validation
- CI/CD pipelines (no EPICS required)

### caproto-profile-collection (PV Testing)
Uses EpicsMotor/EpicsSignal with Caproto IOCs:
- **Has PVs** - Simulated EPICS network
- **Motors**: m1-m4, x, y, z, theta (with motor record PVs)
- **Detectors**: det1-det4 (scalar), cam1 (ADSimDetector-compatible)
- **IOCs**: motor_ioc.py, detector_ioc.py

Good for:
- PV discovery testing
- EPICS integration testing
- Testing services that need real PVs (device_monitoring, direct_control)

## Expected Test Behavior

### ophyd.sim Devices
Devices like SynAxis, SynGauss are classified by class name heuristics — SynAxis matches "axis" → motor, SynGauss matches "gauss" → device (generic fallback). This is expected behavior.

### PV Discovery
sim-profile-collection returns 0 PVs (ophyd.sim devices don't have real PVs).
caproto-profile-collection returns many PVs (EpicsMotor/EpicsSignal have real PV names).

### Plan Schemas
Schemas use `plan_name` key (not `name`) and follow JSON Schema format with `type: object` and `properties`.

## CI Notes

For GitHub Actions CI:
- Use sim-profile-collection (no EPICS infrastructure needed)
- Set `CONFIG_PROFILE_PATH` and `CONFIG_LOAD_STRATEGY=startup_scripts`
- Tests take ~4 minutes for full integration suite
