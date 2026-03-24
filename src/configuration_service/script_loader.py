"""
Script Execution Loader for Configuration Service (SVC-004).

Exec's IPython-style startup scripts into a namespace, introspects live
device objects using bluesky.protocols, and populates a DeviceRegistry.
This is ported from the queueserver ``qserver-list-plans-devices`` pattern
(bluesky_queueserver.manager.profile_ops) and adapted for the config service.

Requires optional dependencies: ophyd, bluesky.
Install with: pip install bluesky-configuration-service[scripts]

The loader runs startup scripts in a subprocess to isolate sys.path
pollution, environment variable changes, and imported modules from the
main service process.
"""

import glob
import inspect
import logging
import multiprocessing
import multiprocessing.connection
import os
import re
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    DeviceInstantiationSpec,
    DeviceMetadata,
    DeviceRegistry,
    DeviceLabel,
)

logger = logging.getLogger(__name__)


# ── IPython patch (ported from queueserver profile_ops.py:210) ───────────

_startup_script_patch = """
import sys
import logging
import builtins

_qs_logger_patch = logging.getLogger(__name__)

class _NullObj:
    '''Catch-all object that absorbs any attribute access or call.'''
    _is_ipython_mock = True
    def __repr__(self): return '_NullObj()'
    def __bool__(self): return False
    def __iter__(self): return iter([])
    def __getattr__(self, name): return _NullObj()
    def __call__(self, *a, **kw): return _NullObj()
    def __setattr__(self, name, value): pass

class _IPDummy:
    '''IPython shell mock for running startup scripts outside IPython.

    Provides enough of the IPython InteractiveShell interface to let
    nslsii.configure_base() and similar beamline setup code run without
    crashing.  Unknown attribute access returns a _NullObj that silently
    absorbs further calls/attribute access.
    '''
    _is_ipython_mock = True
    execution_count = 0

    def __init__(self, user_ns):
        object.__setattr__(self, '_user_ns', user_ns)
        object.__setattr__(self, 'user_ns', user_ns)
        object.__setattr__(self, 'log', logging.getLogger('ipython_patch'))

    def __getattr__(self, name):
        return _NullObj()

    def run_line_magic(self, *args, **kwargs):
        pass

    def run_cell_magic(self, *args, **kwargs):
        pass

    def register_magics(self, *args, **kwargs):
        pass

    def register_magic_function(self, *args, **kwargs):
        pass

_ip_dummy_instance = _IPDummy(globals())

def get_ipython():
    return _ip_dummy_instance

# Monkey-patch IPython so that 'from IPython import get_ipython' also
# returns our dummy.  This is critical for libraries like nslsii that
# call get_ipython() from within their own modules.
try:
    import IPython as _IPython_mod
    import IPython.core.getipython as _ip_getter
    _ip_getter.get_ipython = get_ipython
    _IPython_mod.get_ipython = get_ipython
except ImportError:
    pass

builtins.get_ipython = get_ipython
"""


def _patch_script_code(code_str: str) -> str:
    """
    Patch script code to redirect ``get_ipython`` imports to our dummy.

    Detects lines that import ``get_ipython`` from ``IPython`` and appends
    ``get_ipython = get_ipython`` (the patched version already in namespace)
    after each import.

    Ported from queueserver profile_ops.py:233.
    """

    def _has_get_ipython_import(line: str) -> bool:
        return bool(re.search(r"^[^#]*IPython[^#]+get_ipython", line))

    lines = code_str.splitlines()
    for i, line in enumerate(lines):
        if _has_get_ipython_import(line):
            parts = re.split("#", line)
            if parts[0].strip():
                patched = parts[0] + "; get_ipython = get_ipython"
                if len(parts) > 1:
                    patched += "  #" + "#".join(parts[1:])
                lines[i] = patched

    return "\n".join(lines)


def load_profile_collection(
    path: str,
    *,
    patch_profiles: bool = True,
    ignore_errors: bool = False,
) -> dict:
    """
    Exec startup scripts (``*.py`` / ``*.ipy``) in sorted order into a
    shared namespace dict.

    Ported from queueserver profile_ops.py:261.

    Parameters
    ----------
    path : str
        Path to the directory containing startup scripts.
    patch_profiles : bool
        If True, inject the IPython get_ipython() patch before loading.
    ignore_errors : bool
        If True, log errors from individual scripts and continue loading
        subsequent files instead of aborting.  This is useful when running
        beamline profiles off-site where infrastructure (Redis, Kafka,
        EPICS IOCs, …) is unavailable — the device definitions in later
        scripts can still be collected.

    Returns
    -------
    dict
        The namespace populated by executing all scripts.
    """
    path = os.path.expanduser(path)
    path = os.path.abspath(path)

    if not os.path.exists(path):
        raise IOError(f"Path '{path}' does not exist.")
    if not os.path.isdir(path):
        raise IOError(f"Path '{path}' is not a directory.")

    file_list = sorted(
        glob.glob(os.path.join(path, "*.py"))
        + glob.glob(os.path.join(path, "*.ipy"))
    )

    if not file_list:
        raise IOError(
            f"The directory '{path}' contains no startup files (*.py / *.ipy)."
        )

    # Temporarily add path for local imports within the startup scripts
    path_added = path not in sys.path
    if path_added:
        sys.path.insert(0, path)

    nspace: dict = {}
    failed_scripts: List[str] = []
    try:
        if patch_profiles:
            exec(_startup_script_patch, nspace, nspace)

        for fpath in file_list:
            logger.info("Loading startup file '%s' ...", fpath)
            try:
                nspace["__file__"] = fpath
                nspace["__name__"] = "__main__"

                if not os.path.isfile(fpath):
                    raise IOError(f"Startup file {fpath!r} was not found")

                with open(fpath) as f:
                    code_str = f.read()
                code_str = _patch_script_code(code_str)
                code = compile(code_str, fpath, "exec")
                exec(code, nspace, nspace)

            except Exception as exc:
                msg = f"Error while executing script {fpath!r}: {exc}"
                tb_str = traceback.format_exc()
                if ignore_errors:
                    logger.warning("%s\n%s", msg, tb_str)
                    failed_scripts.append(os.path.basename(fpath))
                else:
                    logger.error("%s\n%s", msg, tb_str)
                    raise RuntimeError(msg) from exc
            finally:
                nspace.pop("__file__", None)

    finally:
        if path_added:
            try:
                sys.path.remove(path)
            except ValueError:
                pass

    if failed_scripts:
        logger.warning(
            "Completed with %d failed script(s): %s",
            len(failed_scripts),
            ", ".join(failed_scripts),
        )

    return nspace


# ── Device detection (ported from queueserver profile_ops.py:676) ────────

def is_device(obj: Any) -> bool:
    """
    Return True if *obj* is a live device instance.

    Checks for ``bluesky.protocols.Readable`` / ``Flyable`` or the
    ``children`` attribute (ophyd-async devices). Excludes classes and
    internal mock objects.

    Ported from queueserver profile_ops.py:676.
    """
    if inspect.isclass(obj):
        return False

    # Exclude our internal IPython/NullObj mocks
    if getattr(obj, "_is_ipython_mock", False):
        return False

    try:
        from bluesky.protocols import Flyable, Readable
    except ImportError:
        # If bluesky isn't installed, fall back to duck-typing
        return hasattr(obj, "read") and hasattr(obj, "describe")

    return isinstance(obj, (Readable, Flyable)) or hasattr(obj, "children")


def devices_from_nspace(nspace: dict) -> Dict[str, Any]:
    """
    Extract device objects from a namespace dict.

    Ported from queueserver profile_ops.py:747.

    Parameters
    ----------
    nspace : dict
        Namespace populated by load_profile_collection().

    Returns
    -------
    dict
        Mapping of device name -> device object.
    """
    devices = {}
    for name, obj in nspace.items():
        if name.startswith("_"):
            continue
        try:
            if is_device(obj):
                devices[name] = obj
        except Exception:
            # Some namespace objects may error on attribute access
            pass
    return devices


# ── Device introspection (config-service specific) ───────────────────────

def _infer_device_label_from_obj(obj: Any) -> DeviceLabel:
    """Infer DeviceLabel from a live device object using class name and protocols."""
    cls_name = type(obj).__name__.lower()

    if "motor" in cls_name or "axis" in cls_name or "positioner" in cls_name:
        return DeviceLabel.MOTOR
    if "det" in cls_name or "area" in cls_name or "camera" in cls_name:
        return DeviceLabel.DETECTOR
    if "signal" in cls_name:
        return DeviceLabel.SIGNAL
    if "fly" in cls_name:
        return DeviceLabel.FLYER

    # Fall back to protocol checks
    try:
        from bluesky.protocols import Flyable, Movable, Readable
        if isinstance(obj, Movable):
            return DeviceLabel.MOTOR
        if isinstance(obj, Flyable):
            return DeviceLabel.FLYER
        if isinstance(obj, Readable):
            return DeviceLabel.READABLE
    except ImportError:
        pass

    return DeviceLabel.DEVICE


def _extract_pvs(obj: Any) -> Dict[str, str]:
    """Extract PV names from a live ophyd device, best-effort."""
    pvs: Dict[str, str] = {}
    try:
        # ophyd v1 devices have .component_names
        for comp_name in getattr(obj, "component_names", ()):
            comp = getattr(obj, comp_name, None)
            if comp is None:
                continue
            pv = getattr(comp, "pvname", None)
            if pv:
                pvs[comp_name] = pv
    except Exception:
        pass

    # Fall back: check for a top-level prefix
    if not pvs:
        prefix = getattr(obj, "prefix", None)
        if prefix and isinstance(prefix, str):
            pvs["prefix"] = prefix

    return pvs


def _extract_labels(obj: Any) -> List[str]:
    """Extract labels from a device, handling ophyd v1 label sets."""
    raw = getattr(obj, "_ophyd_labels_", None)
    if raw is None:
        return []
    if isinstance(raw, set):
        return sorted(raw)
    if isinstance(raw, (list, tuple)):
        return list(raw)
    return []


def _device_to_metadata(name: str, device: Any) -> DeviceMetadata:
    """Convert a live device object to DeviceMetadata."""
    cls = type(device)
    cls_name = cls.__name__
    module = cls.__module__

    # Protocol capability checks
    def _check(proto_name: str) -> bool:
        try:
            import bluesky.protocols as bp
            proto = getattr(bp, proto_name, None)
            if proto is not None:
                return isinstance(device, proto)
        except ImportError:
            pass
        return False

    is_readable = _check("Readable") or hasattr(device, "read")
    is_movable = _check("Movable") or hasattr(device, "set")
    is_flyable = _check("Flyable") or (hasattr(device, "kickoff") and hasattr(device, "complete"))
    is_triggerable = _check("Triggerable") or hasattr(device, "trigger")
    is_stageable = _check("Stageable") or (hasattr(device, "stage") and hasattr(device, "unstage"))
    is_configurable = _check("Configurable") or hasattr(device, "read_configuration")
    is_pausable = _check("Pausable") or (hasattr(device, "pause") and hasattr(device, "resume"))
    is_stoppable = _check("Stoppable") or hasattr(device, "stop")
    is_subscribable = _check("Subscribable") or hasattr(device, "subscribe")
    is_checkable = _check("Checkable") or hasattr(device, "check_value")
    writes_external = _check("WritesExternalAssets") or hasattr(device, "collect_asset_docs")

    pvs = _extract_pvs(device)
    labels = _extract_labels(device)
    device_label = _infer_device_label_from_obj(device)

    # Read/config attrs and hints (ophyd v1)
    read_attrs = list(getattr(device, "read_attrs", []) or [])
    config_attrs = list(getattr(device, "configuration_attrs", []) or [])
    hints = None
    raw_hints = getattr(device, "hints", None)
    if raw_hints is not None:
        # ophyd hints is a property returning a dict
        try:
            hints = dict(raw_hints) if isinstance(raw_hints, dict) else None
        except Exception:
            pass

    return DeviceMetadata(
        name=name,
        device_label=device_label,
        ophyd_class=cls_name,
        module=module,
        is_movable=is_movable,
        is_flyable=is_flyable,
        is_readable=is_readable,
        is_triggerable=is_triggerable,
        is_stageable=is_stageable,
        is_configurable=is_configurable,
        is_pausable=is_pausable,
        is_stoppable=is_stoppable,
        is_subscribable=is_subscribable,
        is_checkable=is_checkable,
        writes_external_assets=writes_external,
        pvs=pvs,
        hints=hints,
        read_attrs=read_attrs,
        configuration_attrs=config_attrs,
        labels=labels,
    )


def _device_to_instantiation_spec(
    name: str, device: Any, profile_path: str
) -> DeviceInstantiationSpec:
    """Extract DeviceInstantiationSpec from a live device."""
    cls = type(device)
    device_class = f"{cls.__module__}.{cls.__name__}"

    # Try to extract prefix (common ophyd v1 pattern)
    prefix = getattr(device, "prefix", None)
    args: List[Any] = []
    if prefix and isinstance(prefix, str):
        args = [prefix]

    kwargs: Dict[str, Any] = {"name": name}

    return DeviceInstantiationSpec(
        name=name,
        device_class=device_class,
        args=args,
        kwargs=kwargs,
        active=True,
    )


# ── Subprocess worker ────────────────────────────────────────────────────

def _worker(
    startup_dir: str,
    profile_path: str,
    conn: multiprocessing.connection.Connection,
) -> None:
    """
    Subprocess target: exec startup scripts, introspect devices, send
    serialised DeviceRegistry back through the pipe.

    Runs in a child process to isolate sys.path / env var / module side-effects.
    """
    # Redirect stdout to devnull to prevent colorama/terminal escape
    # issues in the headless subprocess.  Startup scripts that print
    # (e.g., terminal title escape sequences) would otherwise crash
    # colorama when there is no real terminal attached.  All real
    # results go back through the pipe; stderr is kept for logging.
    sys.stdout = open(os.devnull, "w")
    os.environ["NO_COLOR"] = "1"
    os.environ["TERM"] = "dumb"

    try:
        nspace = load_profile_collection(startup_dir, ignore_errors=True)
        devices = devices_from_nspace(nspace)

        registry = DeviceRegistry()
        for name, dev_obj in devices.items():
            try:
                metadata = _device_to_metadata(name, dev_obj)
                spec = _device_to_instantiation_spec(name, dev_obj, profile_path)
                registry.add_device(metadata, spec)
            except Exception as exc:
                # Log but don't fail the whole load for one bad device
                logger.warning("Failed to introspect device %r: %s", name, exc)

        # Serialise as JSON-compatible dict for pipe transfer
        conn.send(("ok", registry.model_dump()))

    except Exception as exc:
        tb_str = traceback.format_exc()
        conn.send(("error", f"{exc}\n{tb_str}"))
    finally:
        conn.close()


# ── ScriptExecutionLoader ────────────────────────────────────────────────

class ScriptExecutionLoader:
    """
    Load devices by exec'ing IPython-style startup scripts in a subprocess.

    This follows the queueserver ``GenLists`` pattern: startup scripts are
    executed in a child process (isolating sys.path, env vars, and imported
    modules), then devices are introspected from the resulting namespace.

    Requires: ophyd, bluesky (install with ``pip install .[scripts]``).
    """

    def __init__(self, profile_path: Path):
        self.profile_path = Path(profile_path)
        self.startup_dir = self._find_startup_dir()

        if not self.startup_dir:
            raise ValueError(
                f"No startup scripts found in {self.profile_path}. "
                f"Expected *.py files in a 'startup/' subdirectory or "
                f"in the profile directory itself."
            )

        # Verify ophyd/bluesky are importable (fail fast with clear message)
        self._check_dependencies()

    def _find_startup_dir(self) -> Optional[Path]:
        """Locate the directory containing startup scripts."""
        # Check startup/ subdirectory first (standard IPython profile layout)
        startup = self.profile_path / "startup"
        if startup.is_dir() and list(startup.glob("*.py")):
            return startup

        # Fall back to profile root
        if list(self.profile_path.glob("*.py")):
            return self.profile_path

        return None

    def _check_dependencies(self) -> None:
        """Verify that ophyd and bluesky are importable."""
        missing = []
        try:
            import ophyd  # noqa: F401
        except ImportError:
            missing.append("ophyd>=1.9.0")
        try:
            import bluesky.protocols  # noqa: F401
        except ImportError:
            missing.append("bluesky>=1.12.0")

        if missing:
            raise ImportError(
                f"Script execution loader requires: {', '.join(missing)}. "
                f"Install with: pip install bluesky-configuration-service[scripts]"
            )

    def load_registry(self) -> DeviceRegistry:
        """
        Load device registry by executing startup scripts in a subprocess.

        Returns
        -------
        DeviceRegistry
            Registry populated with devices found in the startup scripts.
        """
        logger.info(
            "Loading device registry via script execution from %s",
            self.startup_dir,
        )

        parent_conn, child_conn = multiprocessing.Pipe()

        proc = multiprocessing.Process(
            target=_worker,
            args=(str(self.startup_dir), str(self.profile_path), child_conn),
            daemon=True,
        )
        proc.start()
        child_conn.close()  # Close child end in parent

        # Wait for result (timeout after 5 minutes for large profiles)
        timeout = 300
        if parent_conn.poll(timeout):
            status, payload = parent_conn.recv()
        else:
            proc.kill()
            proc.join(timeout=5)
            raise RuntimeError(
                f"Script execution timed out after {timeout}s "
                f"loading {self.startup_dir}"
            )

        proc.join(timeout=10)
        parent_conn.close()

        if status == "error":
            raise RuntimeError(
                f"Script execution failed for {self.startup_dir}:\n{payload}"
            )

        registry = DeviceRegistry.model_validate(payload)
        logger.info(
            "Loaded %d devices, %d PVs via script execution from %s",
            len(registry.devices),
            len(registry.pvs),
            self.startup_dir,
        )
        return registry
