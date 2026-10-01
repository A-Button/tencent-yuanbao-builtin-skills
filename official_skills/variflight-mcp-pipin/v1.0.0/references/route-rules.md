# Route Rules

Use this file only for the matching workflow branch. The live `tools/list` schema and the tool result take precedence if they differ.

## Places

- `searchAirport` resolves Chinese or English names, city names, airport names, and ambiguous place text.
- Read the returned type information. A city can map to several airports; choose one only when the user's intent identifies it. For a route tool that accepts multiple airport codes, pass the returned airport codes once in the schema's documented format.
- `getAirportInfoByCode` requires one airport code. `getAirportFlightBoard` is also an airport-specific query. Resolve a city to one airport before either call when the user has not selected an airport.
- `getFlightTicketPrice` and `getAirportLowPriceRoutes` accept the place form declared by their runtime schema. Prefer city codes for city-level fare or destination queries and airport codes when the user specifies a physical airport.
- `getAirlineInfoByCode` requires an airline two-letter code. Resolve or clarify an airline name before calling it.

## Dates and fares

- Use `yyyy-MM-dd` when the tool schema requires a date.
- For `getFlightTicketPrice`, the current service accepts `type=1` for one-way and `type=2` for round-trip. One-way uses `depDateBegin` and `depDateEnd`; round-trip uses `depDateBegin` and `arrDate`, with the return date on or after the departure date. Confirm the live enum before sending values.
- The current fare service starts at tomorrow. When a user asks for today or a past date, state the effective date selected by the service before presenting the result. When no departure date is supplied, state that the service default is being used.
- For `getAirportLowPriceRoutes`, supply the required departure place and date window. Use it for destination discovery, not for a specified A-to-B fare or flight-detail question.
- `EPrice`, `FPrice`, and `minPrice` are monetary reference fields. Use only valid returned values and preserve the returned currency/unit. A missing or zero value remains unknown unless the tool explicitly defines its meaning.

## Airport direction

- `getAirportFlightBoard` uses `out=0` for departures and `out=1` for arrivals.
- `getAirportOperationOverview` uses `out=0` for departures, `out=1` for arrivals, and `out=2` for both directions. Use the combined direction when the user asks for an airport's overall operation and does not specify a side.
- Board rows are flight-level facts. Overview values are airport-level aggregates; do not substitute one for the other.

## Flight list to detail

- Use `getFlightList` for route/date candidate summaries. It requires the route and date defined by its runtime schema.
- Use `getFlightStatus` directly for a known flight number and date. For a route-level detail follow-up, use the same route and date in the tool's route mode when its schema supports it.
- Preserve each candidate's `fnum + date + dep + arr`. Associate detail results by that key, never by array index, display order, or flight number alone.
- Keep the original candidate set as the comparison boundary. A result outside that set belongs to a new query unless the user explicitly broadens the scope.

## Result interpretation

- Check the structured error indicator before reading list contents. An error is not an empty result.
- Preserve missing fields as unknown. Do not infer “on time”, “cancelled”, “free”, “no inventory”, or “not available” from a missing or zero field.
- Preserve the distinction between planned, estimated, and actual times, and between average delay, delay rate, airport aggregates, and one-flight status.
- If a resource URI accompanies structured service content, read that resource when the user asks for the full content. Use the structured metadata for concise summaries.
