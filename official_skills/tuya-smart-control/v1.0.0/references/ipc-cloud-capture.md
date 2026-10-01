# IPC AI — Cloud Capture

Cloud snapshot / short video capture for IPC (camera) devices.

> **Bounded capture flow**: invoke one documented all-in-one helper per user request and camera. It allocates once, waits, then resolves once with **at most two NOT_READY retries** (three resolve requests total, all for the same allocation). Do not call resolve immediately, restart the helper, or add an outer polling loop. Rate limits and other IPC errors stop immediately.

The endpoint descriptions and low-level helper names below document SDK internals; they do not authorize direct calls outside the interfaces allowed in `SKILL.md`. Do not use them to extend or reset the retry budget.

## 1. Allocate Cloud Capture

Request the device to take a snapshot or record a short video and upload it to cloud storage. Returns storage coordinates only — no media URL.

**Request**

```
POST /v1.0/end-user/ipc/{device_id}/capture/allocate
```

**Path Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| device_id | String | Yes | Device ID |

**Request Body**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| capture_json | String | Yes | JSON string containing capture parameters |

**`capture_json` Fields**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| device_id | String | Yes | Device ID (must match path parameter) |
| capture_type | String | Yes | `PIC` for snapshot, `VIDEO` for short video |
| pic_count | Integer | No | Number of snapshots. Server clamps to **1–5** |
| video_duration_seconds | Integer | No | Video duration in seconds. Default 10, server clamps to **1–60** |
| home_id | String | No | Home ID. If provided, must match the device owner |

**Request Example**

```json
{
  "capture_json": "{\"device_id\":\"6c95a7a3...\",\"capture_type\":\"PIC\",\"pic_count\":1}"
}
```

**Response**

```json
{
  "success": true,
  "result": {
    "success": true,
    "status": "ACCEPTED",
    "device_id": "6c95a7a3...",
    "capture_type": "PIC",
    "bucket": "ty-cn-storage30",
    "image_object_key": "/path/to/1234567890_0.jpg",
    "encryption_key": "abc123...",
    "upload_async_hint": "bucket/objectKey only mean upload slots were allocated; the device may still be uploading.",
    "pic_count_requested": 1,
    "pic_count_effective": 1,
    "pic_slots": [
      {
        "success": true,
        "image_object_key": "/path/to/1234567890_0.jpg",
        "encryption_key": "abc123..."
      }
    ]
  }
}
```

**Response Fields**

| Field | Type | Description |
|-------|------|-------------|
| success | Boolean | Whether allocation succeeded |
| status | String | `ACCEPTED` or `REJECTED` |
| bucket | String | Cloud storage bucket name |
| image_object_key | String | Image object key (PIC) |
| video_object_key | String | Video object key (VIDEO) |
| cover_image_object_key | String | Video cover image key (VIDEO) |
| encryption_key | String | File encryption key |
| upload_async_hint | String | Reminder that file may still be uploading |
| pic_slots | List | Per-snapshot details (PIC only) |
| video_duration_seconds_effective | Integer | Actual clamped duration (VIDEO only) |

---

## 2. Resolve Capture Access URL

Poll this API after allocate to obtain accessible media URLs. Returns `NOT_READY` while the device is still uploading.

**Request**

```
POST /v1.0/end-user/ipc/{device_id}/capture/resolve
```

**Path Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| device_id | String | Yes | Device ID |

**Request Body**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| resolve_json | String | Yes | JSON string containing resolve parameters |

**`resolve_json` Fields**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| device_id | String | Yes | Device ID |
| capture_type | String | Yes | `PIC` or `VIDEO` (must match allocate) |
| bucket | String | Yes | Bucket from allocate response |
| image_object_key | String | PIC: Yes | Image object key from allocate |
| video_object_key | String | VIDEO: Yes | Video object key from allocate |
| cover_image_object_key | String | No | Cover image key (VIDEO only) |
| encryption_key | String | No | Encryption key from allocate |
| user_privacy_consent_accepted | Boolean | No | `true`: return decrypted playable URLs; `false`: return raw presigned URLs (encrypted) |
| home_id | String | No | Home ID |

**Request Example**

```json
{
  "resolve_json": "{\"device_id\":\"6c95a7a3...\",\"capture_type\":\"PIC\",\"bucket\":\"ty-cn-storage30\",\"image_object_key\":\"/path/to/1234567890_0.jpg\",\"encryption_key\":\"abc123...\",\"user_privacy_consent_accepted\":true}"
}
```

**Response (ready)**

```json
{
  "success": true,
  "result": {
    "status": "ACCEPTED",
    "decrypt_image_url": "https://...",
    "message_for_user": "ok"
  }
}
```

**Response (not ready — only the helper may retry within its two-retry budget)**

```json
{
  "success": true,
  "result": {
    "status": "NOT_READY",
    "error_code": "OBJECT_NOT_READY",
    "message_for_user": "object not uploaded yet or empty (check contentLength)"
  }
}
```

**Response Fields**

| Field | Type | Description |
|-------|------|-------------|
| status | String | `ACCEPTED` (URL ready), `NOT_READY` (retry only within the helper's remaining budget) |
| decrypt_image_url | String | Decrypted playable image URL (when consent = true, PIC) |
| decrypt_video_url | String | Decrypted playable video URL (when consent = true, VIDEO) |
| decrypt_cover_image_url | String | Decrypted cover image URL (VIDEO). May be null if cover is not ready yet — check message_for_user |
| raw_presigned_image_url | String | Raw presigned URL (when consent = false, PIC) |
| raw_presigned_video_url | String | Raw presigned URL (when consent = false, VIDEO) |
| raw_presigned_cover_image_url | String | Raw presigned cover URL (VIDEO). May be null if cover is not ready yet |
| error_code | String | `OBJECT_NOT_READY` when file not yet uploaded |
| message_for_user | String | `ok` when all ready; `ok (cover image not ready yet)` when video ready but cover still uploading |

---

## 3. Fusion-level errors (`success: false` on the outer envelope)

Both capture endpoints are implemented by Hawkeye **`IIpcAiCaptureOpenFusionService`**.

Empty/invalid JSON or missing required fields cause Atop to **throw HawkeyeException**; business exceptions from the Biz layer also propagate as exceptions. All exceptions are caught and mapped to **`FusionResult.buildFail`** by **`HawkeyeFusionService`**. The outer **`code` / `msg`** are determined by the exception type and the Fusion / gateway layer (commonly numeric API error numbers such as **`1109`** for bad input).

---

## 4. Recommended Usage

1. **Capture**: invoke the documented CLI or all-in-one SDK helper once. It allocates once and owns the first resolve plus at most two retries. Once it returns, stop; do not add requests even if a URL is still unavailable.
2. **Video resolve**: return a successful video only when its decrypted URL is present. Cover image URL may be null if still uploading — check `message_for_user` for `"ok (cover image not ready yet)"`. A missing cover is not a reason to retry a successful video capture.
3. **Privacy**: only set `user_privacy_consent_accepted=true` when the user has explicitly agreed.
4. **Outer failures**: if `success` is `false`, read **`code`** and **`msg`** per §3. Parameter errors and Biz exceptions all produce outer `success: false` with a numeric error code.
5. **Stop**: `1199`, HTTP `429`, authentication/authorization errors, network failures and uncertain execution results terminate this attempt immediately. Do not wait and retry, switch CLI/SDK or PIC/VIDEO, increase parameters, or create background jobs. Only a new explicit user request permits a fresh capture.

---

## 5. Pic Capture: Wait and Retry

The device must finish capturing and uploading before resolve can return an image URL.

- **Initial wait**: sleep **2 seconds** before the first resolve call.
- **Request budget**: one resolve request plus at most **two** retries on `NOT_READY`, separated by **3 seconds**. There is no separate polling phase and no extra retries after timeout.
- **Compatibility parameters**: `retry_count` defaults to `2` and accepts only integers `0`–`2`. `poll_timeout` defaults to `30` seconds and limits starting retries after the initial wait; increasing it never raises the three-request cap. An in-flight request still has its HTTP timeout.
- **Exhaustion**: return the last `NOT_READY` result with `terminal_for_current_request: true`, `retry_allowed: false`, and `requires_explicit_user_retry: true`. The agent reports failure and stops; it must not call this helper again.

**Helper methods** (`scripts/tuya_api.py`):

| Method | Description |
|--------|-------------|
| `ipc_ai_capture_pic_resolve_with_wait(...)` | Internal bounded resolver; first request plus at most two retries |
| `ipc_ai_capture_pic_allocate_and_fetch(...)` | Agent entry point: allocate PIC once, then bounded resolve |

**CLI example**:

```bash
python3 scripts/tuya_api.py ipc_pic_fetch <device_id> 1
# consent=1 (decrypted URL); optional 3rd arg: pic_count; optional 4th: home_id
```

---

## 6. Video Capture: Wait and Retry

The device must finish recording and uploading before resolve can return a playable URL.

- **Minimum wait**: before the first resolve call, wait at least **`max(5, video_duration_seconds_effective) + 2` seconds**.
- **Request budget**: one resolve request plus at most **two** retries on `NOT_READY`, separated by **5 seconds**. There is no separate polling phase and no extra retries after timeout.
- **Compatibility parameters**: `retry_count` defaults to `2` and accepts only integers `0`–`2`. `poll_timeout` defaults to `120` seconds and limits starting retries after the initial wait; increasing it never raises the three-request cap. An in-flight request still has its HTTP timeout.
- **Exhaustion**: use the same terminal result and stop policy as PIC above. Do not retry to obtain a missing cover image when the video itself is ready.

**Helper methods** (`scripts/tuya_api.py`):

| Method | Description |
|--------|-------------|
| `ipc_ai_capture_video_resolve_with_wait(...)` | Internal bounded resolver; first request plus at most two retries |
| `ipc_ai_capture_video_allocate_and_fetch(...)` | Agent entry point: allocate VIDEO once, then bounded resolve |

**CLI example**:

```bash
python3 scripts/tuya_api.py ipc_video_fetch <device_id> 5 1
# 5-second video, consent=1 (decrypted URL); optional 4th arg: home_id
```
