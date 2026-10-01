# Infrared Control

All paths below use `/v1.0/end-user/devices/{device_id}/infrareds` as their prefix. Authentication follows `api-conventions.md`.

`device_id` is the infrared gateway ID. Pairing tests use a code-library `remote_index`; control uses the `remote_id` returned when adding a remote.

## 1. Send a Standard Key

**Request**

```
POST /v1.0/end-user/devices/{device_id}/infrareds/remotes/{remote_id}/command
```

**Request Body**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| category_id | Integer | Yes | Appliance category |
| key | String | Yes | Standard key name |
| remote_index | Integer | No | Matched code-library index |

**CLI / SDK**

```bash
python3 {baseDir}/scripts/tuya_api.py ir_control <device_id> <remote_id> <category_id> <key> [--remote_index <index>]
```

```python
api.send_standard_command(device_id, remote_id, category_id, key, remote_index=None)
```

**Key source and power limitation**

Before control, call `GET /remotes/{remote_id}/keys` (see `remote-management.md`). Use the returned `keyList[].key` verbatim; key strings vary by remote. If `duplicatePower` is true, or only `Power` is available, it is a toggle and cannot prove the appliance's actual on/off state.

## 2. Send a Raw Key

**Request**

```
POST /v1.0/end-user/devices/{device_id}/infrareds/remotes/{remote_id}/raw/command
```

**Request Body**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| category_id | Integer | Yes | Appliance category |
| key | String | Conditional | Raw key name; provide key or key_id |
| key_id | Integer | Conditional | Raw key ID; zero is valid |
| remote_index | Integer | No | Matched code-library index |

**CLI / SDK**

```bash
python3 {baseDir}/scripts/tuya_api.py ir_control_raw <device_id> <remote_id> <category_id> --key <key> [--remote_index <index>]
python3 {baseDir}/scripts/tuya_api.py ir_control_raw <device_id> <remote_id> <category_id> --key_id <key_id>
```

```python
api.send_raw_command(device_id, remote_id, category_id,
                     remote_index=None, key=None, key_id=None)
```

Raw keys are infrared remote keys, not Thing Model `raw` properties or uploaded infrared waveforms.

## 3. Test a Key During Pairing

**Requests**

```
POST /v1.0/end-user/devices/{device_id}/infrareds/testing/command
POST /v1.0/end-user/devices/{device_id}/infrareds/testing/raw/command
```

The request bodies match the standard/raw key tables above. Use the candidate `remote_index`; no `remote_id` is needed.

**CLI / SDK**

```bash
python3 {baseDir}/scripts/tuya_api.py ir_test <device_id> <category_id> <remote_index> <key>
python3 {baseDir}/scripts/tuya_api.py ir_test_raw <device_id> <category_id> <remote_index> --key <key>
python3 {baseDir}/scripts/tuya_api.py ir_test_raw <device_id> <category_id> <remote_index> --key_id <key_id>
```

```python
api.test_standard_command(device_id, category_id, key, remote_index=None)
api.test_raw_command(device_id, category_id, remote_index=None, key=None, key_id=None)
```

## Response

All four endpoints return:

```json
{"success": true, "result": true}
```

The SDK returns `result` directly. `true` means dispatched, not confirmed execution. Pairing requires user feedback on the physical response. Infrared writes are not automatically retried.
