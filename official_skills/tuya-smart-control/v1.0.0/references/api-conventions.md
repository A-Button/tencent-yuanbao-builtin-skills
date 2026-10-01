# API Conventions

## Authentication and Endpoint

The default API endpoint is China: `https://openapi.tuyacn.com`.

Each REST request must include:

```http
Authorization: Bearer {access_token}
client_id: {client_id}
```

Set `TUYA_BASE_URL` only when the access token belongs to a different approved API gateway.

## Request Format

All APIs use the configured Base URL concatenated with the path. Examples:

```
GET {base_url}/v1.0/end-user/homes/all
POST {base_url}/v1.0/end-user/devices/{device_id}/shadow/properties/issue
```

Authentication is via `Authorization: Bearer {access_token}` and `client_id` headers (handled automatically by the Python SDK).

## Response Format

APIs return a unified structure:

**Success response**:
```json
{
  "success": true,
  "t": 1710234567890,
  "result": { ... }
}
```

**Error response**:
```json
{
  "success": false,
  "code": 1108,
  "msg": "uri path invalid"
}
```

- When `success` is `true`, the result is in the `result` field
- When `success` is `false`, error details are in the `code` and `msg` fields
- The Python SDK automatically checks `success` and raises `TuyaAPIError` on failure
- Non-IPC REST calls and infrared GET queries retry HTTP 429 and transient 5xx responses with backoff, at most **two retries** after the first request. Do not add agent-level retries after the SDK returns.
- IPC allocate/resolve requests have **no HTTP-layer retries or redirects**. Allocate is issued once; only the bounded capture helper may retry a `NOT_READY` resolve, at most twice (three resolve requests total). Rate limits, authentication failures and other IPC errors propagate immediately and stop the attempt.
- Infrared POST/PUT/DELETE operations are not retried automatically because repeated keys may toggle power or repeat relative adjustments.
