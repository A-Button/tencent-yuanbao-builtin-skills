---
name: variflight-mcp-pipin
description: Use for Yuanbao requests that need current VariFlight data through the `variflight-mcp` server, including flight status or lists, airport boards or operations, airport or airline services, route discovery, and fare references. Use only when that MCP server is available. Do not use for route booking, payment, ticket changes, personal-trip data, flight following, or other unsupported actions.
version: v1.0.0
---

# VariFlight MCP

Coordinate current flight and airport queries through the `variflight-mcp` MCP server. Treat the running server as the source of truth for tool names, schemas, enum values, and returned fields.

## Scope

Use the query tools below for the matching intent. The server may expose additional tools; this Skill covers only these user-facing query paths.

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

Read [references/route-rules.md](references/route-rules.md) before executing a route, date, airport-direction, fare, or list-to-detail workflow.

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

Keep unsupported actions outside this Skill and state the boundary briefly.

Completion: the primary intent, required tool, and any dependent lookup are explicit.

### 3. Resolve places and dates

Use `searchAirport` for natural-language places, ambiguous names, or code verification. Distinguish a city from a specific airport and ask the user to choose when the request requires one airport but the city has multiple plausible airports.

Normalize confirmed IATA codes to uppercase and dates to the target tool's documented format. Convert relative dates using the current date. Ask only for missing information that the selected tool requires; preserve an explicit user choice over a service default.

Use the runtime schema for parameter names, requiredness, and enum values. Never invent a code, parameter, enum, or response field from memory.

Completion: every required input is either confirmed from the user or returned by a tool, and the values match the selected tool schema.

### 4. Execute the minimum useful calls

Call the primary tool once the inputs are ready. Add a dependent call only when its result supplies a required input or answers an explicit part of the request.

For a list followed by a detail, comparison, or filtering request, retain the original date, route, filters, and each flight's stable four-part identity (`fnum + date + dep + arr`). Follow the list-to-detail rules in the reference instead of issuing one detail call per row.

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

## Conversation continuity

Retain the latest confirmed intent, effective date, place codes, filters, and stable flight identities for follow-up questions. Reuse that context only when the user clearly refers to the same result set. A new date, place, route, or scope starts a new query.

## Security and boundaries

Keep OAuth credentials, Authorization headers, internal stack traces, and full raw responses out of user-visible text. Authentication or permission failures should follow the OAuth flow: refresh an expired access token when possible, otherwise guide the user to re-authorize; do not ask an end user for `client_secret` or a token.

Use this Skill for read/query workflows. Do not turn a query result into an assertion that a flight is bookable, a fare is purchasable, an airport has no service, or an operation is safe unless the tool explicitly states that fact.
