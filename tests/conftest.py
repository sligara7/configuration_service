"""
Pytest configuration and fixtures for Configuration Service tests.

Provides fixtures for:
- Mock data testing (fast unit tests)
- Integration testing with sim-profile-collection (ophyd.sim devices, no PVs)
- Integration testing with caproto-profile-collection (EpicsMotor/EpicsSignal with PVs)

Profile Collections:
- sim-profile-collection: Uses ophyd.sim devices (SynAxis, SynGauss, etc.)
  - No PVs required - pure Python simulation
  - Good for basic device/plan introspection tests

- caproto-profile-collection: Uses EpicsMotor/EpicsSignal with Caproto IOCs
  - Requires Caproto IOCs to be running for connection
  - Has real PV names for PV discovery testing
  - Use for full PV integration tests
"""

import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from configuration_service.main import create_app
from configuration_service.config import Settings


# Get project root for profile paths
PROJECT_ROOT = Path(__file__).parent.parent

# Profile fixtures can live locally under tests/fixtures/profiles/,
# or point to the monorepo fixtures if available.
PROFILES_DIR = PROJECT_ROOT / "tests" / "fixtures" / "profiles"
MONOREPO_PROFILES = Path(os.environ.get(
    "BLUESKY_MONOREPO_PROFILES",
    str(Path.home() / "git_projects" / "bluesky-remote-architecture" / "tests" / "fixtures" / "profiles"),
))

def _find_profile(name: str) -> Path:
    """Find a profile directory, checking local then monorepo paths."""
    local = PROFILES_DIR / name
    if local.exists():
        return local
    return MONOREPO_PROFILES / name

SIM_PROFILE_PATH = _find_profile("sim-profile-collection")
CAPROTO_PROFILE_PATH = _find_profile("caproto-profile-collection")

# Profile format test paths
BITS_PROFILE_PATH = _find_profile("bits-startup")
HAPPI_PROFILE_PATH = _find_profile("happi-startup")

# KREIOS IOC profiles (all three formats)
KREIOS_PROFILE_COLLECTION_PATH = _find_profile("kreios-profile-collection")
KREIOS_BITS_PROFILE_PATH = _find_profile("kreios-bits-startup")
KREIOS_HAPPI_PROFILE_PATH = _find_profile("kreios-happi-startup")


@pytest.fixture
def mock_settings(tmp_path) -> Settings:
    """Settings configured for mock data (fast unit tests)."""
    return Settings(use_mock_data=True, db_path=tmp_path / "test.db")


@pytest.fixture
def sim_settings(tmp_path) -> Settings:
    """Settings configured for sim-profile-collection integration tests."""
    if not SIM_PROFILE_PATH.exists():
        pytest.skip(f"sim-profile-collection not found at {SIM_PROFILE_PATH}")
    return Settings(
        profile_path=SIM_PROFILE_PATH,
        load_strategy="startup_scripts",
        db_path=tmp_path / "test.db",
    )


@pytest.fixture
def caproto_settings(tmp_path) -> Settings:
    """
    Settings configured for caproto-profile-collection integration tests.

    Note: Devices will have PV names but may show connection warnings
    if Caproto IOCs are not running. This is fine for testing PV discovery.
    """
    if not CAPROTO_PROFILE_PATH.exists():
        pytest.skip(f"caproto-profile-collection not found at {CAPROTO_PROFILE_PATH}")
    return Settings(
        profile_path=CAPROTO_PROFILE_PATH,
        load_strategy="startup_scripts",
        db_path=tmp_path / "test.db",
    )


@pytest.fixture
def mock_client(mock_settings) -> TestClient:
    """
    Create test client with mock data.

    Fast client for unit tests that don't need real profile loading.
    """
    app = create_app(mock_settings)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def sim_client(sim_settings) -> TestClient:
    """
    Create test client with sim-profile-collection.

    Integration client that loads ophyd.sim devices and custom plans.
    Does NOT have real PVs - devices are pure Python simulations.
    """
    app = create_app(sim_settings)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def caproto_client(caproto_settings) -> TestClient:
    """
    Create test client with caproto-profile-collection.

    Integration client that loads EpicsMotor/EpicsSignal devices with PVs.
    Has real PV names for testing PV discovery functionality.

    Note: Will show connection warnings if IOCs not running - this is expected.
    """
    import warnings
    # Suppress ophyd connection warnings during test setup
    warnings.filterwarnings("ignore", category=UserWarning, module="ophyd")

    app = create_app(caproto_settings)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client(mock_settings) -> TestClient:
    """Default client using mock data (backward compatibility)."""
    app = create_app(mock_settings)
    with TestClient(app) as client:
        yield client


# =============================================================================
# Profile Format Testing Fixtures (BITS, Happi, Profile-Collection)
# =============================================================================

@pytest.fixture
def bits_settings(tmp_path) -> Settings:
    """Settings configured for BITS format profile testing."""
    if not BITS_PROFILE_PATH.exists():
        pytest.skip(f"bits-startup not found at {BITS_PROFILE_PATH}")
    return Settings(
        profile_path=BITS_PROFILE_PATH,
        load_strategy="bits",
        db_path=tmp_path / "test.db",
    )


@pytest.fixture
def happi_settings(tmp_path) -> Settings:
    """Settings configured for Happi format profile testing."""
    if not HAPPI_PROFILE_PATH.exists():
        pytest.skip(f"happi-startup not found at {HAPPI_PROFILE_PATH}")
    return Settings(
        profile_path=HAPPI_PROFILE_PATH,
        load_strategy="happi",
        db_path=tmp_path / "test.db",
    )


@pytest.fixture
def bits_client(bits_settings) -> TestClient:
    """
    Create test client with BITS format profile.

    Tests the BitsProfileLoader with YAML-based device definitions.
    """
    app = create_app(bits_settings)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def happi_client(happi_settings) -> TestClient:
    """
    Create test client with Happi format profile.

    Tests the HappiProfileLoader with JSON database format.
    """
    app = create_app(happi_settings)
    with TestClient(app) as client:
        yield client


# =============================================================================
# KREIOS IOC Profile Fixtures (all three formats)
# =============================================================================

@pytest.fixture
def kreios_profile_collection_settings(tmp_path) -> Settings:
    """Settings for KREIOS profile-collection format."""
    if not KREIOS_PROFILE_COLLECTION_PATH.exists():
        pytest.skip(f"kreios-profile-collection not found at {KREIOS_PROFILE_COLLECTION_PATH}")
    return Settings(
        profile_path=KREIOS_PROFILE_COLLECTION_PATH,
        load_strategy="startup_scripts",
        db_path=tmp_path / "test.db",
    )


@pytest.fixture
def kreios_bits_settings(tmp_path) -> Settings:
    """Settings for KREIOS BITS format."""
    if not KREIOS_BITS_PROFILE_PATH.exists():
        pytest.skip(f"kreios-bits-startup not found at {KREIOS_BITS_PROFILE_PATH}")
    return Settings(
        profile_path=KREIOS_BITS_PROFILE_PATH,
        load_strategy="bits",
        db_path=tmp_path / "test.db",
    )


@pytest.fixture
def kreios_happi_settings(tmp_path) -> Settings:
    """Settings for KREIOS Happi format."""
    if not KREIOS_HAPPI_PROFILE_PATH.exists():
        pytest.skip(f"kreios-happi-startup not found at {KREIOS_HAPPI_PROFILE_PATH}")
    return Settings(
        profile_path=KREIOS_HAPPI_PROFILE_PATH,
        load_strategy="happi",
        db_path=tmp_path / "test.db",
    )


@pytest.fixture
def kreios_profile_collection_client(kreios_profile_collection_settings) -> TestClient:
    """Test client for KREIOS profile-collection format."""
    import warnings
    warnings.filterwarnings("ignore", category=UserWarning, module="ophyd")
    app = create_app(kreios_profile_collection_settings)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def kreios_bits_client(kreios_bits_settings) -> TestClient:
    """Test client for KREIOS BITS format."""
    import warnings
    warnings.filterwarnings("ignore", category=UserWarning, module="ophyd")
    app = create_app(kreios_bits_settings)
    with TestClient(app) as client:
        yield client


# =============================================================================
# Real-World Beamline Profile Fixtures
# =============================================================================

# Paths to real beamline profile collections (external git repos)
BEAMLINE_PROFILES = {
    "csx": Path("/home/asligar/git_projects/csx-profile-collection"),
    "hex": Path("/home/asligar/git_projects/hex-profile-collection"),
    "iss": Path("/home/asligar/git_projects/iss-profile-collection"),
    "srx": Path("/home/asligar/git_projects/srx-profile-collection"),
    "tst": Path("/home/asligar/git_projects/tst-profile-collection"),
    "xpd": Path("/home/asligar/git_projects/xpd-profile-collection"),
}


def _make_beamline_client(profile_path: Path, load_strategy: str, tmp_path: Path):
    """Create a test client for a beamline profile collection."""
    import warnings
    warnings.filterwarnings("ignore", category=UserWarning, module="ophyd")
    warnings.filterwarnings("ignore", category=DeprecationWarning)

    settings = Settings(
        profile_path=profile_path,
        load_strategy=load_strategy,
        db_path=tmp_path / "test.db",
    )
    app = create_app(settings)
    return TestClient(app)


# YAML-based profiles (fast — no script execution)
@pytest.fixture
def hex_client(tmp_path) -> TestClient:
    """HEX beamline — YAML format with 120+ devices."""
    path = BEAMLINE_PROFILES["hex"]
    if not path.exists():
        pytest.skip(f"hex-profile-collection not found at {path}")
    with _make_beamline_client(path, "startup_scripts", tmp_path) as client:
        yield client


@pytest.fixture
def tst_client(tmp_path) -> TestClient:
    """TST beamline — YAML format with 100+ devices (ophyd-async)."""
    path = BEAMLINE_PROFILES["tst"]
    if not path.exists():
        pytest.skip(f"tst-profile-collection not found at {path}")
    with _make_beamline_client(path, "startup_scripts", tmp_path) as client:
        yield client


@pytest.fixture
def xpd_client(tmp_path) -> TestClient:
    """XPD beamline — YAML format with 280+ devices."""
    path = BEAMLINE_PROFILES["xpd"]
    if not path.exists():
        pytest.skip(f"xpd-profile-collection not found at {path}")
    with _make_beamline_client(path, "startup_scripts", tmp_path) as client:
        yield client


# Script-execution profiles (slower — exec's startup scripts in subprocess)
@pytest.fixture
def csx_client(tmp_path) -> TestClient:
    """CSX beamline — startup scripts with csx1 submodule."""
    path = BEAMLINE_PROFILES["csx"]
    if not path.exists():
        pytest.skip(f"csx-profile-collection not found at {path}")
    with _make_beamline_client(path, "startup_scripts", tmp_path) as client:
        yield client


@pytest.fixture
def iss_client(tmp_path) -> TestClient:
    """ISS beamline — 44 startup scripts, most complex pure-Python profile."""
    path = BEAMLINE_PROFILES["iss"]
    if not path.exists():
        pytest.skip(f"iss-profile-collection not found at {path}")
    with _make_beamline_client(path, "startup_scripts", tmp_path) as client:
        yield client


@pytest.fixture
def srx_client(tmp_path) -> TestClient:
    """SRX beamline — 59 startup scripts."""
    path = BEAMLINE_PROFILES["srx"]
    if not path.exists():
        pytest.skip(f"srx-profile-collection not found at {path}")
    with _make_beamline_client(path, "startup_scripts", tmp_path) as client:
        yield client


@pytest.fixture
def kreios_happi_client(kreios_happi_settings) -> TestClient:
    """Test client for KREIOS Happi format."""
    import warnings
    warnings.filterwarnings("ignore", category=UserWarning, module="ophyd")
    app = create_app(kreios_happi_settings)
    with TestClient(app) as client:
        yield client
