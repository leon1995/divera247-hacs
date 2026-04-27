# DIVERA 24/7 for Home Assistant

> **Warning**
> This integration is still a work in progress and may change or break between updates.

Home Assistant custom integration for [DIVERA 24/7](https://www.divera247.com/),
built on top of the async [`divera247`](https://github.com/leon1995/divera247)
Python client.

This integration is inspired by [moehrem/DiveraControl](https://github.com/moehrem/DiveraControl) and [lassefactory/divera-hacs](https://github.com/lassefactory/divera-hacs), combining DiveraControl's broad sensor coverage with divera-hacs style status updates via WebSocket.

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

The integration is configured entirely through the UI. You need to create an
**Api Key** in the DIVERA web app under
[_Einstellungen -> Login_](https://app.divera247.com/account/einstellungen.html).

Only the Access Key auth flow is exposed in the UI -- it is the simplest way
to authenticate and works for both REST and WebSocket endpoints of the DIVERA
API.

## What you get

### Device

A single device per configured Access Key, named after the owning user.

### Sensors

| Entity | Description |
| --- | --- |
| `sensor.<user>_status` | Current user status (name); attributes include the full DIVERA status payload |
| `sensor.<user>_status_vehicle_id` | Vehicle ID currently attached to your status (if set) |
| `sensor.<user>_status_changed` | Timestamp of the last status change |
| `sensor.<user>_next_status_reset` | Timestamp of the next automatic status reset |
| `sensor.<user>_new_alarms` | Counter: number of new alarms in the pull payload |
| `sensor.<user>_open_alarms` | Counter: number of currently open alarms |
| `sensor.<user>_new_messages` | Counter: number of new messages |
| `sensor.<user>_latest_alarm` | Headline (_Stichwort_) of the most recent alarm; attributes include full alarm payload |
| `sensor.<user>_latest_alarm_time` | Timestamp of the most recent alarm |
| `sensor.<user>_next_event` | Title of the next upcoming event; attributes include full event payload |
| `sensor.<user>_status_count_<id>` | Dynamic sensors: one per available status ID, value is current member count in that status |
| `sensor.<user>_user` | Full name (diagnostic) |
| `sensor.<user>_unit` | Configured unit/cluster name (diagnostic); attributes include full cluster payload (including cluster ID) |
| `sensor.<user>_can_set_status` | Whether the account can change user status (diagnostic) |
| `sensor.<user>_can_manage_alarms` | Whether the account can manage alarms (diagnostic) |
| `sensor.<user>_can_send_messages` | Whether the account can send messages (diagnostic) |
| `sensor.<user>_can_manage_news` | Whether the account can manage news (diagnostic) |
| `sensor.<user>_can_set_vehicle_status` | Whether the account can change vehicle status (diagnostic) |

### Binary sensors

| Entity | Description |
| --- | --- |
| `binary_sensor.<user>_active_alarm` | On while at least one alarm is open |
| `binary_sensor.<user>_status_reset_scheduled` | On when a future automatic status reset is scheduled |

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

* A single `Divera247Client` is created per config entry and reused for both
  REST and WebSocket communication. It is closed again when the entry unloads.
* The coordinator performs a periodic `/api/v2/pull/all` refresh (every
  **15 minutes**) and exposes that payload to all entities.
* On each coordinator update, the integration also fetches
  `/api/v2/pull/vehicle-status`; if that request fails temporarily, the last
  known vehicle-status cache is kept.
* After startup, a persistent WebSocket listener connects to
  `wss://ws.divera247.com/ws` and applies push events:
  * `user-status` updates patch `coordinator.data.status` in place, so status
    entities update immediately without an extra REST request.
  * `cluster-vehicle` updates trigger a targeted `vehicle-status` refresh and
    update vehicle entities immediately (with full refresh fallback on errors).
  * `cluster-pull` and `cluster-monitor` updates trigger a coordinator refresh.
  * Unknown events are logged, with safe fallback routing for known raw event
    type strings. If you encounter any, feel free to create a pull request at
    [divera247](https://github.com/leon1995/divera247), in order for the event
    to get implemented.
* Dynamic `status_count_<id>` sensors are generated from the available status
  definitions in the cluster payload and use live counts from monitor/UCR data.
* The `select.<user>_status` entity builds its options directly from DIVERA
  status definitions, preserving naming and ordering from the cluster config.

## Limitations

* Only one UCR (UserClusterRelation) is exposed -- the one DIVERA returns as
  the active context for the Access Key. If you have multiple units, only the
  primary unit's data is surfaced.

## License

AGPL-3.0 -- see [`LICENSE`](LICENSE).
