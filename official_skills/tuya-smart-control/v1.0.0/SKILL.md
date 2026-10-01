---
name: tuya-smart-control
description: Control Tuya smart home devices via natural language. Use when the user asks to control smart devices (turn on/off lights, AC, plugs, adjust brightness/temperature/mode), query device status or list devices, manage homes and rooms, rename devices, check weather by location, send notifications (email or App push), view device data statistics (e.g. energy/power consumption), or capture snapshots/short videos from IPC cameras. Use also to control infrared TVs, air conditioners and other appliances through an online Tuya infrared gateway, or pair and manage their remotes. Controls only authorized cloud-connected devices without special security-level restrictions; offline Bluetooth devices and door locks are not supported. Infrared appliances need a cloud-connected gateway, not their own cloud connection.
---

# Tuya Smart Home Device Control Skill

## Basic Information

- **Official Website**: https://www.tuya.com/
- **Source Code**: https://github.com/tuya/tuya-openclaw-skills
- **Authentication**: Via headers `Authorization: Bearer {access_token}` and `client_id: {client_id}`.
- **Credentials**: Read from required environment variables `TUYA_ACCESS_TOKEN` and `TUYA_CLIENT_ID`. The default endpoint is China (`https://openapi.tuyacn.com`); override it with `TUYA_BASE_URL` only when needed.
- **API Reference**: See individual files under `references/`
- **Python SDK**: See `scripts/tuya_api.py`

## Device Control Scope

- **Supported**: authorized devices connected to the Tuya cloud, directly or through an online gateway, with no special security-level restrictions and with the requested API capability. Examples include lights, plugs, switches, air conditioners, fans and curtains; category alone does not guarantee support.
- **Infrared appliances**: TVs, air conditioners, set-top boxes, fans, projectors and other appliances supported by the gateway's returned code library. The infrared gateway must be cloud-connected and online; the appliance itself need not connect to the cloud and must be within infrared range.
- **Unsupported**: offline devices, Bluetooth devices without an available cloud connection (including local-only/offline Bluetooth devices), door locks and other devices subject to special security-level restrictions. Cloud connectivity alone does not make a restricted device controllable.
- Before control, check authorization, connectivity and capabilities. Stop for unsupported/restricted devices even if they appear in the device list; do not infer an undocumented numeric security-level threshold.

## Environment Variable Configuration

Set the following environment variable before use:

```bash
export TUYA_ACCESS_TOKEN="your-access-token"
export TUYA_CLIENT_ID="your-client-id"
# Optional; defaults to https://openapi.tuyacn.com
# export TUYA_BASE_URL="https://openapi.tuyacn.com"
```

The Skill will not load if `TUYA_ACCESS_TOKEN` or `TUYA_CLIENT_ID` is missing.

## Usage

Mandatory execution constraints:
- Use only the interfaces documented in this `SKILL.md`: the listed `scripts/tuya_api.py` CLI commands and the shown `TuyaAPI` SDK methods. Do not use any other Tuya endpoint, local protocol, app/browser action, inferred API, or external interface for Tuya operations.
- Before a cloud-device command, reread the target device through `device_detail` / `get_device_detail`. Before an infrared command, reread the infrared gateway detail and use the configured-remote and key-query interfaces below; gateway state does not prove the appliance's actual state.

### Retry Budget and Mandatory Stop

- **At most two retries** means one initial request plus at most two additional attempts, not three retries. SDK/HTTP retries count toward this budget; do not add an agent-level retry loop after a command returns. Operations that forbid retries (such as infrared toggle/relative commands) still forbid them.
- **IPC capture: allocate once, resolve at most three times.** Invoke exactly one `ipc_pic_fetch` / `ipc_video_fetch` command or its documented `allocate_and_fetch` SDK helper per user request and camera. Only the helper may retry `NOT_READY`, at most twice against the same allocation. There is no separate polling allowance or additional retry allowance after a timeout.
- Once the helper returns `NOT_READY`, lacks the required decrypted URL, or fails, end this request and report the result. Do not call the helper again, switch CLI/SDK or PIC/VIDEO, change parameters to reset the budget, or invoke low-level allocate/resolve methods yourself.
- For IPC, rate-limit errors (`1199` or HTTP `429`), authentication/authorization errors, network errors and uncertain execution results stop immediately; they do not authorize another attempt. A tool timeout does not prove that the operation never started.
- If any command returns HTTP `403 Forbidden` from the Tuya API—especially an error such as `Error: HTTP error from Tuya API: 403 Client Error: Forbidden ... Command: devices`—treat the current authorization as expired, revoked, or displaced by another account session. Stop retrying and tell the user that they can first try unbinding Tuya Smart Control in the Skill Marketplace, then bind it again. Retry the Tuya operation only after the user has completed reauthorization and explicitly asks to continue.
- Do not extend capture through custom polling scripts, longer timeouts, `sleep` commands, scheduled jobs, `nohup`, `setsid`, or background processes. Do not modify the skill scripts to bypass this policy.
- After stopping, only a new explicit user request to retry permits another capture. “Try again later” is advice to the user, not permission for the agent to wait and retry automatically.

**Always prefer Method 1 (Command Line)** — single command, no boilerplate code. It handles Bearer authentication, JSON serialization, and error handling automatically.

### Method 1: Via Command Line (Recommended)

```bash
python3 {baseDir}/scripts/tuya_api.py <command> [params...]
# Examples:
python3 {baseDir}/scripts/tuya_api.py homes
python3 {baseDir}/scripts/tuya_api.py devices
python3 {baseDir}/scripts/tuya_api.py devices --home 5053559
python3 {baseDir}/scripts/tuya_api.py devices --room 123456
python3 {baseDir}/scripts/tuya_api.py device_detail <device_id>
python3 {baseDir}/scripts/tuya_api.py model <device_id>
python3 {baseDir}/scripts/tuya_api.py control <device_id> '{"switch_led":true}'
python3 {baseDir}/scripts/tuya_api.py rename <device_id> "New Name"
python3 {baseDir}/scripts/tuya_api.py ir_remotes <gateway_device_id>
python3 {baseDir}/scripts/tuya_api.py ir_keys <gateway_device_id> <remote_id>
python3 {baseDir}/scripts/tuya_api.py ir_rules <gateway_device_id> <category_id> <brand_id> <remote_index>
python3 {baseDir}/scripts/tuya_api.py ir_remote_brands <gateway_device_id> <category_id> <remote_index>
python3 {baseDir}/scripts/tuya_api.py ir_control <device_id> <remote_id> <category_id> <key>
python3 {baseDir}/scripts/tuya_api.py ir_categories <device_id>
python3 {baseDir}/scripts/tuya_api.py ir_brands <device_id> <category_id>
python3 {baseDir}/scripts/tuya_api.py ir_indexes <device_id> <category_id> <brand_id>
python3 {baseDir}/scripts/tuya_api.py ir_test <device_id> <category_id> <remote_index> <key>
python3 {baseDir}/scripts/tuya_api.py ir_add <device_id> <category_id> <remote_index> "Remote Name"
python3 {baseDir}/scripts/tuya_api.py ir_rename <device_id> <remote_id> "New Name"
python3 {baseDir}/scripts/tuya_api.py ir_delete <device_id> <remote_id>
python3 {baseDir}/scripts/tuya_api.py weather 39.90 116.40
python3 {baseDir}/scripts/tuya_api.py mail "Subject" "Content"
python3 {baseDir}/scripts/tuya_api.py push "Subject" "Content"
python3 {baseDir}/scripts/tuya_api.py stats_config
python3 {baseDir}/scripts/tuya_api.py stats_data <dev_id> <dp_code> <type> <start> <end>
python3 {baseDir}/scripts/tuya_api.py ipc_pic_fetch <device_id> <consent> [pic_count] [home_id]
python3 {baseDir}/scripts/tuya_api.py ipc_video_fetch <device_id> <duration> <consent> [home_id]
```

CLI validation rules:
- `devices` supports only one scope flag at a time: `--home <id>` or `--room <id>`
- `ir_control_raw` / `ir_test_raw` require `--key <name>` or `--key_id <integer>`; optional arguments for all infrared commands are listed in `--help`
- `control` requires `properties_json` to be a valid JSON object (not array/string)
- `weather` validates coordinate range: latitude `[-90, 90]`, longitude `[-180, 180]`
- `stats_data` validates `start`/`end` format `yyyyMMddHH` and max 24-hour window
- `ipc_pic_fetch` args: `<device_id> <consent> [pic_count] [home_id]` — consent `1` = decrypted URL
- `ipc_video_fetch` args: `<device_id> <duration> <consent> [home_id]` — duration in seconds (1-60)
- Use `python3 {baseDir}/scripts/tuya_api.py --help` for command help and examples

### Method 2: Via Python SDK

Use when you need to chain multiple API calls or do complex logic in a single script:

```python
import sys
sys.path.insert(0, "{baseDir}/scripts")
from tuya_api import TuyaAPI

api = TuyaAPI()

homes = api.get_homes()
devices = api.get_all_devices()
detail = api.get_device_detail("device_id_here")
result = api.issue_properties("device_id_here", {"switch_led": True, "bright_value": 500})
weather = api.get_weather(lat="39.90", lon="116.40")
# IPC cloud capture — take a snapshot and get decrypted URL
capture = api.ipc_ai_capture_pic_allocate_and_fetch("device_id_here")
```

### IPC Media Output (`media_info`)

- All user-facing IPC images MUST be output with a `<media_info>` block. VIDEO output follows the mandatory URL rules below and does not require an inline video player.
- Whenever the final answer outputs or presents an image—including a PIC snapshot or an explicitly requested VIDEO cover/photo—it MUST also include this exact visible sentence: `因为信息安全保护，图片会过期哦～`
- For a successful PIC capture, use the decrypted image URL:

```text
<media_info>[{"type":"image","description":"Tuya IPC snapshot","url":"<decrypt_image_url>"}]</media_info>
```

- For a successful VIDEO capture, the final answer MUST visibly include the complete, unmodified value of `resolve["decrypt_video_url"]` on its own line. Do not shorten, redact, hide behind link text, omit, or replace it with a local path.
- Format it as the label `视频链接：` followed on the next line by the raw URL value. Do not wrap the URL in a code fence.
- Choose exactly one VIDEO delivery branch from the user's request:
  - **Video only (default)**: when the user asks for a recorded video without explicitly requesting its cover, a photo, a still image, or a snapshot from that recording, the raw `resolve["decrypt_video_url"]` is the only user-facing media deliverable. Do not call `present_files`, emit `<media_info>`, create a video card, or output, attach, mention, or otherwise expose `resolve["decrypt_cover_image_url"]`, `raw_presigned_cover_image_url`, the cover-image object key, or any other media item. The mere presence of cover-image fields in the API response is not permission to include them.
  - **Video plus explicitly requested cover/photo**: when the same request explicitly asks for the video's cover, a photo, a still image, or a snapshot, the raw `resolve["decrypt_video_url"]` remains mandatory and the final answer MUST also emit exactly one image `<media_info>` item using `resolve["decrypt_cover_image_url"]`. Do not leave a cover/photo heading empty, do not output the cover as a bare URL, and do not emit a video `<media_info>` item or call `present_files`.

```text
视频链接：
<decrypt_video_url>

<media_info>[{"type":"image","description":"视频封面","url":"<decrypt_cover_image_url>"}]</media_info>
```

- If the user explicitly requests the cover/photo but `resolve["decrypt_cover_image_url"]` is missing or empty, do not emit an empty `<media_info>` item. Still output the video URL, state that the cover image is unavailable, and do not retry solely to obtain the cover.
- The final answer must still contain the visible raw video URL after any tool call or media block. Do not put the URL only inside tool arguments, tool output, `media_info`, Markdown link text, or a code block.
- Only emit a media item when the capture resolve status is successful and its decrypted URL is present. Never place an empty, unresolved, or `NOT_READY` URL in `media_info`.
- Do not download a VIDEO merely to display or send it. A local image download is only for internal processing such as visual recognition. Never return a local MP4 path instead of `resolve["decrypt_video_url"]`.

### Image File Storage for Internal Processing (Sandbox)

- This section applies only when an IPC image must be downloaded for internal processing. It does not replace the required user-facing `media_info` output.
- Save downloaded IPC images inside the sandbox at the absolute directory `/data/workspace/`. This includes snapshots and video cover images when a local copy is actually needed.
- Create the directory if needed. Use a unique filename such as `/data/workspace/tuya_snapshot_<timestamp>_<uuid>.jpg`, with an extension matching the actual image format; do not overwrite existing files.
- Do not save images to the skill directory, the current working directory, `/tmp`, or a host-machine path. If `/data/workspace/` cannot be created or written, report the failure instead of silently choosing another directory.
- The SDK returns media URLs and cloud object keys; it does not download files. Download from the returned decrypted image URL separately. `image_object_key` is a cloud storage key, not a local destination path.
- Verify that the download succeeded and the saved file is non-empty before passing its absolute path to a vision tool. Never return this internal local path as the user-facing media result.

## Feature Overview

| Module | Capabilities | Reference |
|--------|-------------|-----------|
| Home Management | List all homes, list rooms in a home | `references/home-and-space.md` |
| Device Query | All devices, devices by home/room, single device detail (including current property states) | `references/device-query.md` |
| Device Control | Query device Thing Model, issue property commands | `references/device-control.md` |
| Infrared Control | Discover configured remotes, query supported keys, control TVs/ACs and test remote keys | `references/infrared-control.md` |
| Infrared Remote Management | Query configured remotes, categories, brands and code libraries; add, rename and delete remotes | `references/remote-management.md` |
| Device Management | Rename device | `references/device-management.md` |
| Weather Service | Current and forecast weather | `references/weather.md` |
| Notifications | Email, App push | `references/notifications.md` |
| Data Statistics | Hourly statistics config query, statistics value query | `references/statistics.md` |
| IPC Cloud Capture | Cloud snapshot and short video capture for IPC cameras | `references/ipc-cloud-capture.md` |
| Error Handling | Error codes and recovery strategies | `references/error-handling.md` |
| API Conventions | Request/response format and Bearer-token authentication | `references/api-conventions.md` |

## Core Workflows

### Control Routing: Infrared vs. Cloud Device

Before controlling an appliance named by the user (for example, “打开电视”), determine the control path; never route based only on the appliance name, `category: qt`, or `product_name: TV`.

1. List devices and identify candidate infrared gateways. A `wnykq` category is a candidate only; read its detail and continue only when it is online and identified as an infrared gateway (for example, `product_name: Smart IR`).
2. For every eligible infrared gateway, call `ir_remotes <gateway_device_id>` and match the requested appliance against `remoteName`. The presence of a matching configured remote is the authoritative indication that the appliance can use the infrared path.
3. Independently identify same-name ordinary cloud-device candidates from the device list. Do not treat the virtual remote record's category as proof of a direct cloud-control capability; ordinary control still requires a device-detail and Thing Model capability check.
4. Route exactly one infrared match to Workflow 10. Route exactly one valid cloud-device match to Workflow 1. If both paths match, or either path has multiple candidates that cannot be resolved by the user-specified room/location, present the candidates and ask the user to choose. If neither path matches, report that no configured controllable appliance was found.
5. Once the infrared path is selected, use the matched remote record's `remoteId`, `categoryId`, `brandId`, and `remoteIndex`, then query `ir_keys` before issuing a command.

### Workflow 1: Device Control

When the user says things like "turn on the living room light" or "set the AC temperature to 26 degrees":

1. **Locate the device** — Find the target device based on the device name or location mentioned by the user. Follow this priority:
   - **Priority 1 — Room + category match**: If the user mentions a room (e.g. "living room AC"), first query the home list → room list to match the room, then list devices in that room and match by `category_name` or device `name`
   - **Priority 2 — Device name match**: If the user only mentions a device name (e.g. "AC"), call "List All Devices" API and match by `category_name` first, then by device `name` fuzzy match
   - **Priority 3 — Disambiguation**: If multiple devices match, list all candidates with their room information and ask the user to choose

2. **Check control scope and get current state** — Exclude devices outside the Device Control Scope above, including door locks and devices with special security-level restrictions. Apply the Control Routing rule above before treating a named appliance as a normal cloud device or routing it to Workflow 10.
   **Get current state** — Call the "Get Single Device Detail" API
   - **If `result` is `null`**: the device does not exist or you have no permission — inform the user and stop
   - **If `online` is `false`**: the device is offline — tell the user "Device XX is currently offline, please check its power and network connection" and do not proceed further
   - Only continue when `result` is valid and `online` is `true`
   - The `properties` field contains current values of each functional property (e.g. switch state, brightness, temperature)

3. **Query capabilities** — Call the "Query Device Thing Model" API to get the device's supported property list
   - **Important**: The `result.model` field is a JSON **string** that must be parsed again (e.g. `json.loads(result["model"])`) to obtain the property definitions
   - Check each property's `accessMode`:
     - `ro` (read-only): cannot be controlled, only queried — inform the user "this property is read-only"
     - `wr` (write-only): can be controlled but current value cannot be read
     - `rw` (read-write): can be both controlled and queried

4. **Map the command** — Map the user's intent to Thing Model properties:
   - Turn on/off → find a bool-type switch property (e.g. `switch_led`, `switch`)
   - Adjust brightness → find a value-type brightness property
   - Adjust temperature → find a value-type temp property
   - If the device does not support the requested function, inform the user and list supported functions
   - **Relative adjustments** — When the user says "a bit brighter", "lower the temperature by 2 degrees", etc.:
     1. Read the current value from `properties` in the device detail (Step 2)
     2. Read `min`, `max`, `step` from the Thing Model `typeSpec` (Step 3)
     3. Calculate the target value:
        - Vague ("a bit", "a little") → current value ± (max - min) × 10%
        - Specific ("by 2 degrees", "by 100") → current value ± the specified amount
     4. Clamp the target value within [min, max] and round to the nearest `step`
   - **Validate value range**: Before issuing, confirm the target value is within the `typeSpec` min/max range

5. **Issue the command** — Call the "Issue Properties" API using the Python SDK: `api.issue_properties(device_id, {property_code: value})`
   - The SDK handles `properties` JSON string serialization automatically
   - If not using the SDK: the `properties` field must be a JSON **string**, not a JSON object. You must double-serialize: `{"properties": "{\"switch_led\":true}"}`

6. **Verify and return result** — After issuing the command:
   - Wait 1-2 seconds, then call "Get Device Detail" again to read the updated `properties`
   - Compare the target value with the actual value to confirm execution
   - If values match: inform the user the operation succeeded
   - If values differ: tell the user "command sent, but the device state has not updated yet — there may be a delay"

### Workflow 2: Rename Device

1. Locate the device using Workflow 1 Step 1 to obtain the device_id
2. Call the "Rename Device" API with the new name
3. Return the result

### Workflow 3: Notifications

1. Identify the message type: Email / App Push
2. Extract required parameters (message content; email and push also need a subject)
3. Call the corresponding API (all notification APIs are self-send — messages can only be sent to the current logged-in user)
4. Return the send result

### Workflow 4: Weather Query

1. **Obtain coordinates**:
   - First call Home List API and check the `latitude` / `longitude` fields
   - **Note**: the coordinate format is `{"Value": "30.3"}` — you must extract the `.Value` field (e.g. `home["latitude"]["Value"]`)
   - If the home has no location set, ask the user for their city and convert to coordinates (see common city coordinates in `references/weather.md`)
2. Determine which weather attributes to query (default: temperature, humidity, weather condition)
3. Call the weather query API
4. Translate the returned data into a human-readable description

### Workflow 5: Data Statistics

1. Locate the device (same as Workflow 1 Step 1)
2. Call the "Statistics Config Query" API to confirm whether the device has the corresponding statistics capability
3. If available, call the "Statistics Value Query" API
   - **Time inference**: Convert the user's natural language to `yyyyMMddHH` format:
     - "today" → start = today 00:00, end = current hour
     - "yesterday" → start = yesterday 00:00, end = yesterday 23:00
     - The time range cannot exceed 24 hours per request — for longer ranges, make multiple requests and aggregate
     - Format example: `2024010100` = January 1, 2024 00:00
4. Aggregate and return the results

### Workflow 6: Device Status Query

When the user asks "Is the living room light on?" or "What's the AC set to?":

For infrared appliances, these APIs do not provide confirmed appliance state. Explain this limitation instead of treating gateway properties or the last dispatched key as the appliance's current state.

1. Locate the device and get current state (same as Workflow 1 Steps 1-2; stop if device not found or offline)
2. Read `properties` values, cross-reference with the Thing Model property names/descriptions, and translate to natural language (e.g. `"switch_led": true` → "the light is currently on")

### Workflow 7: Multi-Device Batch Control

When the user says "Turn off all lights" or "Set all ACs to 26 degrees":

1. Call "List All Devices" API and filter matching devices by `category_name` or device `name` keyword
2. For each matching device: apply the Device Control Scope and Workflow 1 Steps 2-6, skipping offline or security-restricted devices. Use Workflow 10 for infrared appliances; report dispatch separately from verified execution
3. Aggregate results: report how many devices succeeded, which ones failed or were offline
4. Add a brief delay (0.5-1s) between requests to avoid rate limiting

### Workflow 8: IPC Cloud Capture

When the user asks to "take a photo with the camera" or "record a short video from the camera":

1. **Locate the IPC device** — same as Workflow 1 Step 1, filter by camera category
2. **Determine capture type**:
   - Snapshot → `PIC` (optional `pic_count`, 1-5)
   - Short video → `VIDEO` (optional `video_duration_seconds`, 1-60, default 10)
3. **Execute capture** — Use the all-in-one helper methods:
   - For PIC: `api.ipc_ai_capture_pic_allocate_and_fetch(device_id, pic_count=1)`
   - For VIDEO: `api.ipc_ai_capture_video_allocate_and_fetch(device_id, video_duration_seconds=5)`
   - Invoke the helper once. It allocates once, waits, then makes one resolve request and at most **two retries** on `NOT_READY` (three resolve requests total). All attempts use the same allocation; SDK/HTTP and agent retries must not be stacked.
4. **Return the capture result** — Follow **IPC Media Output (`media_info`)** above:
   - PIC with consent: output `resolve["decrypt_image_url"]` as a `type: "image"` media item
   - VIDEO with consent always prints the complete `resolve["decrypt_video_url"]` visibly on its own line. For a video-only request, output no media item, video card, `present_files` call, or cover-related content.
   - If the same VIDEO request explicitly asks for the cover, a photo, a still image, or a snapshot, additionally emit exactly one `type: "image"` `<media_info>` item using `resolve["decrypt_cover_image_url"]`. Never leave the requested cover/photo blank. Do not emit a video `<media_info>` item or pass either URL to `present_files`.
   - If an explicitly requested cover URL is unavailable, report that fact without an empty media item and without retrying solely for the cover; the mandatory video URL still remains in the final answer.
   - Do not download the video merely for display or delivery, and do not return a `/data/workspace/` path. Keep PIC delivery unchanged through image `media_info`.
   - Treat the helper's return as the end of this attempt. If `status` is still `NOT_READY` or the expected decrypted URL is missing, do not emit `media_info`; report that no usable media was returned and that this request has stopped. Do not restart capture or continue polling.
   - On `1199`, HTTP `429`, or any other IPC error, report the failure and stop immediately under **Retry Budget and Mandatory Stop**. Do not wait for a rate limit to clear automatically.

### Workflow 9: IPC Visual Recognition

When the user asks "What's in front of my camera?", "Is there anyone at the door?", or "Describe what the camera sees":

1. **Capture a snapshot** — Follow Workflow 8 Steps 1-3 to take a PIC capture
2. **Get the image URL** — Extract `resolve["decrypt_image_url"]` from the capture result. If the resolve failed or returned `NOT_READY`, inform the user and stop
3. **Download and save the image for internal analysis** — Fetch the image content from the decrypted URL and save it under `/data/workspace/`, following **Image File Storage for Internal Processing (Sandbox)** above. This local file is only model input and must not be returned as the user-facing media result. Stop and report the error if downloading or saving fails.
4. **Send to AI vision model** — Load the verified local image using its absolute path and pass it to the AI large model for visual understanding. Describe the image content in natural language based on the user's question:
   - General question ("What's there?") → describe the overall scene, objects, and people
   - Specific question ("Is there a package?", "Is anyone at the door?") → focus on answering the specific question
5. **Return the description** — Respond to the user with the visual analysis result in conversational language. If the captured snapshot is also presented, output it through `media_info` using `resolve["decrypt_image_url"]`; never present the local analysis path or raw URL instead

### Workflow 10: Infrared Device Control

When the user says "turn on the living room TV" or "turn up the TV volume":

1. **Locate the remote** — Locate an online authorized infrared gateway, then call `ir_remotes <gateway_device_id>`. Match the requested appliance by returned `remoteName`; if multiple records match, ask the user to choose. Use that record's `remoteId`, `categoryId`, `brandId` and `remoteIndex`; never guess IDs or reuse them from another gateway.
2. **Check availability** — Query the gateway detail and apply the same online/authorization checks as Workflow 1 Step 2. Here `device_id` is the gateway ID; `remote_id` identifies the virtual appliance remote.
3. **Determine capabilities** — Call `ir_keys <gateway_device_id> <remote_id>` before control. Use `keyList[].key` exactly as returned; do not infer a key from a generic name. For air conditioners, validate mode, temperature and fan speed against `keyRange`.
4. **Map the command** — Use the returned `categoryId`, `remoteIndex` and supported `key`. If `duplicatePower` is true or only `Power` exists, it is a toggle key: explain that actual on/off state cannot be verified before dispatching it.
5. **Issue the command** — Run `ir_control <device_id> <remote_id> <category_id> <key>`, or `ir_control_raw` with `--key` / `--key_id` for a known raw key. SDK: `api.send_standard_command(device_id, remote_id, category_id, key)`.
6. **Return the result** — Report "command sent" when successful. Infrared APIs do not confirm appliance state; do not use gateway properties as verification or automatically resend a toggle/relative command after an uncertain result. Mask all device, remote and home IDs in user-facing output unless the user explicitly needs them.

### Workflow 11: Pair an Infrared Remote

When the user asks to add or pair an appliance remote:

1. Locate the infrared gateway and check availability as in Workflow 10 Steps 1-2.
2. Query categories → brands → code-library indexes with `ir_categories`, `ir_brands` and `ir_indexes`. Use the actual returned IDs; brand/index queries default to country `CN`.
3. Test a candidate with `ir_test` or `ir_test_raw`, then ask whether the appliance responded. Try the next index only after a failed physical response.
4. Once matched, call `ir_add` with the remote name. Return the new `remote_id` and its gateway/category/index association for subsequent control. The CLI does not persist this association automatically.

See `references/remote-management.md` for lookup and addition parameters.

### Workflow 12: Rename or Delete an Infrared Remote

1. Locate the intended remote and gateway using Workflow 10 Step 1.
2. Run `ir_rename <device_id> <remote_id> <new_name>` or `ir_delete <device_id> <remote_id>` according to the user's request.
3. Return the result. These operations affect the virtual remote, not the physical gateway.

## Important Notes

1. Device name matching uses fuzzy matching; when multiple results are found, ask the user to confirm
2. The statistics API time format is `yyyyMMddHH`, and the time range cannot exceed 24 hours per request
3. Both notification APIs are self-send only — messages can only be sent to the currently logged-in user
4. The weather query requires latitude and longitude; if unavailable from the Home API, ask for the user's city
5. The default base URL is `https://openapi.tuyacn.com`; override `TUYA_BASE_URL` only for an approved alternative gateway
6. If you encounter issues, visit https://github.com/tuya/tuya-openclaw-skills for announcements and troubleshooting
7. Never log or display `TUYA_ACCESS_TOKEN` or `TUYA_CLIENT_ID` values in output
8. CLI exits with code `2` for usage/validation errors, and `1` for runtime/API/network errors

## Supported and Unsupported Operations

### Supported Property Types for Control

Only basic data type properties are currently supported for device control:

| Type | Description | Example |
|------|-------------|---------|
| bool | Boolean on/off | Turn light on/off, turn AC on/off, turn plug on/off |
| enum | Enumeration selection | Switch AC mode (auto/cold/hot), set fan speed (low/mid/high) |
| value (Integer) | Numeric value | Adjust brightness (0-1000), set temperature (16-30) |
| string | String value | Set device display text |

### Unsupported Operations

The following operations involve sensitive actions or complex data types and are **NOT supported**:

- **Lock control** — Unlock doors, lock/unlock smart locks (security-sensitive)
- **Live video streaming** — Pull real-time video streams or view camera live footage (cloud snapshot/short video capture IS supported — see Workflow 8)
- **Image operations** — Retrieve or push images from/to devices
- **Complex data type control** — Properties with `raw`, `bitmap`, `struct`, or `array` typeSpec are not supported for issuing commands
- **Firmware upgrades** — OTA firmware update operations
- **Hardware device pairing/removal** — Adding or removing physical devices; infrared virtual remote pairing/addition/removal is supported via Workflows 11-12
- **Infrared learning/upload** — Custom infrared code learning or upload is not supported

If the user requests any of these unsupported operations, clearly inform them that the operation is not available through this skill and suggest using the Tuya App directly.

## Data Egress Statement

**This skill sends data to the Tuya Open Platform**:

| Data Type | Sent To | Purpose | Required |
|-----------|---------|---------|----------|
| Access token and client ID | User-configured base_url | API authentication | Required |
| Device ID | User-configured base_url | Device query and control | Required |
| Control commands | User-configured base_url | Device property issuance and infrared dispatch | Required |
| Infrared category, brand, code index, remote ID/name and keys | User-configured base_url | Code-library lookup and virtual remote management | For infrared operations |
