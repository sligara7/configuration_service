# Configuration Service — Feature Comparison

How the Bluesky Remote Architecture Configuration Service compares to
existing open-source projects that expose device configuration over a
network interface.

## Systems Compared

| Project | Maintainer | Purpose |
|---------|-----------|---------|
| **Configuration Service** (this project) | Bluesky Remote Architecture | Full device registry with metadata, PV mappings, instantiation specs, runtime CRUD, and protocol detection — exposed as a REST API. |
| **ophyd-websocket** | ALS (Advanced Light Source) | WebSocket bridge exposing live ophyd device trees to web UIs. |
| **blueapi** | Diamond Light Source | REST interface to the Bluesky RunEngine; includes device listing with protocol-based typing. |
| **bluesky-queueserver** | NSLS-II / Bluesky | Queue-based plan execution server; generates `existing_plans_and_devices.yaml` with device capability flags. |
| **as-ophyd-api** | Australian Synchrotron | REST API over ophyd devices; supports class-based filtering and component introspection. |

## Feature Comparison

| Feature | Config Service | ophyd-websocket | blueapi | bluesky-queueserver | as-ophyd-api |
|---------|:-:|:-:|:-:|:-:|:-:|
| **List devices** | Y | Y | Y | Y | Y |
| **Get device metadata** | Y | Y | Y | Y | Y |
| **List device classes** | Y | — | — | — | Y |
| **List device types** | Y | — | Y | — | — |
| **Filter by device type** | Y | — | Y | — | — |
| **Filter by ophyd_class** | Y | — | — | — | Y |
| **Filter by glob pattern** | Y | — | — | — | — |
| **Filter by labels** | Y | — | — | — | — |
| **Protocol flags: movable, flyable, readable** | Y | — | Y | Y | — |
| **Protocol flags: triggerable, stageable, configurable, pausable, stoppable, subscribable, checkable, writes_external_assets** | Y | — | Y | — | — |
| **PV mapping per device** | Y | Y | — | — | Y |
| **PV search (glob)** | Y | — | — | — | — |
| **PV metadata (dtype, units, limits)** | Y | Y | — | — | Y |
| **Nested component tree** | Y | Y | — | — | Y |
| **Component depth control** | Y | — | — | — | — |
| **Device instantiation specs** | Y | — | — | — | — |
| **Runtime device CRUD** | Y | — | — | — | — |
| **Persistent change history (survives restart)** | Y | — | — | — | — |
| **Shared cache with version** | Y | — | — | — | — |
| **Multiple profile formats (startup scripts, happi, BITS, mock)** | Y | — | — | Y (startup scripts) | — |
| **Auto-detect profile format** | Y | — | — | — | — |
| **Hints for plotting** | Y | — | — | Y | — |
| **Happi metadata (beamline, location, functional group)** | Y | — | — | — | — |
| **OpenAPI / REST** | Y | — (WebSocket) | Y | Y (via HTTP API) | Y |

## Summary

The Configuration Service encapsulates every configuration-related feature
found across the four comparison projects:

- **From ophyd-websocket**: device trees, PV mappings, nested component
  traversal, PV metadata.
- **From blueapi**: device protocol typing with the full union of Bluesky
  protocol interfaces (Triggerable, Stageable, Configurable, Pausable,
  Stoppable, Subscribable, Checkable, writes-external-assets).
- **From bluesky-queueserver**: `existing_plans_and_devices.yaml`
  compatibility, capability flags (is_movable, is_flyable, is_readable),
  startup-script loading.
- **From as-ophyd-api**: class-based filtering, component introspection,
  device class listing.

It also adds capabilities not present in any of the compared projects:
runtime device CRUD with persistent change history, shared instantiation-spec
cache with version tracking, multi-format profile loading with
auto-detection, glob-based PV search, label-based filtering, and
component depth control.
