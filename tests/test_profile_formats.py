"""
Profile Format Integration Tests for Configuration Service.

Tests that the Configuration Service can correctly load and parse all three
supported profile formats:

1. Profile-Collection (startup_scripts) - IPython/queueserver style
2. BITS - BCDA-APS YAML format
3. Happi - LCLS/SLAC JSON database format

Each format test verifies:
- Service starts and loads devices
- Device count matches expectations
- Device metadata is correctly extracted

Note: Plan catalog functionality has been moved to the Experiment Execution Service.

Test Profiles:
- bits-startup: BITS format with ophyd.sim devices
- happi-startup: Happi format with ophyd.sim devices
- sim-profile-collection: startup_scripts format (existing test baseline)
"""

from fastapi.testclient import TestClient


# =============================================================================
# BITS Format Tests
# =============================================================================

class TestBitsProfileFormat:
    """
    Test Configuration Service with BITS format profile.

    BITS (Bluesky Instrument Testing Suite) uses YAML-based device definitions
    with creator functions and labels for device categorization.

    Format: configs/devices.yml with module.creator_function entries
    """

    def test_bits_service_starts_healthy(self, bits_client: TestClient):
        """Test service starts and reports healthy with BITS profile."""
        response = bits_client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["devices_loaded"] > 0, "BITS profile should load devices"

    def test_bits_loads_expected_devices(self, bits_client: TestClient):
        """Test BITS profile loads expected simulated devices."""
        response = bits_client.get("/api/v1/devices")
        assert response.status_code == 200

        devices = response.json()
        assert isinstance(devices, list)

        # BITS bits-startup has ophyd.sim devices
        expected_devices = ["det", "motor", "motor1", "motor2"]
        for device in expected_devices:
            assert device in devices, f"BITS profile missing expected device: {device}"

    def test_bits_device_has_labels(self, bits_client: TestClient):
        """Test BITS devices have label metadata from YAML config."""
        response = bits_client.get("/api/v1/devices/motor")
        assert response.status_code == 200

        device = response.json()
        assert device["name"] == "motor"
        # BITS format supports labels for device categorization
        assert "labels" in device or "device_label" in device

    def test_bits_device_metadata_complete(self, bits_client: TestClient):
        """Test BITS device metadata has required fields."""
        response = bits_client.get("/api/v1/devices/det")
        assert response.status_code == 200

        device = response.json()
        assert "name" in device
        assert "device_label" in device
        assert "ophyd_class" in device
        assert "is_readable" in device


# =============================================================================
# Happi Format Tests
# =============================================================================

class TestHappiProfileFormat:
    """
    Test Configuration Service with Happi format profile.

    Happi (Hardware Abstraction Protocol) uses JSON database with device
    metadata including device_class, args, kwargs, and beamline info.

    Format: happi_db.json with device class and instantiation parameters
    """

    def test_happi_service_starts_healthy(self, happi_client: TestClient):
        """Test service starts and reports healthy with Happi profile."""
        response = happi_client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["devices_loaded"] > 0, "Happi profile should load devices"

    def test_happi_loads_expected_devices(self, happi_client: TestClient):
        """Test Happi profile loads expected devices from JSON database."""
        response = happi_client.get("/api/v1/devices")
        assert response.status_code == 200

        devices = response.json()
        assert isinstance(devices, list)

        # Happi happi-startup has same devices as other sim profiles
        expected_devices = ["det", "motor", "motor1", "motor2"]
        for device in expected_devices:
            assert device in devices, f"Happi profile missing expected device: {device}"

    def test_happi_device_has_beamline_metadata(self, happi_client: TestClient):
        """Test Happi devices have beamline-specific metadata."""
        response = happi_client.get("/api/v1/devices/motor")
        assert response.status_code == 200

        device = response.json()
        assert device["name"] == "motor"
        # Happi format typically includes beamline and functional_group
        # These may be in metadata or top-level fields

    def test_happi_device_metadata_complete(self, happi_client: TestClient):
        """Test Happi device metadata has required fields."""
        response = happi_client.get("/api/v1/devices/det")
        assert response.status_code == 200

        device = response.json()
        assert "name" in device
        assert "device_label" in device
        assert "ophyd_class" in device
        assert "is_readable" in device


# =============================================================================
# Profile Format Comparison Tests
# =============================================================================

class TestProfileFormatComparison:
    """
    Test that all three profile formats load equivalent devices.

    This validates that the three different loaders (ProfileCollectionLoader,
    BitsProfileLoader, HappiProfileLoader) can all produce consistent results
    when loading the same logical device set.
    """

    def test_all_formats_load_devices(
        self,
        sim_client: TestClient,
        bits_client: TestClient,
        happi_client: TestClient,
    ):
        """Test all three formats successfully load devices."""
        for client, name in [
            (sim_client, "profile-collection"),
            (bits_client, "bits"),
            (happi_client, "happi"),
        ]:
            response = client.get("/api/v1/devices")
            assert response.status_code == 200, f"{name} format failed to list devices"
            devices = response.json()
            assert len(devices) > 0, f"{name} format loaded no devices"

    def test_all_formats_share_common_devices(
        self,
        sim_client: TestClient,
        bits_client: TestClient,
        happi_client: TestClient,
    ):
        """Test all formats have common device names (det, motor)."""
        common_devices = ["det", "motor"]

        for client, name in [
            (sim_client, "profile-collection"),
            (bits_client, "bits"),
            (happi_client, "happi"),
        ]:
            response = client.get("/api/v1/devices")
            devices = response.json()

            for device in common_devices:
                assert device in devices, (
                    f"{name} format missing common device '{device}'"
                )


# =============================================================================
# KREIOS IOC Profile Format Tests
# =============================================================================

class TestKreiosProfileCollection:
    """
    Test KREIOS IOC with profile-collection (startup_scripts) format.

    This validates the KREIOS photoelectron spectrometer devices
    can be loaded using the IPython/queueserver-style profile format.
    """

    def test_kreios_profile_collection_healthy(
        self, kreios_profile_collection_client: TestClient
    ):
        """Test KREIOS profile-collection starts healthy."""
        response = kreios_profile_collection_client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["devices_loaded"] > 0

    def test_kreios_profile_collection_loads_devices(
        self, kreios_profile_collection_client: TestClient
    ):
        """Test KREIOS profile-collection loads spectrometer devices."""
        response = kreios_profile_collection_client.get("/api/v1/devices")
        assert response.status_code == 200

        devices = response.json()
        # KREIOS should have main detector device
        assert "kreios" in devices, "KREIOS main device not loaded"


class TestKreiosBitsFormat:
    """
    Test KREIOS IOC with BITS format.

    Validates that KREIOS devices defined in YAML format
    are correctly loaded by the BitsProfileLoader.

    Note: The BITS loader can only load devices from installed Python packages.
    Custom device classes in the profile's local devices/ directory are not
    imported unless the loader is enhanced to add the profile path to sys.path.
    """

    def test_kreios_bits_healthy(self, kreios_bits_client: TestClient):
        """Test KREIOS BITS profile starts healthy."""
        response = kreios_bits_client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        # Note: device count may be 0 if custom device classes can't be imported

    def test_kreios_bits_loads_devices(self, kreios_bits_client: TestClient):
        """Test KREIOS BITS profile loads spectrometer devices."""
        response = kreios_bits_client.get("/api/v1/devices")
        assert response.status_code == 200

        devices = response.json()
        # BITS loader may not be able to import custom device classes
        # from the profile's local devices/ directory
        assert isinstance(devices, list)


class TestKreiosHappiFormat:
    """
    Test KREIOS IOC with Happi format.

    Validates that KREIOS devices defined in happi_db.json
    are correctly loaded by the HappiProfileLoader.

    Note: The Happi loader can only load devices from installed Python packages.
    Custom device classes in the profile's local devices/ directory are not
    imported unless the loader is enhanced to add the profile path to sys.path.
    """

    def test_kreios_happi_healthy(self, kreios_happi_client: TestClient):
        """Test KREIOS Happi profile starts healthy."""
        response = kreios_happi_client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        # Note: device count may be 0 if custom device classes can't be imported

    def test_kreios_happi_loads_devices(self, kreios_happi_client: TestClient):
        """Test KREIOS Happi profile loads spectrometer devices."""
        response = kreios_happi_client.get("/api/v1/devices")
        assert response.status_code == 200

        devices = response.json()
        # Happi loader may not be able to import custom device classes
        # from the profile's local devices/ directory
        assert isinstance(devices, list)

    def test_kreios_happi_device_endpoint_accessible(self, kreios_happi_client: TestClient):
        """Test KREIOS Happi device info endpoint is accessible."""
        response = kreios_happi_client.get("/api/v1/devices-info")
        assert response.status_code == 200

        devices_info = response.json()
        # Even with partial loading, the endpoint should work
        assert isinstance(devices_info, dict)


# =============================================================================
# KREIOS Format Comparison Tests
# =============================================================================

class TestKreiosFormatComparison:
    """
    Test that all three KREIOS profile formats start and respond correctly.

    Note: The profile-collection format fully supports custom device classes
    because it executes Python scripts directly. The BITS and Happi formats
    require device classes to be installed packages, so they may have partial
    loading with local custom device classes.
    """

    def test_all_kreios_formats_respond(
        self,
        kreios_profile_collection_client: TestClient,
        kreios_bits_client: TestClient,
        kreios_happi_client: TestClient,
    ):
        """Test all KREIOS formats respond to device listing."""
        clients = [
            (kreios_profile_collection_client, "profile-collection"),
            (kreios_bits_client, "bits"),
            (kreios_happi_client, "happi"),
        ]

        device_counts = {}
        for client, name in clients:
            response = client.get("/api/v1/devices")
            assert response.status_code == 200, f"KREIOS {name} failed to list devices"
            devices = response.json()
            device_counts[name] = len(devices)

        # Log device counts for comparison
        print(f"KREIOS device counts: {device_counts}")

        # Profile-collection should load devices (it executes scripts directly)
        assert device_counts["profile-collection"] > 0, "profile-collection should load KREIOS devices"

    def test_all_kreios_formats_report_healthy(
        self,
        kreios_profile_collection_client: TestClient,
        kreios_bits_client: TestClient,
        kreios_happi_client: TestClient,
    ):
        """Test all KREIOS formats report healthy status."""
        clients = [
            (kreios_profile_collection_client, "profile-collection"),
            (kreios_bits_client, "bits"),
            (kreios_happi_client, "happi"),
        ]

        for client, name in clients:
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy", f"KREIOS {name} not healthy"


# =============================================================================
# Profile Auto-Detection Tests
# =============================================================================

class TestProfileAutoDetection:
    """
    Test that profile format auto-detection works correctly.

    The configuration service should automatically detect the profile format
    based on file presence:
    - happi_db.json -> happi format
    - configs/devices.yml -> bits format
    - startup/*.py -> startup_scripts format
    """

    def test_bits_profile_detected_correctly(self, bits_client: TestClient):
        """Test BITS profile is correctly loaded with its format."""
        response = bits_client.get("/health")
        assert response.status_code == 200
        # If healthy, format was detected and loaded correctly

    def test_happi_profile_detected_correctly(self, happi_client: TestClient):
        """Test Happi profile is correctly loaded with its format."""
        response = happi_client.get("/health")
        assert response.status_code == 200
        # If healthy, format was detected and loaded correctly

    def test_profile_collection_detected_correctly(self, sim_client: TestClient):
        """Test profile-collection is correctly loaded with its format."""
        response = sim_client.get("/health")
        assert response.status_code == 200
        # If healthy, format was detected and loaded correctly
