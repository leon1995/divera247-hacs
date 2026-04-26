# DIVERA 24/7 for Home Assistant

Home Assistant custom integration for [DIVERA 24/7](https://www.divera247.com/),
built on top of the async [`divera247`](https://github.com/leon1995/divera247)
Python client.

The integration is intentionally read-first: it polls your personal account
(via a single `access_key`), surfaces the data you care about as sensors and
binary sensors, and offers one write-action -- changing your own user status.

## Installation

### Via HACS (recommended)

1. In HACS, open _Integrations_ → _⋮_ → _Custom repositories_.
2. Add this repository's URL with category _Integration_.
3. Search for **DIVERA 24/7**, install, and restart Home Assistant.
4. Go to _Settings_ → _Devices & services_ → _Add integration_ → **DIVERA 24/7**.

### Manual

Copy the `custom_components/divera247` folder into your Home Assistant
`config/custom_components` directory and restart Home Assistant.

## Configuration

The integration is configured entirely through the UI. You only need your
personal **Access Key**, which you can find in the DIVERA web app under
_User profile → API_.

Only the Access Key auth flow is exposed in the UI -- it is the simplest way
to authenticate and works for both REST and WebSocket endpoints of the DIVERA
API.

## What you get

### Device

A single device per configured Access Key, named after the owning user.

### Sensors

| Entity | Description |
| --- | --- |
| `sensor.<user>_status` | Current user status (name); attributes include raw `status_id`, note and vehicle ID |
| `sensor.<user>_status_changed` | Timestamp of the last status change |
| `sensor.<user>_new_alarms` | Counter: number of new alarms in the pull payload |
| `sensor.<user>_new_messages` | Counter: number of new messages |
| `sensor.<user>_latest_alarm` | Headline (_Stichwort_) of the most recent alarm |
| `sensor.<user>_user` | Full name (disabled by default) |
| `sensor.<user>_unit` | Configured unit/cluster name (disabled by default) |

### Binary sensors

| Entity | Description |
| --- | --- |
| `binary_sensor.<user>_active_alarm` | On while at least one alarm is open |
| `binary_sensor.<user>_unread_alarm` | On while any alarm is flagged as new (disabled by default) |

### Controls

| Entity | Description |
| --- | --- |
| `select.<user>_status` | Dropdown of visible DIVERA statuses; selecting one calls `statusgeber/set-status` |

### Services

* `divera247.set_status` -- set the current user status. Useful when you need
  to pass a free-text note or vehicle ID in addition to the status ID, which
  the `select` entity does not expose.

  ```yaml
  service: divera247.set_status
  data:
    status_id: 42
    note: "Heading to station"
    vehicle_id: 123
  ```

## How it works

* A single `Divera247Client` is owned per config entry and closed on unload.
* After the initial REST fetch a **WebSocket listener** connects to
  `wss://ws.divera247.com/ws` (via `divera247.websocket.stream_websocket`)
  and feeds push events back into the coordinator:
  * `user-status` events patch the cached status in place -- no extra HTTP
    request is issued, entities update immediately.
  * `cluster-pull` events trigger a scoped `/api/v2/pull/all` refresh.
  * Unknown event types are logged.
* The REST poll still runs every **15 minutes** as a safety net in case the
  WebSocket is temporarily disconnected.
* The `select` entity resolves each DIVERA status definition from the cluster
  payload so the available options (and their ordering) match the official
  DIVERA app.

## Limitations

* Only one UCR (UserClusterRelation) is exposed -- the one DIVERA returns as
  the active context for the Access Key. If you have multiple units, only the
  primary unit's data is surfaced.
* Only static Access Key authentication is offered from the UI. If you need
  JWT or refreshing JWT auth, use the library directly.

## License

AGPL-3.0 -- see [`LICENSE`](LICENSE).
