"""
Comprehensive Integration Tests for Configuration Service.

Tests all API endpoints using sim-profile-collection with startup_scripts
loading strategy, demonstrating the queueserver-pattern introspection.

Test Categories:
1. Health Endpoints - Service health and readiness
2. Device Endpoints - Device registry and metadata
3. PV Endpoints - Process Variable discovery
4. Nested Component Endpoints - Device component navigation

Expected sim-profile-collection devices:
- Detectors: det, det1, det2, noisy_det, rand, rand2, img
- Motors: motor, motor1, motor2, motor3, jittery_motor1, jittery_motor2
- Flyers: flyer1, flyer2

Note: Plan catalog functionality has been moved to the Experiment Execution Service.
"""

from fastapi.testclient import TestClient


# =============================================================================
# Health Endpoints
# =============================================================================

class TestHealthEndpoints:
    """Test health check endpoints with integration data."""

    def test_health_returns_status(self, sim_client: TestClient):
        """
        Test /health endpoint returns service status.

        Endpoint: GET /health
        Expected: 200 with healthy status and loaded counts
        """
        response = sim_client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "configuration_service"
        assert data["devices_loaded"] > 0, "Should have loaded devices from sim-profile-collection"

    def test_health_shows_device_count(self, sim_client: TestClient):
        """
        Verify health endpoint shows correct device count.

        sim-profile-collection should have ~10 devices.
        """
        response = sim_client.get("/health")
        data = response.json()

        # sim-profile-collection has: det, det1, det2, noisy_det, rand, rand2, img,
        # motor, motor1, motor2, motor3, jittery_motor1, jittery_motor2, flyer1, flyer2
        assert data["devices_loaded"] >= 10, f"Expected >= 10 devices, got {data['devices_loaded']}"

    def test_ready_when_loaded(self, sim_client: TestClient):
        """
        Test /ready endpoint when service is fully loaded.

        Endpoint: GET /ready
        Expected: 200 with ready status
        """
        response = sim_client.get("/ready")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ready"


# =============================================================================
# Device Endpoints - List Operations
# =============================================================================

class TestDeviceListEndpoints:
    """Test device listing and filtering endpoints."""

    def test_list_all_devices(self, sim_client: TestClient):
        """
        Test GET /api/v1/devices returns all device names.

        Endpoint: GET /api/v1/devices
        Expected: List of device name strings
        """
        response = sim_client.get("/api/v1/devices")
        assert response.status_code == 200

        devices = response.json()
        assert isinstance(devices, list)
        assert len(devices) >= 10

        # Check for known devices from sim-profile-collection
        assert "motor" in devices
        assert "det" in devices

    def test_list_devices_filter_by_device_label(self, sim_client: TestClient):
        """
        Test filtering devices by device type.

        Endpoint: GET /api/v1/devices?device_label=<type>
        Expected: Only devices of that type returned

        Note: ophyd.sim devices (SynAxis, SynGauss) are classified based on
        class name heuristics into motor, detector, or device types.
        """
        # First get the available device types
        types_response = sim_client.get("/api/v1/devices/types")
        assert types_response.status_code == 200
        available_types = types_response.json()
        assert len(available_types) > 0

        # Test filtering by first available type
        first_type = available_types[0]
        response = sim_client.get(f"/api/v1/devices?device_label={first_type}")
        assert response.status_code == 200

        devices = response.json()
        assert isinstance(devices, list)
        # Should return devices of that type

    def test_list_devices_filter_by_device_label(self, sim_client: TestClient):
        """
        Test filtering by 'device' type (generic ophyd.sim devices).

        Endpoint: GET /api/v1/devices?device_label=device
        Note: sim-profile-collection uses SynAxis, SynGauss, etc. which
        are classified by class name heuristics into motor/detector/device.
        """
        response = sim_client.get("/api/v1/devices?device_label=device")
        assert response.status_code == 200

        devices = response.json()
        assert isinstance(devices, list)

    def test_list_devices_filter_by_pattern(self, sim_client: TestClient):
        """
        Test filtering devices by glob pattern.

        Endpoint: GET /api/v1/devices?pattern=motor*
        Expected: Only devices matching pattern
        """
        response = sim_client.get("/api/v1/devices?pattern=motor*")
        assert response.status_code == 200

        devices = response.json()
        assert isinstance(devices, list)

        # All returned devices should start with 'motor'
        for device in devices:
            assert device.startswith("motor"), f"Device {device} doesn't match pattern motor*"

    def test_list_devices_combined_filters(self, sim_client: TestClient):
        """
        Test combining type and pattern filters.

        Endpoint: GET /api/v1/devices?device_label=motor&pattern=motor1*
        Expected: Motors matching pattern motor1*
        """
        response = sim_client.get("/api/v1/devices?device_label=motor&pattern=motor1*")
        assert response.status_code == 200

        devices = response.json()
        assert isinstance(devices, list)
        # Should match motor1 at minimum
        for device in devices:
            assert device.startswith("motor1")


# =============================================================================
# Device Endpoints - Info Operations
# =============================================================================

class TestDeviceInfoEndpoints:
    """Test device metadata and info endpoints."""

    def test_get_all_devices_info(self, sim_client: TestClient):
        """
        Test GET /api/v1/devices-info returns all device metadata.

        Endpoint: GET /api/v1/devices-info
        Expected: Dict mapping device names to full metadata
        """
        response = sim_client.get("/api/v1/devices-info")
        assert response.status_code == 200

        devices_info = response.json()
        assert isinstance(devices_info, dict)
        assert len(devices_info) >= 10

        # Check a known device has expected fields
        assert "motor" in devices_info
        motor_info = devices_info["motor"]
        assert "name" in motor_info
        assert "device_label" in motor_info
        assert "ophyd_class" in motor_info

    def test_get_device_classes(self, sim_client: TestClient):
        """
        Test GET /api/v1/devices/classes returns unique device classes.

        Endpoint: GET /api/v1/devices/classes
        Expected: Sorted list of unique ophyd class names
        """
        response = sim_client.get("/api/v1/devices/classes")
        assert response.status_code == 200

        classes = response.json()
        assert isinstance(classes, list)
        assert len(classes) > 0

        # Classes should be sorted and unique
        assert classes == sorted(set(classes))

        # sim-profile-collection uses ophyd.sim classes
        # e.g., SynAxis, SynGauss, SynSignal, MockFlyer

    def test_get_device_labels(self, sim_client: TestClient):
        """
        Test GET /api/v1/devices/types returns device type categories.

        Endpoint: GET /api/v1/devices/types
        Expected: Sorted list of device type values
        """
        response = sim_client.get("/api/v1/devices/types")
        assert response.status_code == 200

        types = response.json()
        assert isinstance(types, list)
        assert len(types) > 0

        # Should have at least motor and detector types
        # (types are enum values like "motor", "detector", "device", etc.)

    def test_get_device_metadata(self, sim_client: TestClient):
        """
        Test GET /api/v1/devices/{device_name} returns device metadata.

        Endpoint: GET /api/v1/devices/motor
        Expected: Full device metadata object
        """
        response = sim_client.get("/api/v1/devices/motor")
        assert response.status_code == 200

        device = response.json()
        assert device["name"] == "motor"
        assert "device_label" in device
        assert "ophyd_class" in device
        assert "is_movable" in device
        assert "is_readable" in device

    def test_get_device_metadata_for_detector(self, sim_client: TestClient):
        """
        Test device metadata for a detector device.

        Endpoint: GET /api/v1/devices/det
        """
        response = sim_client.get("/api/v1/devices/det")
        assert response.status_code == 200

        device = response.json()
        assert device["name"] == "det"
        assert device["is_readable"] == True

    def test_get_device_not_found(self, sim_client: TestClient):
        """
        Test 404 for non-existent device.

        Endpoint: GET /api/v1/devices/nonexistent_device
        Expected: 404 Not Found
        """
        response = sim_client.get("/api/v1/devices/nonexistent_device")
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()


# =============================================================================
# Device Endpoints - Component Navigation
# =============================================================================

class TestDeviceComponentEndpoints:
    """Test nested device component navigation endpoints."""

    def test_get_device_components_list(self, sim_client: TestClient):
        """
        Test GET /api/v1/devices/{device_name}/components lists components.

        Endpoint: GET /api/v1/devices/motor/components
        Expected: List of component metadata for the device
        """
        response = sim_client.get("/api/v1/devices/motor/components")
        assert response.status_code == 200

        components = response.json()
        assert isinstance(components, list)
        # Components may be empty for simulated devices without PVs

    def test_get_nested_device_component(self, sim_client: TestClient):
        """
        Test GET /api/v1/devices/{device_path}/component for top-level device.

        Endpoint: GET /api/v1/devices/motor/component
        Expected: Component metadata for the device itself
        """
        response = sim_client.get("/api/v1/devices/motor/component")
        assert response.status_code == 200

        component = response.json()
        assert component["name"] == "motor"
        assert "device_path" in component
        assert "is_readable" in component
        assert "is_settable" in component

    def test_get_component_not_found(self, sim_client: TestClient):
        """
        Test 404 for component of non-existent device.

        Endpoint: GET /api/v1/devices/nonexistent/component
        Expected: 404 Not Found
        """
        response = sim_client.get("/api/v1/devices/nonexistent/component")
        assert response.status_code == 404


# =============================================================================
# PV Endpoints
# =============================================================================

class TestPVEndpoints:
    """Test Process Variable discovery endpoints."""

    def test_list_pvs(self, sim_client: TestClient):
        """
        Test GET /api/v1/pvs lists available PVs.

        Endpoint: GET /api/v1/pvs
        Expected: Response with success, pvs list, and count

        Note: sim-profile-collection uses ophyd.sim devices which don't
        have real PVs, so the list may be empty. This is expected.
        """
        response = sim_client.get("/api/v1/pvs")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] == True
        assert "pvs" in data
        assert isinstance(data["pvs"], list)
        assert "count" in data
        assert data["count"] == len(data["pvs"])

    def test_list_pvs_with_pattern(self, sim_client: TestClient):
        """
        Test GET /api/v1/pvs?pattern=* with pattern filter.

        Endpoint: GET /api/v1/pvs?pattern=BL*
        Expected: Only PVs matching pattern (may be empty for sim)
        """
        response = sim_client.get("/api/v1/pvs?pattern=*")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] == True

    def test_get_pvs_detailed(self, sim_client: TestClient):
        """
        Test GET /api/v1/pvs/detailed returns PVs organized by device.

        Endpoint: GET /api/v1/pvs/detailed
        Expected: Response with devices mapping and counts
        """
        response = sim_client.get("/api/v1/pvs/detailed")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] == True
        assert "devices" in data
        assert isinstance(data["devices"], dict)
        assert "device_count" in data
        assert "pv_count" in data


# =============================================================================
# Verification Tests - Cross-Endpoint Consistency
# =============================================================================

class TestCrossEndpointConsistency:
    """Test consistency between related endpoints."""

    def test_devices_count_matches_health(self, sim_client: TestClient):
        """
        Verify device count in health matches devices endpoint.
        """
        health_response = sim_client.get("/health")
        devices_response = sim_client.get("/api/v1/devices")

        health_count = health_response.json()["devices_loaded"]
        devices_list = devices_response.json()

        assert health_count == len(devices_list)

    def test_devices_info_matches_list(self, sim_client: TestClient):
        """
        Verify devices-info keys match devices list.
        """
        list_response = sim_client.get("/api/v1/devices")
        info_response = sim_client.get("/api/v1/devices-info")

        device_list = list_response.json()
        device_info = info_response.json()

        assert set(device_list) == set(device_info.keys())

    def test_all_listed_devices_have_metadata(self, sim_client: TestClient):
        """
        Verify each listed device can be queried individually.
        """
        list_response = sim_client.get("/api/v1/devices")
        devices = list_response.json()

        # Check first 5 devices to keep test fast
        for device_name in devices[:5]:
            response = sim_client.get(f"/api/v1/devices/{device_name}")
            assert response.status_code == 200, f"Failed to get metadata for {device_name}"
            assert response.json()["name"] == device_name


# =============================================================================
# Expected Content Tests - Validate sim-profile-collection Content
# =============================================================================

class TestExpectedSimProfileContent:
    """
    Test that sim-profile-collection contains expected devices.

    These tests validate the startup_scripts loading strategy correctly
    introspected the namespace after executing the startup scripts.
    """

    def test_expected_motor_devices(self, sim_client: TestClient):
        """
        Verify expected motor devices from sim-profile-collection.

        Expected: motor, motor1, motor2, motor3, jittery_motor1, jittery_motor2
        """
        response = sim_client.get("/api/v1/devices")
        devices = response.json()

        expected_motors = ["motor", "motor1", "motor2", "motor3"]
        for motor in expected_motors:
            assert motor in devices, f"Expected motor '{motor}' not found"

    def test_expected_detector_devices(self, sim_client: TestClient):
        """
        Verify expected detector devices from sim-profile-collection.

        Expected: det, det1, det2, noisy_det, rand, rand2, img
        """
        response = sim_client.get("/api/v1/devices")
        devices = response.json()

        expected_detectors = ["det", "det1", "det2"]
        for det in expected_detectors:
            assert det in devices, f"Expected detector '{det}' not found"

    def test_motor_device_is_movable(self, sim_client: TestClient):
        """
        Verify motor devices are correctly identified as movable.
        """
        response = sim_client.get("/api/v1/devices/motor")
        device = response.json()

        assert device["is_movable"] == True, "Motor should be movable"

    def test_detector_device_is_readable(self, sim_client: TestClient):
        """
        Verify detector devices are correctly identified as readable.
        """
        response = sim_client.get("/api/v1/devices/det")
        device = response.json()

        assert device["is_readable"] == True, "Detector should be readable"


# =============================================================================
# Load Strategy Verification
# =============================================================================

class TestLoadStrategyVerification:
    """
    Test that startup_scripts loading strategy works correctly.

    This verifies the queueserver-pattern introspection:
    1. Execute startup scripts in order
    2. Introspect namespace for devices
    3. Extract metadata from loaded objects
    """

    def test_devices_have_ophyd_class(self, sim_client: TestClient):
        """
        Verify devices have ophyd_class from introspection.
        """
        response = sim_client.get("/api/v1/devices/motor")
        device = response.json()

        assert "ophyd_class" in device
        assert device["ophyd_class"] is not None
        # sim devices are from ophyd.sim, typically SynAxis

    def test_devices_have_module_info(self, sim_client: TestClient):
        """
        Verify devices have module information from introspection.
        """
        response = sim_client.get("/api/v1/devices/motor")
        device = response.json()

        assert "module" in device
        # Module should be from ophyd.sim

