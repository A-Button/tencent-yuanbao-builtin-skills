# Infrared Remote Management

All paths below use `/v1.0/end-user/devices/{device_id}/infrareds` as their prefix. `device_id` is the gateway ID. Authentication follows `api-conventions.md`; SDK methods return the response's `result` directly.

## Configured Remote and Capability Queries

Use these read-only APIs before controlling an appliance. All example IDs are placeholders or masked values.

### List Configured Remotes

**Request**: `GET /remotes`

```bash
python3 {baseDir}/scripts/tuya_api.py ir_remotes <gateway_device_id>
```

```python
api.get_remotes(gateway_device_id)
```

Match `remoteName` to the appliance. Each result can include `categoryId`, `brandId`, `brandName`, `remoteId`, `remoteName`, `remoteIndex`, `operatorId`, `operatorName`, `areaId`, and `areaName`.

`remoteId` is the configured virtual remote ID used for key lookup and control. `remoteIndex` is the code-library index; they are not interchangeable.

```json
{"success": true, "result": [{"remoteId": "remote_****_id", "remoteName": "Living Room TV", "categoryId": 2, "brandId": 7, "brandName": "Example Brand", "remoteIndex": 87}]}
```

### Query Supported Keys

**Request**: `GET /remotes/{remote_id}/keys`

```bash
python3 {baseDir}/scripts/tuya_api.py ir_keys <gateway_device_id> <remote_id>
```

```python
api.get_remote_keys(gateway_device_id, remote_id)
```

The result includes `brandId`, `categoryId`, `remoteIndex`, `singleAir`, `duplicatePower`, `keyList`, and optional air-conditioner `keyRange`. Each `keyList` item provides `key`, `keyId`, `keyName`, and `standardKey`.

Use `keyList[].key` verbatim in standard control. Do not infer key strings: one remote may return `Volume+`, while another may use a different value. If `duplicatePower` is true, or there is only `Power` without separate on/off keys, treat it as a toggle and do not claim a confirmed power state. For air conditioners, allow only mode, temperature, and fan combinations returned in `keyRange`.

### Query Code-Library Rules

**Request**: `GET /categories/{category_id}/brands/{brand_id}/remotes/{remote_index}/rules`

```bash
python3 {baseDir}/scripts/tuya_api.py ir_rules <gateway_device_id> <category_id> <brand_id> <remote_index>
```

```python
api.get_remote_rules(gateway_device_id, category_id, brand_id, remote_index)
```

Returns `keyId`, `key`, `keyName`, and the underlying infrared `code` for each code-library rule. Use it only when raw code information is needed; ordinary control should use the configured remote's supported-key list.

### Query Brands by Remote Index

**Request**: `GET /categories/{category_id}/remotes/{remote_index}/brands`

Optional query parameter: `countryCode`.

```bash
python3 {baseDir}/scripts/tuya_api.py ir_remote_brands <gateway_device_id> <category_id> <remote_index> [--country_code <country>]
```

```python
api.get_remote_brands(gateway_device_id, category_id, remote_index, country_code=None)
```

Use this lookup when category and remote index are known but the brand is not.

## 1. Query Appliance Categories

**Request**: `GET /categories`

**CLI / SDK**

```bash
python3 {baseDir}/scripts/tuya_api.py ir_categories <device_id>
```

```python
api.get_categories(device_id)
```

**Response Example**

```json
{"success": true, "result": [{"categoryId": 2, "categoryName": "TV"}]}
```

Use returned categories and IDs rather than assuming a fixed list.

## 2. Query Brands

**Request**: `GET /categories/{category_id}/brands`

**Query Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| countryCode | String | No | Country filter; use CN for China |

**CLI / SDK**

```bash
python3 {baseDir}/scripts/tuya_api.py ir_brands <device_id> <category_id> [--country_code <country>]
```

```python
api.get_brands(device_id, category_id, country_code="CN")
```

**Response Example**

```json
{"success": true, "result": [{"brandId": 12, "brandName": "Samsung"}]}
```

## 3. Query Code-Library Indexes

**Request**: `GET /categories/{category_id}/brands/{brand_id}/remote-indexs`

**Query Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| countryCode | String | No | Country filter |
| mode | String | No | Model-name fuzzy filter |
| page | Integer | No | Page number; default 1 |
| size | Integer | No | Page size; default 100, maximum 1000 |

**CLI / SDK**

```bash
python3 {baseDir}/scripts/tuya_api.py ir_indexes <device_id> <category_id> <brand_id> [--country_code <country>] [--mode <model>] [--page <page>] [--size <size>]
```

```python
api.get_remote_indexes(device_id, category_id, brand_id,
                       country_code="CN", mode=None, page=1, size=100)
```

**Response Example**

```json
{"success": true, "result": {"totalCount": 2, "remoteIndexList": [{"remoteIndex": 10572}, {"remoteIndex": 692}]}}
```

Use `totalCount` and the returned list to determine whether more pages are needed.

## 4. Add a Remote

**Request**: `POST /remotes`

**Request Body**

| Parameter | Type | API Required | Description |
|-----------|------|--------------|-------------|
| category_id | Integer | No | Appliance category |
| remote_index | Integer | No | Matched code-library index |
| remote_name | String | No | Display name |
| brand_id | Integer | No | Brand ID |
| brand_name | String | No | Brand name |

The CLI/SDK require category, index and name for the pairing workflow.

**CLI / SDK**

```bash
python3 {baseDir}/scripts/tuya_api.py ir_add <device_id> <category_id> <remote_index> <remote_name> [--brand_id <id>] [--brand_name <name>]
```

```python
api.add_remote(device_id, category_id, remote_index, remote_name,
               brand_id=None, brand_name=None)
```

**Response Example**

```json
{"success": true, "result": "remote_****_id"}
```

The result is the new `remote_id`, used for subsequent control and management.

## 5. Rename a Remote

**Request**: `PUT /remotes/{remote_id}`

**Request Body**

```json
{"remoteName": "Bedroom TV"}
```

`remoteName` is camelCase. The SDK maps `remote_name` to this field.

**CLI / SDK**

```bash
python3 {baseDir}/scripts/tuya_api.py ir_rename <device_id> <remote_id> <new_name>
```

```python
api.rename_remote(device_id, remote_id, remote_name)
```

## 6. Delete a Remote

**Request**: `DELETE /remotes/{remote_id}`; no request body.

**CLI / SDK**

```bash
python3 {baseDir}/scripts/tuya_api.py ir_delete <device_id> <remote_id>
```

```python
api.delete_remote(device_id, remote_id)
```

Rename and delete return `{"success": true, "result": true}` on success.
