"""
Real-world beamline profile collection tests.

Validates that the Configuration Service can load device registries from
actual NSLS-II beamline profile collections using script execution (the
only loading strategy for startup_scripts format — no YAML fallback).

All profiles use ScriptExecutionLoader which:
  1. Exec's startup scripts in a subprocess with ignore_errors=True
  2. Introspects live device objects using bluesky.protocols
  3. Populates a DeviceRegistry with DeviceMetadata + InstantiationSpec

Profiles with self-contained device scripts (XPD, SRX, ISS) load many
devices even off-site.  Profiles with tightly coupled scripts (HEX, CSX)
load fewer devices because infrastructure dependencies (Redis, Kafka,
EPICS IOCs) cause cascading failures in their startup chain.

Note: These tests require the profile collection repos cloned locally
and the nslsii package installed (pip install nslsii).  They will be
skipped automatically if the profile paths don't exist.

Beamline summary (off-site, nslsii installed):
  - TST:   6 devices  — ophyd-async (HDFPanda, Motor, VimbaDetector)
  - XPD: 101 devices  — 18 classes, self-contained device scripts
  - ISS:  14 devices  — custom device classes (Electrometer, EncoderFS)
  - SRX:  50 devices  — 34 classes, largest successful profile
  - HEX:   0 devices  — ophyd-async, cascading file_loading_timer failure
  - CSX:   0 devices  — PV connection timeouts on device instantiation

Each test verifies:
  1. Service starts healthy
  2. Device count meets minimum expectations
  3. All loaded devices have valid metadata
  4. Device types are from the canonical DeviceLabel enum
  5. Cross-endpoint consistency (device list matches devices-info)
"""

import pytest
from fastapi.testclient import TestClient

from configuration_service.models import DeviceLabel

VALID_DEVICE_TYPES = {dt.value for dt in DeviceLabel}


# =============================================================================
# Helpers
# =============================================================================

def _assert_service_healthy(client: TestClient, min_devices: int):
    """Verify the service started and loaded at least min_devices."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["devices_loaded"] >= min_devices, (
        f"Expected >= {min_devices} devices, got {data['devices_loaded']}"
    )
    return data["devices_loaded"]


def _assert_devices_have_valid_metadata(client: TestClient):
    """Verify every listed device has valid metadata with a canonical device type."""
    response = client.get("/api/v1/devices-info")
    assert response.status_code == 200
    devices_info = response.json()

    for name, device in devices_info.items():
        assert "device_label" in device, f"Device '{name}' missing device_label"
        assert device["device_label"] in VALID_DEVICE_TYPES, (
            f"Device '{name}' has invalid device_label: {device['device_label']}"
        )
        assert "ophyd_class" in device, f"Device '{name}' missing ophyd_class"
        assert device["ophyd_class"], f"Device '{name}' has empty ophyd_class"

    return devices_info


def _assert_cross_endpoint_consistency(client: TestClient):
    """Verify device list and devices-info endpoints agree."""
    list_resp = client.get("/api/v1/devices")
    info_resp = client.get("/api/v1/devices-info")
    assert list_resp.status_code == 200
    assert info_resp.status_code == 200
    assert set(list_resp.json()) == set(info_resp.json().keys())


# =============================================================================
# Profiles that load many devices (self-contained startup scripts)
# =============================================================================

class TestXPDProfile:
    """XPD beamline (X-ray Powder Diffraction) — 36 startup scripts, 101 devices.

    Largest successful profile.  Device scripts have self-contained imports
    so they survive even when 00-startup.py partially fails.
    """

    def test_loads_healthy(self, xpd_client):
        _assert_service_healthy(xpd_client, min_devices=80)

    def test_device_metadata_valid(self, xpd_client):
        _assert_devices_have_valid_metadata(xpd_client)

    def test_cross_endpoint_consistency(self, xpd_client):
        _assert_cross_endpoint_consistency(xpd_client)

    def test_large_device_count(self, xpd_client):
        """XPD has 101 top-level devices — verify bulk endpoint handles scale."""
        response = xpd_client.get("/api/v1/devices")
        assert response.status_code == 200
        devices = response.json()
        assert len(devices) >= 80, f"XPD should have many devices, got {len(devices)}"

    def test_device_label_distribution(self, xpd_client):
        """XPD should have multiple device type categories."""
        response = xpd_client.get("/api/v1/devices/types")
        assert response.status_code == 200
        types = response.json()
        assert len(types) >= 2, f"Expected multiple device types, got {types}"

    def test_device_classes_diverse(self, xpd_client):
        """XPD should have many ophyd device classes."""
        response = xpd_client.get("/api/v1/devices/classes")
        assert response.status_code == 200
        classes = response.json()
        assert len(classes) >= 10, f"Expected diverse classes, got {classes}"


class TestSRXProfile:
    """SRX beamline (Sub-micron Resolution X-ray) — 48 startup scripts, 50 devices.

    Self-contained device scripts.  Loads detectors, motors, signals.
    """

    def test_loads_healthy(self, srx_client):
        _assert_service_healthy(srx_client, min_devices=30)

    def test_device_metadata_valid(self, srx_client):
        _assert_devices_have_valid_metadata(srx_client)

    def test_cross_endpoint_consistency(self, srx_client):
        _assert_cross_endpoint_consistency(srx_client)

    def test_has_detectors_and_motors(self, srx_client):
        """SRX should have both detector and motor device types."""
        response = srx_client.get("/api/v1/devices/types")
        assert response.status_code == 200
        types = response.json()
        assert "motor" in types, "SRX should have motor devices"
        assert "detector" in types, "SRX should have detector devices"

    def test_device_classes_diverse(self, srx_client):
        """SRX should have many ophyd device classes."""
        response = srx_client.get("/api/v1/devices/classes")
        assert response.status_code == 200
        classes = response.json()
        assert len(classes) >= 20, f"Expected diverse classes, got {classes}"


class TestISSProfile:
    """ISS beamline (Inner Shell Spectroscopy) — 48 startup scripts, 14 devices.

    Loads custom device classes (Electrometer, EncoderFS, Accelerator).
    Many scripts fail due to infrastructure dependencies but device
    definition scripts in the middle of the chain survive.
    """

    def test_loads_healthy(self, iss_client):
        _assert_service_healthy(iss_client, min_devices=5)

    def test_device_metadata_valid(self, iss_client):
        _assert_devices_have_valid_metadata(iss_client)

    def test_cross_endpoint_consistency(self, iss_client):
        _assert_cross_endpoint_consistency(iss_client)

    def test_has_custom_classes(self, iss_client):
        """ISS should have custom beamline device classes."""
        response = iss_client.get("/api/v1/devices/classes")
        assert response.status_code == 200
        classes = response.json()
        assert len(classes) >= 5, f"Expected custom classes, got {classes}"


class TestTSTProfile:
    """TST beamline (Test) — 7 startup scripts, 6 devices.

    Uses ophyd-async devices (HDFPanda, Motor, VimbaDetector) alongside
    ophyd.sim devices (SynAxis, SynGauss).
    """

    def test_loads_healthy(self, tst_client):
        _assert_service_healthy(tst_client, min_devices=4)

    def test_device_metadata_valid(self, tst_client):
        _assert_devices_have_valid_metadata(tst_client)

    def test_cross_endpoint_consistency(self, tst_client):
        _assert_cross_endpoint_consistency(tst_client)

    def test_has_ophyd_async_classes(self, tst_client):
        """TST uses ophyd-async devices (HDFPanda, Motor, VimbaDetector)."""
        response = tst_client.get("/api/v1/devices/classes")
        assert response.status_code == 200
        classes = response.json()
        assert len(classes) >= 3, f"Expected ophyd-async classes, got {classes}"


# =============================================================================
# Profiles with limited off-site loading (infrastructure dependencies)
# =============================================================================

class TestHEXProfile:
    """HEX beamline (Hard X-ray Engineering) — 15 startup scripts.

    All ophyd-async devices.  00-startup.py defines file_loading_timer at
    the end, but fails midway due to Redis/Tiled/Kafka dependencies.
    Every subsequent script starts with file_loading_timer.start_timer()
    and fails immediately.  Loads 0 devices off-site but the service
    starts healthy.
    """

    def test_starts_healthy(self, hex_client):
        """Service starts healthy even with 0 devices loaded."""
        response = hex_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_endpoints_respond(self, hex_client):
        """All endpoints respond correctly even with empty registry."""
        assert hex_client.get("/api/v1/devices").status_code == 200
        assert hex_client.get("/api/v1/devices-info").status_code == 200
        assert hex_client.get("/api/v1/devices/types").status_code == 200
        assert hex_client.get("/api/v1/devices/classes").status_code == 200

    def test_cross_endpoint_consistency(self, hex_client):
        _assert_cross_endpoint_consistency(hex_client)


class TestCSXProfile:
    """CSX beamline (Coherent Soft X-ray) — 5 startup scripts + csx1/ package.

    Uses modular package layout.  00-nsls2-tools.py fails on nslsii
    configure_base, and 90-softGluescalar.py times out on PV connections.
    Loads 0 devices off-site but the service starts healthy.
    """

    def test_starts_healthy(self, csx_client):
        """Service starts healthy even with 0 devices loaded."""
        response = csx_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_endpoints_respond(self, csx_client):
        """All endpoints respond correctly even with empty registry."""
        assert csx_client.get("/api/v1/devices").status_code == 200
        assert csx_client.get("/api/v1/devices-info").status_code == 200
        assert csx_client.get("/api/v1/devices/types").status_code == 200
        assert csx_client.get("/api/v1/devices/classes").status_code == 200

    def test_cross_endpoint_consistency(self, csx_client):
        _assert_cross_endpoint_consistency(csx_client)


# =============================================================================
# Cross-Beamline Comparison
# =============================================================================

class TestAllBeamlinesLoad:
    """Verify all 6 beamlines start the service successfully."""

    @pytest.mark.parametrize("beamline", ["tst", "xpd", "iss", "srx"])
    def test_beamlines_with_devices(self, beamline, request):
        """Beamlines with self-contained scripts load devices."""
        client = request.getfixturevalue(f"{beamline}_client")
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["devices_loaded"] > 0, f"{beamline} loaded 0 devices"

    @pytest.mark.parametrize("beamline", ["hex", "csx"])
    def test_beamlines_start_healthy(self, beamline, request):
        """Beamlines with infrastructure deps still start healthy."""
        client = request.getfixturevalue(f"{beamline}_client")
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
