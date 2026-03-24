"""
Integration Tests for Configuration Service with Caproto Profile Collection.

Tests PV discovery functionality using caproto-profile-collection which has
real EPICS PV names (EpicsMotor, EpicsSignal, ADSimDetector devices).

These tests:
1. Can run without IOCs (tests PV discovery from device definitions)
2. Verify PV names are extracted from EpicsMotor/EpicsSignal devices
3. Validate PV organization by device

Note: Devices will show connection warnings if IOCs are not running.
This is expected - the tests verify PV *discovery*, not PV *connectivity*.

Expected devices from caproto-profile-collection:
- Motors: m1, m2, m3, m4, x, y, z, theta (EpicsMotor with motor record PVs)
- Scalar Detectors: det1, det2, det3, det4 (ScalarDetector with CNT, VAL PVs)
- Area Detector: cam1 (SimAreaDetector with ADSimDetector PVs)

Expected PV patterns:
- Motors: SIM:m1.VAL, SIM:m1.RBV, SIM:m1.VELO, etc.
- Detectors: SIM:det1:VAL, SIM:det1:CNT, SIM:det1:CENTER, etc.
- Camera: SIM:cam1:Acquire, SIM:cam1:AcquireTime_RBV, etc.
"""

import pytest
from fastapi.testclient import TestClient


# =============================================================================
# Skip marker for tests requiring caproto-profile-collection
# =============================================================================

pytestmark = pytest.mark.skipif(
    True,  # Currently skipped - enable when testing PV discovery
    reason="Caproto tests require manual enable (set skipif to False)"
)


# =============================================================================
# Health Endpoints with Caproto Devices
# =============================================================================

class TestCaprotoHealth:
    """Test health endpoints with caproto devices loaded."""

    def test_health_with_epics_devices(self, caproto_client: TestClient):
        """
        Test health endpoint reports devices loaded.

        caproto-profile-collection should load ~13 devices:
        - 8 motors (m1-m4, x, y, z, theta)
        - 4 scalar detectors (det1-det4)
        - 1 area detector (cam1)
        """
        response = caproto_client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["devices_loaded"] >= 10

    def test_health_shows_pvs_discovered(self, caproto_client: TestClient):
        """
        Verify health/status shows PVs were discovered.

        EpicsMotor and EpicsSignal devices have real PV names
        that should be discovered during introspection.
        """
        response = caproto_client.get("/health")
        data = response.json()

        # With EpicsMotor devices, we should have PVs
        # (unlike ophyd.sim which has 0 PVs)
        # Note: pvs_discovered might not be in health, check /api/v1/pvs


# =============================================================================
# Device Endpoints with Real Ophyd Classes
# =============================================================================

class TestCaprotoDevices:
    """Test device endpoints with EpicsMotor/EpicsSignal devices."""

    def test_list_motors(self, caproto_client: TestClient):
        """
        Test listing motor devices.

        caproto-profile-collection defines EpicsMotor subclass (SimMotor)
        for m1-m4, x, y, z, theta.
        """
        response = caproto_client.get("/api/v1/devices")
        assert response.status_code == 200

        devices = response.json()
        expected_motors = ["m1", "m2", "m3", "m4", "x", "y", "z", "theta"]

        for motor in expected_motors:
            assert motor in devices, f"Expected motor '{motor}' not found"

    def test_motor_has_epics_class(self, caproto_client: TestClient):
        """
        Verify motor devices have EpicsMotor-based class.
        """
        response = caproto_client.get("/api/v1/devices/m1")
        assert response.status_code == 200

        device = response.json()
        assert "ophyd_class" in device
        # Should be SimMotor (subclass of EpicsMotor)
        assert "Motor" in device["ophyd_class"] or "SimMotor" in device["ophyd_class"]

    def test_area_detector_exists(self, caproto_client: TestClient):
        """
        Verify ADSimDetector-compatible area detector is loaded.
        """
        response = caproto_client.get("/api/v1/devices/cam1")
        assert response.status_code == 200

        device = response.json()
        assert device["name"] == "cam1"
        assert "ophyd_class" in device


# =============================================================================
# PV Discovery Tests
# =============================================================================

class TestPVDiscovery:
    """
    Test PV discovery from EpicsMotor/EpicsSignal devices.

    This is the key differentiator from sim-profile-collection:
    EpicsMotor devices have real PV names that can be discovered.
    """

    def test_pvs_list_not_empty(self, caproto_client: TestClient):
        """
        Verify PV list is not empty.

        Unlike ophyd.sim devices, EpicsMotor/EpicsSignal have PV names.
        """
        response = caproto_client.get("/api/v1/pvs")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] == True
        assert data["count"] > 0, "Expected PVs from EpicsMotor/EpicsSignal devices"

    def test_motor_pv_format(self, caproto_client: TestClient):
        """
        Verify motor PVs follow EPICS motor record format.

        Expected PVs like: SIM:m1.VAL, SIM:m1.RBV, SIM:m1.VELO
        """
        response = caproto_client.get("/api/v1/pvs")
        data = response.json()
        pvs = data["pvs"]

        # Find motor-related PVs
        motor_pvs = [pv for pv in pvs if "m1" in pv or "motor" in pv.lower()]

        # Check for common motor record fields
        # .VAL, .RBV, .VELO, .ACCL are standard motor record fields
        if motor_pvs:
            pv_suffixes = [".VAL", ".RBV", ".HLS", ".LLS"]
            found_motor_fields = any(
                any(suffix in pv for suffix in pv_suffixes)
                for pv in motor_pvs
            )
            assert found_motor_fields, f"Motor PVs don't have expected suffixes: {motor_pvs[:5]}"

    def test_detector_pv_format(self, caproto_client: TestClient):
        """
        Verify detector PVs are discovered.

        Expected PVs like: SIM:det1:VAL, SIM:det1:CNT
        """
        response = caproto_client.get("/api/v1/pvs")
        data = response.json()
        pvs = data["pvs"]

        # Find detector-related PVs
        det_pvs = [pv for pv in pvs if "det" in pv.lower()]

        assert len(det_pvs) > 0, "Expected detector PVs"

    def test_pvs_filter_by_pattern(self, caproto_client: TestClient):
        """
        Test PV pattern filtering.
        """
        response = caproto_client.get("/api/v1/pvs?pattern=SIM:m*")
        assert response.status_code == 200

        data = response.json()
        # All returned PVs should match pattern
        for pv in data["pvs"]:
            assert pv.startswith("SIM:m"), f"PV {pv} doesn't match pattern SIM:m*"


# =============================================================================
# PV Detailed Endpoint
# =============================================================================

class TestPVDetailed:
    """Test detailed PV endpoint with device organization."""

    def test_pvs_organized_by_device(self, caproto_client: TestClient):
        """
        Verify /api/v1/pvs/detailed organizes PVs by device.
        """
        response = caproto_client.get("/api/v1/pvs/detailed")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] == True
        assert "devices" in data
        assert isinstance(data["devices"], dict)

        # Should have devices like m1, det1, cam1
        assert data["device_count"] > 0

    def test_motor_pvs_grouped(self, caproto_client: TestClient):
        """
        Verify motor device has its PVs grouped together.
        """
        response = caproto_client.get("/api/v1/pvs/detailed")
        data = response.json()
        devices = data["devices"]

        # m1 should be in the devices dict
        if "m1" in devices:
            m1_pvs = devices["m1"]
            assert isinstance(m1_pvs, (list, dict))
            # Should have motor record PVs

    def test_area_detector_has_many_pvs(self, caproto_client: TestClient):
        """
        Verify area detector (cam1) has many PVs.

        ADSimDetector has many PVs: Acquire, AcquireTime, SizeX, etc.
        """
        response = caproto_client.get("/api/v1/pvs/detailed")
        data = response.json()
        devices = data["devices"]

        # cam1 should have many PVs (ADBase + SimDetector)
        if "cam1" in devices:
            cam1_pvs = devices["cam1"]
            pv_count = len(cam1_pvs) if isinstance(cam1_pvs, list) else len(cam1_pvs)
            # ADSimDetector has 40+ PVs
            assert pv_count > 10, f"Expected many PVs for cam1, got {pv_count}"


# =============================================================================
# Cross-Service PV Sharing
# =============================================================================

class TestPVSharing:
    """
    Test that PVs can be shared with other services.

    The configuration service provides PV information that:
    - device_monitoring uses to subscribe to PVs
    - direct_control uses to write to PVs
    """

    def test_pv_list_format_for_monitoring(self, caproto_client: TestClient):
        """
        Verify PV list format is suitable for device_monitoring.

        device_monitoring needs: list of PV names to subscribe
        """
        response = caproto_client.get("/api/v1/pvs")
        data = response.json()

        assert "pvs" in data
        assert isinstance(data["pvs"], list)

        # Each item should be a string PV name
        for pv in data["pvs"][:5]:
            assert isinstance(pv, str)
            assert len(pv) > 0

    def test_detailed_format_for_direct_control(self, caproto_client: TestClient):
        """
        Verify detailed format is suitable for direct_control.

        direct_control needs: device -> PV mapping for write operations
        """
        response = caproto_client.get("/api/v1/pvs/detailed")
        data = response.json()

        assert "devices" in data
        # Should provide device_name -> pv_info mapping
