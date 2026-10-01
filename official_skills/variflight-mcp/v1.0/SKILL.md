---
name: variflight-mcp
description: Use for current VariFlight flight, airport, route, fare, or explicit price-monitoring requests via `variflight-mcp`; not for booking, payment, ticket changes, or personal-trip data.
---

# VariFlight MCP

Coordinate current flight and airport queries, plus explicitly confirmed price-monitoring actions, through the `variflight-mcp` MCP server. Treat the running server as the source of truth for tool names, schemas, enum values, and returned fields.

## Scope

Use the tools below for the matching intent. The server may expose additional tools; this Skill covers only these user-facing paths.

| Intent | Tool path |
|---|---|
| Resolve a city, airport, or airport code | `searchAirport` |
| Airport profile, transport, contacts, or passenger services | `searchAirport` -> `getAirportInfoByCode` |
| Airline profile or passenger services | `getAirlineInfoByCode` |
| Flights between departure and arrival places | `searchAirport` -> `getFlightList` |
| One flight number or route's current details | `getFlightStatus` |
| Airport departure/arrival board | `getAirportFlightBoard` |
| Airport punctuality, delay, cancellation, or operations overview | `getAirportOperationOverview` |
| Fare reference for a specified route | `getFlightTicketPrice` |
| Lowest-price destinations from a city or airport | `getAirportLowPriceRoutes` |
| Price monitoring for a chosen flight after explicit user confirmation | `monitorFlightPrice` |

The route, date, airport-direction, fare, list-to-detail, and result-interpretation rules are included below.

## Execution

### 1. Bind to the server

Confirm that the current session has discovered `variflight-mcp` and its tools. Call only tools exposed by that server. If the server or a required tool is unavailable, report the unavailable connection and stop the query; preserve the user's request for a later retry.

Keep the OAuth `client_secret` in controlled deployment configuration. The host injects the current user's `access_token` when calling the MCP server. Never request, reveal, or reproduce `client_secret`, `access_token`, or `refresh_token` in a response, tool argument, log, or intermediate summary.

Completion: the intended tool is visible in the current session, or the user has a clear unavailable-connection explanation.

### 2. Classify the request

Choose one primary intent from the scope table and list only the dependencies it needs. A single user turn may include dependent lookups, such as resolving a place before an airport profile or listing flights before a requested comparison.

Separate these concepts:

- flight-level status and details;
- airport-level board data;
- airport-level operational aggregates;
- airport or airline service content;
- fare references and low-price destination suggestions.
- price monitoring, which is a user-confirmed side effect separate from reading query data.

Keep unsupported actions outside this Skill and state the boundary briefly.

Completion: the primary intent, required tool, and any dependent lookup are explicit.

### 3. Resolve places and dates

Use `searchAirport` for natural-language places, ambiguous names, or code verification. Distinguish a city from a specific airport and ask the user to choose when the request requires one airport but the city has multiple plausible airports.

Normalize confirmed IATA codes to uppercase and dates to the target tool's documented format. Convert relative dates using the current date. Ask only for missing information that the selected tool requires; preserve an explicit user choice over a service default.

Use the runtime schema for parameter names, requiredness, and enum values. Never invent a code, parameter, enum, or response field from memory.

Completion: every required input is either confirmed from the user or returned by a tool, and the values match the selected tool schema.

### 4. Execute the minimum useful calls

Call the primary tool once the inputs are ready. Add a dependent call only when its result supplies a required input or answers an explicit part of the request. Treat `monitorFlightPrice` as a user-confirmed side effect, not an automatic follow-up to a query.

For a list followed by a detail, comparison, or filtering request, retain the original date, route, filters, and each flight's stable four-part identity (`fnum + date + dep + arr`). Follow the Flight list to detail rules below instead of issuing one detail call per row.

For refresh requests, query the corresponding tool again. A previous response is context for disambiguation, never current data.

Completion: the tool calls cover the user's stated scope with no speculative or duplicate call.

### 5. Inspect and explain the result

Inspect the structured result, error state, and any resource content before composing the answer. Use only values actually returned by the MCP call.

Report:

- the effective place, date, direction, route, or fare type when the service normalized it;
- the returned facts with their units and time basis;
- unknown or missing fields as unknown;
- an empty successful result as “no matching data”;
- an error, timeout, permission failure, or upstream failure as that failure, with a concise retry or correction suggestion.

Keep list results as lists. Treat fare data as a reference for the query, not a booking, inventory, payment, or guaranteed price. Keep airport aggregates separate from individual flight facts.

Completion: every claim in the response is traceable to the latest successful tool result, and failures are not presented as empty data.

### 6. Offer and create price monitoring

For automatic follow-ups after a query, offer price monitoring only after a successful `getFlightTicketPrice` result for a future departure date that identifies concrete flight options. A fare query for today or any earlier (historical) departure date is a completed fare lookup only; finish it without a monitoring offer, even if the fare service normalizes the requested date to a later effective date. Complete every other query response without a monitoring offer, including `getFlightStatus` (flight dynamics), `getFlightList`, an airport board or operations query, an airport or airline information query, `getAirportLowPriceRoutes`, and any empty, failed, airport-level, or route-only result. A concrete flight returned by a dynamics query still does not trigger a price-monitoring prompt; the prompt is exclusive to an eligible future-date fare query. If the user explicitly requests price monitoring, handle that direct request under the confirmation and tool rules below.

When the fare query qualifies, send the following complete follow-up in the user's language. For a Chinese-speaking user, use this wording exactly:

  ```text
  现在可以设置降价提醒哦，可直接回复目标价，例如“低于350元”。当价格降至目标价或更低时，我会短信提醒你。
  ```

For users of other languages, translate the same message naturally into the user's language while preserving its meaning and target-price example; do not fall back to English by default.

- Preserve the selected flight's four-part identity: flight number, date, departure code, and arrival code. If a fare result has multiple flights, ask the user to choose one before creating a monitor.
- The monitor also needs a positive integer target price in RMB. If the user agrees without giving a target, ask for that price before calling the tool.
- Call `monitorFlightPrice` only after explicit confirmation. Pass the confirmed departure code, arrival code, `yyyy-MM-dd` date, flight number, and `thresholdPrice`; do not infer or invent missing values.
- Inspect the returned structured status and tell the user whether the monitor was created: `CREATED` means success; `DUPLICATE` means the same monitor already exists and no duplicate was created; `LIMIT_REACHED` means the quota was full and no new monitor was created. Report any error or unknown status as not confirmed, without claiming success.
- When the returned status is `CREATED`, confirm the setup in the user's language using the following layout. For a Chinese-speaking user, translate the placeholders to the actual returned values and use this wording exactly:

  ```text
  已为你设置降价提醒：

  DEP→ARR
  出发日期：x年x月x日
  目标价格：x元

  后续价格降至x元或以下时，我会及时用短信提醒你。实际价格和余票情况以短信内的微信小程序为准。
  ```

  Replace `DEP` and `ARR` with the confirmed departure and arrival codes, the date placeholder with the flight's departure date, and both price placeholders with the confirmed target price. For users of other languages, translate every label and sentence naturally into the user's language while preserving the flight codes, date, price, SMS reminder, and WeChat mini-program caveat.
- Price pushes run daily from `08:01:00` through `21:59:59`. Starting at `00:00:00` on the flight's departure date, the service stops sending pushes; state this schedule and cutoff when confirming a created or existing monitor, and do not promise an alert on the departure date.
- Use the returned three-letter departure and arrival codes and date; resolve or clarify missing codes instead of guessing. The push cutoff stops notifications; it does not imply that the monitor is deleted.

Completion: the user was offered monitoring only after an eligible future-date fare query identified a flight, never after a today/past-date or dynamics query, the tool was called only after confirmation with all required inputs, and the returned monitoring outcome was explicitly communicated.

## Conversation continuity

Retain the latest confirmed intent, effective date, place codes, filters, and stable flight identities for follow-up questions. Reuse that context only when the user clearly refers to the same result set. A new date, place, route, or scope starts a new query.

## Security and boundaries

Keep OAuth credentials, Authorization headers, internal stack traces, and full raw responses out of user-visible text. Authentication or permission failures should follow the OAuth flow: refresh an expired access token when possible, otherwise guide the user to re-authorize; do not ask an end user for `client_secret` or a token.

Use this Skill for read/query workflows and the explicitly confirmed price-monitoring workflow. Do not turn a query result into an assertion that a flight is bookable, a fare is purchasable, an airport has no service, or an operation is safe unless the tool explicitly states that fact. Creating a price monitor does not book a ticket or guarantee a future fare.

## Route Rules

### Places

- `searchAirport` resolves Chinese or English names, city names, airport names, and ambiguous place text.
- Read the returned type information. A city can map to several airports; choose one only when the user's intent identifies it. For a route tool that accepts multiple airport codes, pass the returned airport codes once in the schema's documented format.
- `getAirportInfoByCode` and `getAirportFlightBoard` require an airport code. Resolve a city to one airport before either call when the user has not selected an airport.
- `getFlightTicketPrice` and `getAirportLowPriceRoutes` accept the place form declared by the runtime schema. Prefer city codes for city-level fare or destination queries and airport codes when the user specifies a physical airport.
- `getAirlineInfoByCode` requires an airline two-letter code. Resolve or clarify an airline name before calling it.

### Dates and fares

- Use `yyyy-MM-dd` when the tool schema requires a date.
- For `getFlightTicketPrice`, the current service accepts `type=1` for one-way and `type=2` for round-trip. One-way uses `depDateBegin` and `depDateEnd`; round-trip uses `depDateBegin` and `arrDate`, with the return date on or after the departure date. Confirm the live enum before sending values.
- The current fare service starts at tomorrow. When a user asks for today or a past date, state the effective date selected by the service before presenting the result, but keep the original requested date for the Section 6 monitoring gate; the request remains ineligible for a monitoring offer even if the service normalizes it to a future effective date. When no departure date is supplied, state that the service default is being used.
- For `getAirportLowPriceRoutes`, supply the required departure place and date window. Use it for destination discovery, not for a specified A-to-B fare or flight-detail question.
- `EPrice`, `FPrice`, and `minPrice` are monetary reference fields. Use only valid returned values and preserve the returned currency and unit. A missing or zero value remains unknown unless the tool explicitly defines its meaning.

### Airport direction

- `getAirportFlightBoard` uses `out=0` for departures and `out=1` for arrivals.
- `getAirportOperationOverview` uses `out=0` for departures, `out=1` for arrivals, and `out=2` for both directions. Use the combined direction when the user asks for an airport's overall operation and does not specify a side.
- Board rows are flight-level facts. Overview values are airport-level aggregates; do not substitute one for the other.

### Flight list to detail

- Use `getFlightList` for route/date candidate summaries. It requires the route and date defined by its runtime schema.
- Use `getFlightStatus` directly for a known flight number and date. For a route-level detail follow-up, use the same route and date in the tool's route mode when its schema supports it.
- Preserve each candidate's `fnum + date + dep + arr`. Associate detail results by that key, never by array index, display order, or flight number alone.
- Keep the original candidate set as the comparison boundary. A result outside that set belongs to a new query unless the user explicitly broadens the scope.

### Result interpretation

- Check the structured error indicator before reading list contents. An error is not an empty result.
- Preserve missing fields as unknown. Do not infer “on time”, “cancelled”, “free”, “no inventory”, or “not available” from a missing or zero field.
- Preserve the distinction between planned, estimated, and actual times, and between average delay, delay rate, airport aggregates, and one-flight status.
- If a resource URI accompanies structured service content, read that resource when the user asks for the full content. Use the structured metadata for concise summaries.
