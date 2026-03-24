# Device Locking via Configuration Service — Design Proposal

## Status: Approved (2026-03-12)

## Problem

When Experiment Execution (SVC-001) runs a Bluesky plan, devices used by that
plan must be protected from concurrent direct-control commands. Currently, EE
manages device locks in its own in-memory state and Direct Control (SVC-003)
queries EE directly before every write operation.

This creates a split model: Configuration Service is the authority for device
metadata, instantiation specs, and enabled/disabled status, but lock state lives
in a completely separate service. Direct Control must know about and communicate
with both services to answer the simple question "can I use this device?"

## Proposal

Route all device locking through the Configuration Service so it becomes the
**single source of truth** for device availability — combining metadata,
enabled/disabled status, and lock state in one place.

### Current Architecture

```
EE (SVC-001)                    DC (SVC-003)
 ├── CoordinationManager         ├── CoordinationClient
 │   (in-memory locks)           │   queries EE for lock state
 │                               │
 │   POST plan starts ──────►   │   GET /coordination/devices/{name}/status
 │   locks acquired locally      │   ◄── {available, locked_by, ...}
 │                               │
 │   Plan completes ──────►     │
 │   locks released locally      │

Config Service (SVC-004)
 └── Device registry only (no lock awareness)
```

### Proposed Architecture

```
EE (SVC-001)                         Config Service (SVC-004)
 │                                    ├── Device registry (metadata + PV mappings)
 │  Plan starts                       ├── Enabled/disabled state
 │  ├── POST /api/v1/devices/lock ──► ├── Lock state (in-memory, device-level)
 │  │   {devices, item_id, plan}      ├── Audit log (lock/unlock events)
 │  │                                 │
 │  │  Plan executes...               │   DC (SVC-003)
 │  │                                 │    ├── GET /api/v1/pvs/{pv}/status
 │  │                                 │    │   Config resolves PV → device → lock
 │  │                                 │    │   ◄── {available, locked, enabled}
 │  │                                 │    │
 │  │                                 │    │  caput (only if available=true)
 │  │                                 │    │
 │  Plan completes/fails              │
 │  └── POST /api/v1/devices/unlock ► │
 │      {devices, item_id}            │
```

## New Endpoints on Configuration Service

### `POST /api/v1/devices/lock` — Bulk Atomic Lock

Acquire locks on multiple devices atomically (all-or-nothing). If any device is
already locked, unavailable, or disabled, the entire request fails and no locks
are acquired.

**Request:**
```json
{
  "device_names": ["sample_x", "det1"],
  "item_id": "550e8400-e29b-41d4-a716-446655440000",
  "plan_name": "count",
  "locked_by_service": "experiment_execution"
}
```

**Response (success):**
```json
{
  "success": true,
  "locked_devices": ["sample_x", "det1"],
  "locked_pvs": ["BL01:SAMPLE:X", "BL01:SAMPLE:X.RBV", "BL01:DET1:Value"],
  "lock_id": "a1b2c3d4-...",
  "registry_version": 42
}
```

**Response (conflict — device already locked):**
```json
{
  "success": false,
  "message": "Device 'sample_x' is locked by plan 'rel_scan'",
  "conflicting_devices": [
    {
      "device_name": "sample_x",
      "locked_by_plan": "rel_scan",
      "locked_at": "2026-03-11T14:58:00Z"
    }
  ]
}
```

**Status codes:**
- `200` — Locks acquired
- `409` — One or more devices already locked (none acquired)
- `404` — One or more devices not found in registry
- `422` — One or more devices are disabled

### `POST /api/v1/devices/unlock` — Bulk Unlock

Release locks on devices. Only the service/item that acquired the lock can
release it (unless force is used).

**Request:**
```json
{
  "device_names": ["sample_x", "det1"],
  "item_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response:**
```json
{
  "success": true,
  "unlocked_devices": ["sample_x", "det1"],
  "registry_version": 43
}
```

**Status codes:**
- `200` — Locks released
- `403` — Lock owned by a different item (use `force: true` to override)

### `POST /api/v1/devices/force-unlock` — Administrative Force Unlock

Emergency endpoint to clear stale locks (e.g., after EE crash). Clears all
locks regardless of ownership. Requires explicit intent.

**Request:**
```json
{
  "device_names": ["sample_x"],
  "reason": "EE crashed during rel_scan, clearing stale locks"
}
```

**Status codes:**
- `200` — Locks force-cleared
- `404` — Device not found

### `GET /api/v1/devices/{device_name}/status` — Device Availability

Combined availability check returning lock state, enabled/disabled, and
metadata in one call.

**Response:**
```json
{
  "device_name": "sample_x",
  "available": false,
  "enabled": true,
  "lock_status": "locked",
  "locked_by_plan": "count",
  "locked_by_item": "550e8400-e29b-41d4-a716-446655440000",
  "locked_at": "2026-03-11T15:00:00Z"
}
```

A device is `available: true` only when it is **both enabled and unlocked**.

**Status codes:**
- `200` — Status returned
- `404` — Device not found in registry

### `GET /api/v1/pvs/{pv_name}/status` — PV Availability

This is the primary endpoint Direct Control calls before every write operation
(e.g., `caput`). DC controls individual PVs, not whole devices, so it needs to
check availability at the PV level.

Config Service looks up which device owns the PV and returns that device's lock
and enabled state. Standalone PVs (not bound to any device) are always
available.

**Response (PV belongs to a locked device):**
```json
{
  "pv_name": "BL01:SAMPLE:X",
  "available": false,
  "device_name": "sample_x",
  "device_enabled": true,
  "device_lock_status": "locked",
  "locked_by_plan": "count",
  "locked_by_item": "550e8400-e29b-41d4-a716-446655440000",
  "locked_at": "2026-03-11T15:00:00Z"
}
```

**Response (standalone PV, no owning device):**
```json
{
  "pv_name": "BL01:RING:CURRENT",
  "available": true,
  "device_name": null,
  "device_enabled": null,
  "device_lock_status": null,
  "locked_by_plan": null,
  "locked_by_item": null,
  "locked_at": null
}
```

**Status codes:**
- `200` — Status returned
- `404` — PV not found in registry

## Lock State Storage

### In-Memory (Primary)

Lock state is **ephemeral** — it lives in the Configuration Service's in-memory
registry alongside device metadata. Locks are not persisted to SQLite because:

- Lock state is transient (seconds to hours, not permanent)
- On Config Service restart, all locks start cleared (clean slate)
- Persisting locks would risk stale locks surviving restarts

### Audit Log (SQLite)

Lock and unlock **events** are written to the existing `device_audit_log` table
for history and debugging:

```
| operation    | details                                              |
|-------------|------------------------------------------------------|
| lock        | {"plan": "count", "item_id": "...", "devices": [...]}|
| unlock      | {"plan": "count", "item_id": "...", "reason": "complete"} |
| force_unlock| {"reason": "EE crashed during rel_scan", "admin": true} |
```

### PV-Level Lock Propagation

When a device is locked, **all PVs belonging to that device** are implicitly
locked. Config Service already maintains the device → PV mapping in the
registry. The lock is stored at the device level; PV status checks resolve
the owning device and return its lock state.

This means DC does not need to know device names — it can check availability
using only the PV name it intends to `caput` to.

## Lock Lifecycle

Locks are trust-based with manual recovery for failure cases:

1. **Lock** — EE sends `POST /lock` before plan execution begins
2. **Hold** — Locks remain active for the duration of the plan (minutes to hours)
3. **Unlock** — EE sends `POST /unlock` when plan completes, fails, or is aborted
4. **Stale lock recovery** — If EE crashes mid-plan, an admin uses `POST /force-unlock`
   to clear orphaned locks

There is no TTL or heartbeat mechanism. Plans at synchrotron beamlines can run
for hours, and adding periodic keep-alive traffic between EE and Config Service
adds complexity without meaningful benefit. The force-unlock endpoint provides
a simple, explicit recovery path for the rare case of an EE crash.

## EE Process Model and Lock State Transitions

### Recommended EE Architecture

EE should adopt the proven three-process model from
[bluesky-queueserver](https://github.com/bluesky/bluesky-queueserver), which
was developed and iterated at real beamlines:

```
Watchdog (main process)
 │  monitors Manager heartbeat
 │  restarts Manager if unresponsive
 │
 └── RE Manager (child process)
      │  owns plan queue (persisted to SQLite)
      │  handles external API requests
      │  sends lock/unlock to Config Service
      │
      └── RE Worker (grandchild process)
           │  owns the Bluesky RunEngine
           │  executes plans
           │  isolated: crashes don't affect Manager
```

**Why this matters for locking**: The Manager survives Worker crashes and can
always send `POST /unlock` to Config Service to release device locks. Only a
full crash of all three processes requires admin intervention via force-unlock.

### Plan Interruption Options

EE supports these interruption modes (matching bluesky-queueserver):

| Action | Description |
|--------|-------------|
| **Pause (deferred)** | Plan pauses at the next checkpoint (safe stopping point) |
| **Pause (immediate)** | Plan pauses immediately |
| **Resume** | Continues a paused plan from where it stopped |
| **Stop** | Gracefully ends a paused plan (treated as successful completion) |
| **Abort** | Fails a paused plan (plan is marked as aborted) |
| **Halt** | Fails a paused plan, RE enters "panicked" state (most severe) |

### Lock State per EE Event

The critical question: what happens to device locks in Config Service for each
EE state transition?

| EE Event | Lock Action | Config Service Call | Rationale |
|----------|-------------|-------------------|-----------|
| Plan starts | **Lock** | `POST /lock` | Acquire devices before RunEngine starts |
| Pause (deferred) | *Held — no change* | — | Plan is suspended, not finished; will resume. Devices still owned by plan. |
| Pause (immediate) | *Held — no change* | — | Same as deferred pause. |
| Resume | *Held — no change* | — | Locks were already held through pause. |
| Stop | **Unlock** | `POST /unlock` | Plan gracefully completed. Devices released. |
| Abort | **Unlock** | `POST /unlock` | Plan failed/aborted. No longer running. |
| Halt | **Unlock** | `POST /unlock` | Plan failed, RE panicked. Devices released. |
| Worker crash | **Unlock** | Manager sends `POST /unlock` | Manager detects crash, cleans up locks. |
| Manager crash | **Unlock** | Watchdog restarts Manager; Manager recovers queue state and sends `POST /unlock` | Manager knows which item was running from persisted queue state. |
| Full crash (all 3) | **Force-unlock** | Admin sends `POST /force-unlock` | Manual recovery for catastrophic failure. |

### Why Locks Are Held During Pause

When a plan is paused (deferred or immediate), devices **stay locked** because:

1. **The plan still owns those devices.** A paused scan at step 47 of 100 will
   resume and expects the hardware to be where it left it.
2. **DC write commands could corrupt the experiment.** If DC moves a motor while
   a scan is paused, resuming the plan produces invalid data — the motor position
   no longer matches the scan trajectory.
3. **Reads are already allowed.** DC read operations (`caget`) skip lock checks,
   so operators can still monitor PV values during a paused plan.
4. **Operators who need to intervene have options.** They can `stop` or `abort`
   the plan (which unlocks devices), then use DC freely.

### Recovery Scenarios

**Worker crashes mid-plan:**
```
1. Worker dies unexpectedly
2. Manager detects unexpected_shutdown in status poll (every 0.5s)
3. Manager marks plan as failed in queue
4. Manager sends POST /unlock to Config Service → devices released
5. Manager can spawn new Worker when environment is re-opened
```

**Manager crashes mid-plan:**
```
1. Manager stops sending heartbeats
2. Watchdog detects timeout (5s), kills Manager, spawns new one
3. New Manager loads queue state from SQLite
4. New Manager sees interrupted plan, marks it failed
5. New Manager sends POST /unlock to Config Service → devices released
```

**Config Service restarts while plan is running:**
```
1. Config Service restarts with clean in-memory state (no locks)
2. EE plan continues executing (lock/unlock only at start/end)
3. DC can now command devices (no locks to check) — RISK
4. When plan ends, EE sends POST /unlock — Config returns success (no-op)
5. Mitigation: DC should treat Config Service unavailability as "locked"
   (fail-safe), and EE should re-lock devices if it detects Config restart
   via registry_version reset
```

## Changes Per Service

### Configuration Service (SVC-004)

| Change | Description |
|--------|-------------|
| New models | `DeviceLockRequest`, `DeviceLockResponse`, `DeviceLockState`, `DeviceStatus`, `PVStatus` |
| New endpoints | `POST /lock`, `POST /unlock`, `POST /force-unlock`, `GET /devices/{name}/status`, `GET /pvs/{name}/status` |
| Registry update | `DeviceRegistry` gains per-device lock state fields |
| PV lookup | Status check resolves PV → owning device → lock state |
| Audit log | Lock/unlock/force-unlock events written to existing audit table |

### Experiment Execution (SVC-001)

| Change | Description |
|--------|-------------|
| Process model | Adopt Watchdog → Manager → Worker architecture (from bluesky-queueserver) |
| CoordinationManager | Manager sends lock/unlock HTTP calls to Config Service (not local state) |
| Lock acquisition | Manager calls `POST /api/v1/devices/lock` before dispatching plan to Worker |
| Lock release | Manager calls `POST /api/v1/devices/unlock` on plan completion, failure, abort, halt, or Worker crash |
| Plan interruption | Support pause (deferred/immediate), resume, stop, abort, halt |
| Queue persistence | SQLite for queue state; no external dependencies, enables lock recovery after Manager restart |
| Remove endpoints | `/api/v1/coordination/*` endpoints removed (Config Service owns lock state) |
| Config | New setting: `config_service_url` for lock operations |

### Direct Control (SVC-003)

| Change | Description |
|--------|-------------|
| CoordinationClient | Target changes from SVC-001 to SVC-004 |
| Endpoint | Checks `GET /api/v1/pvs/{pv_name}/status` before each `caput` |
| Config | `experiment_execution_url` → `configuration_service_url` for coordination |
| Response handling | Parse new combined response (available = enabled AND unlocked) |

## Benefits

1. **Single source of truth** — Config Service owns all device state: metadata,
   instantiation specs, enabled/disabled, and lock status
2. **PV-level availability** — DC checks a single PV name and gets back the
   owning device's full availability state; no need to know device names
3. **Simplified DC** — Direct Control queries one service for "can I use this
   PV?" instead of two
4. **Unified audit trail** — Lock/unlock events sit alongside device add/update/
   delete/enable/disable in the same history
5. **Combined availability** — `available = enabled AND unlocked` in one check,
   preventing edge cases where a disabled device could still be "available" per
   the coordination check

## Authentication and Authorization

All three core services (Config Service, EE, DC) sit behind HAProxy which
handles authentication. Authorization is enforced in FastAPI middleware within
each service.

### AuthN (HAProxy)

HAProxy verifies user/service identity and injects headers:

```
X-Remote-User: tom
X-Remote-Groups: staff_scientist
X-Remote-Email: tom@facility.org
```

Services trust these headers because HAProxy is the only ingress path.

### AuthZ (Middleware)

FastAPI middleware reads the HAProxy headers and enforces per-endpoint
permissions:

| Endpoint | Required Permission | Typical Caller |
|----------|-------------------|----------------|
| `GET /api/v1/devices/{name}/status` | Any authenticated user | DC, UI |
| `GET /api/v1/pvs/{name}/status` | Any authenticated user | DC (before `caput`) |
| `POST /api/v1/devices/lock` | `EXECUTE_PLAN` | EE service account |
| `POST /api/v1/devices/unlock` | `EXECUTE_PLAN` | EE service account |
| `POST /api/v1/devices/force-unlock` | `ADMIN` | Admin only |

This is the same AuthZ pattern used for all device and PV CRUD operations:

| Operation | Required Permission |
|-----------|-------------------|
| Read endpoints (GET) | Any authenticated user |
| Device/PV CRUD (POST/PUT/DELETE) | `MODIFY_REGISTRY` |
| Enable/disable devices | `MODIFY_REGISTRY` |

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Config Service becomes critical path for plan execution | Already critical for device instantiation; adding lock ops doesn't change the dependency graph |
| Added latency on lock acquisition | Lock/unlock are one-time operations per plan (at start/end), not per-step; negligible impact |
| Config Service crash clears locks | Acceptable: if Config Service is down, DC can't check availability anyway; EE should pause/abort plans if Config Service is unreachable |
| EE crash leaves orphaned locks | Admin uses `POST /force-unlock` to clear stale locks; rare failure case doesn't justify TTL/heartbeat complexity |
| Network partition between EE and Config | Lock/unlock only happens at plan start/end; brief network issues during plan execution don't affect held locks |

## Resolved Questions

1. **Force-unlock authorization** — Requires `ADMIN` role via HAProxy/middleware
   AuthZ. Same pattern as all other endpoints.
2. **AuthN/AuthZ approach** — HAProxy handles AuthN, FastAPI middleware handles
   AuthZ. No dependency on the Auth Service (SVC-010).
3. **TTL/heartbeat** — Not needed. Locks are held for the duration of the plan
   (which can be hours). If EE crashes, admin uses force-unlock. Simpler and
   sufficient for the failure mode.
4. **PV-level locking** — DC primarily uses `caput` on individual PVs, so a
   `GET /pvs/{name}/status` endpoint resolves PV → owning device → lock state.
   Locking a device implicitly locks all its PVs.

## Open Questions

1. **Should DC also be able to query bulk lock status?** (e.g., `GET /api/v1/devices/locks`
   to show all currently locked devices in a UI)
2. **Should lock state be included in the existing `GET /api/v1/devices/{name}`
   response?** Or keep it separate via the `/status` endpoint?
