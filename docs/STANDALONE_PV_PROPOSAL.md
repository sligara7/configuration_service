# Standalone PV Registration Proposal

**Status:** Awaiting feedback
**Date:** 2026-02-12

## Problem Statement

The Configuration Service is the single source of truth for devices and PVs. Currently, the PV universe is bounded by what is defined as ophyd/ophyd-async devices — either from the profile-collection or runtime-added via the device CRUD endpoints.

Any PV that exists on the beamline network (EPICS IOCs, etc.) but is not wrapped in an ophyd device is invisible to the entire architecture. Downstream services (Direct Control, Device Monitoring, Image Streaming) can only interact with PVs that are registered as part of a device.

At a real beamline, there are often hundreds of infrastructure PVs that operators need to monitor or control but are not part of the experiment's device definitions:

- **Facility PVs** — ring current, beam position, fill pattern
- **Beamline infrastructure** — shutter status, vacuum gauges, temperature sensors, interlocks
- **Diagnostic PVs** — beam loss monitors, BPMs
- **Ad-hoc PVs** — a technician wants to quickly monitor a PV during troubleshooting

## Current State

### Device CRUD Endpoints

The Configuration Service has CRUD endpoints that operate at the **device level**:

- `POST /api/v1/devices` — create a device (DeviceMetadata + DeviceInstantiationSpec)
- `PUT /api/v1/devices/{name}` — update entire device metadata/spec
- `DELETE /api/v1/devices/{name}` — remove a device

PVs are an attribute of a device (`DeviceMetadata.pvs` dict), not independently manageable entities. To add a single PV, you must create or update an entire ophyd device definition — heavyweight for "just let me watch this one PV."

### PV Read Endpoints (read-only)

- `GET /api/v1/pvs` — list PVs (derived from device registry)
- `GET /api/v1/pvs/{pv_name}` — get PV metadata

These are lookups into the registry's PV index, which is populated from device metadata.

## Key Concern: Access Control

Not all PVs should be controllable by all users. The RBAC system in the Auth Service exists specifically for this kind of access control.

### Proposed Permission Model

| PV Category | Example | Who can monitor | Who can command |
|---|---|---|---|
| Experiment devices | `SIM:MOTOR:X` | experiment user, staff | experiment user (via plans), staff |
| Beamline infrastructure | `BL:SHUTTER:01` | staff, experiment user (read-only) | staff only |
| Facility | `SR:CURRENT` | everyone (read-only) | nobody (external) |
| Diagnostic/ad-hoc | `DIAG:BPM:01` | staff | staff |

Regular experiment users should be limited to their experiment's devices (defined in the profile). Beamline staff/operators need access to infrastructure PVs (shutters, valves, etc.). The RBAC resource model would need to support PV-level or PV-group-level permissions, extending from the current device-level `"resource": "devices"`.

## Proposed Approach

### Lightweight PV Registration

Add a way to register standalone PVs without requiring a full ophyd device definition. A standalone PV entry would need at minimum:

- **PV name** (e.g., `BL:SHUTTER:01:STATUS`)
- **Protocol** (Channel Access, pvAccess)
- **Labels/groups** for RBAC mapping (e.g., `["beamline-infrastructure"]`)
- **Access mode** (read-only, read-write)
- **Description** (human-readable purpose)

### Integration with Existing Architecture

1. **Configuration Service** — registers standalone PVs with classification (labels/permission groups), persists them alongside device change history
2. **Auth Service** — gates access based on role + PV labels using existing RBAC framework
3. **Direct Control / Device Monitoring** — checks both PV existence (from Configuration Service) and user permissions (from Auth Service) before allowing operations

### Leveraging Existing Patterns

- The `labels` field already exists on `DeviceMetadata` and could serve as the grouping mechanism for RBAC
- The `DeviceChangeHistory` pattern (SQLite persistence, survive restarts) could be reused for standalone PV storage
- The device CRUD auth dependency (`require_modify_registry_or_anonymous`) already demonstrates the auth check pattern

## Open Questions

1. Should standalone PVs be a new resource type, or modeled as a minimal "virtual device" with a single PV?
2. What RBAC permissions are needed beyond the existing `MODIFY_REGISTRY`? (e.g., `MONITOR_INFRASTRUCTURE`, `CONTROL_INFRASTRUCTURE`)
3. Should there be a PV discovery endpoint that scans the EPICS network, or is manual registration sufficient?
4. How should standalone PVs interact with the cache version mechanism used by downstream services?
5. Should the Image Streaming service also support standalone PVs (e.g., area detector PVs not tied to an ophyd device)?

## Next Steps

Awaiting feedback before proceeding with implementation.
