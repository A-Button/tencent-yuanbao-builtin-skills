# Notifications

All notification APIs are **self-send** mode — they can only send messages to the currently logged-in user.

## 1. Send Email

Send an email to the current user's bound email address.

**Request**

```
POST /v1.0/end-user/services/mail/self-send
```

**Request Body**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| subject | String | Yes | Email subject |
| content | String | Yes | Email body |

**Request Example**

```json
{
  "subject": "Device Offline Notification",
  "content": "Your living room smart air conditioner has gone offline. Please check the device network connection."
}
```

**Error Codes**

| Code | Description |
|------|-------------|
| 30001 | Invalid email address |
| 30002 | Same email exceeded 30 emails within 24 hours |
| 30003 | Same email sent identical content more than 2 times within 50 seconds |
| 30004 | Can only send emails to the email address bound to this account |

---

## 2. Send App Push Notification

Send an App notification bar push to the current user.

**Request**

```
POST /v1.0/end-user/services/push/self-send
```

**Request Body**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| subject | String | Yes | Push notification title |
| content | String | Yes | Push notification content |

**Request Example**

```json
{
  "subject": "Security Alert Notification",
  "content": "Your porch smart camera detected a moving object. Please check the live feed."
}
```

**Error Codes**

| Code | Description |
|------|-------------|
| 50001 | Can only send push notifications to this account |

---

## Common Error Codes

The following error codes apply to all notification APIs:

| Code | Description |
|------|-------------|
| 500 | System error |
| 10001 | Invalid parameter |
| 10010 | End user does not exist |
| 10011 | End user has no bound contact method |
