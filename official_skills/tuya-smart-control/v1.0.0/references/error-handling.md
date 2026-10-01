# Error Handling

## Common Error Scenarios

| Scenario | How to Handle |
|----------|--------------|
| Device not found (`result` is `null`) | Tell the user: "Cannot find a device named XX, please verify the device name" |
| Device offline (`online` is `false`) | Tell the user: "Device XX is currently offline, please check its power and network connection." Do not attempt to issue commands |
| Device does not support the function | Tell the user: "Device XX does not support XX function", and list the device's supported functions |
| Home/room not found | Tell the user: "Cannot find a home/room named XX" |
| Multiple devices match | List all matching devices with room information and ask the user to choose |
| Notification send failure | Return the specific error code explanation (rate limit, format error, etc.) |
| Property value out of range | Tell the user: "The value XX is outside the supported range (min-max). Please provide a value within range" |
| Read-only property (`accessMode: ro`) | Tell the user: "This property is read-only and cannot be controlled" |
| Invalid CLI JSON input (`control` / `weather` codes) | Return clear parameter error and ask user to provide valid JSON |
| Invalid statistics time window (`stats_data`) | Tell the user start/end must use `yyyyMMddHH`, end >= start, and window <= 24 hours |

## API Error Codes

| Code | Message | Description | Recovery |
|------|---------|-------------|----------|
| 1010 | token invalid | Access token is invalid or expired | Tell the user the access token needs to be refreshed |
| 1108 | uri path invalid | API path is incorrect | Check whether the API path is correct |
| 10001 | Invalid parameter | Request parameter error | Verify the parameters format and values |
| 10010 | End user does not exist | User account issue | Check the access token and client ID are valid |
| 10011 | End user has no bound contact | Missing email | Tell the user to bind a contact method in the Tuya App |
| 40000901 | The device does not exist | Device not found | Verify the device_id |
| 40000903 | The modelId of the device does not exist | Device model not found | Device may not support Thing Model queries |
| 1199 | your requests are too frequent | API rate limited | Stop the current request; do not automatically wait and retry |
| 500 | System error | Server-side error | IPC: stop immediately. Other retryable REST calls: SDK-owned retries only, at most two; no outer retry loop |
| 429 | Too Many Requests | API rate limited | IPC: stop immediately. Other retryable REST calls: SDK-owned backoff/`Retry-After`, at most two retries; no outer retry loop |

> API error codes may appear as numeric integers (e.g. `1010`) or string identifiers (e.g. `"DEVICE_NOT_EXIST_V2"`) depending on the endpoint. Handle both forms when matching error codes.

## Notification-Specific Error Codes

For channel-specific error codes (Email, App Push), see `references/notifications.md`.

## General Recovery Strategy

For IPC, only a `NOT_READY` result can be retried by the capture helper, at most twice after the first resolve. Once the helper returns, the current attempt is over, even if its process exits successfully. Missing media URLs, exhausted retries, API/network errors, and uncertain execution results must not trigger another capture, a different entry point, or a delayed/background job. A new capture requires a new explicit user request. See **Retry Budget and Mandatory Stop** in `SKILL.md`.

When encountering an unresolvable error, guide the user to visit the GitHub repository for the latest announcements and troubleshooting: https://github.com/tuya/tuya-openclaw-skills

## CLI Error Output Contract

The command-line SDK outputs a standardized error block to `stderr`:
- `Error`: human-readable error message
- `Command`: command name
- `Args`: argument summary (JSON)
- `TuyaErrorCode` and `Suggestion`: included when Tuya API returns a known error code

Exit codes:
- `2`: usage or parameter validation error
- `1`: runtime/API/network error
