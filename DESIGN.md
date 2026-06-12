# Design document for the project's major components

## callsignLookup

A module that, given an aircraft callsign (e.g. `AAL1599`), returns the airline name and route (origin + destination airports with ICAO codes, names, cities, countries, and coordinates).

### Files

```
callsignLookup.py            # main module — importable library + CLI
data/
  List_of_airline_codes.csv  # Wikipedia airline codes table (IATA, ICAO, Airline, ...)
requirements.txt             # requests (everything else is stdlib)
config.example.json          # copy to config.json and fill in API keys
```

---

### Architecture

```
callsign
  │
  ▼
RouteCache (SQLite)  ──hit──▶  FlightRoute
  │
 miss
  │
  ▼
Service chain (in order, skip unavailable)
  1. AirLabs
  2. AeroDataBox
  3. FlightAware
  4. AviationStack
  5. OpenSky  ← last resort; indirect route lookup
  │
  ▼
Airline name fallback: prefix match against data/List_of_airline_codes.csv
  │
  ▼
RouteCache.put() + return FlightRoute
```

A service is marked unavailable for the session when it returns a rate-limit signal. Services are used in order until one succeeds or all are exhausted. "Not found" from a service is not fatal; the next service is tried.

Services are tried in order. A service is skipped for the remainder of the session when it returns a rate-limit signal. Any service that returns no route (not found, partial, or error) causes the next service to be tried. The loop stops only when a service returns a route with both origin and destination, or all services are exhausted.

If no service returns a complete route but the callsign prefix matches a known ICAO airline code, a partial `FlightRoute` (airline name, no airports) is returned but not cached.

---

### Cache

SQLite file, default `~/.aircrafttracker/routes.db`. Created automatically. Schema:

```sql
CREATE TABLE routes (
    callsign       TEXT PRIMARY KEY,
    airline        TEXT,
    origin_icao    TEXT,  origin_name    TEXT,  origin_city    TEXT,
    origin_country TEXT,  origin_lat     REAL,  origin_lon     REAL,
    dest_icao      TEXT,  dest_name      TEXT,  dest_city      TEXT,
    dest_country   TEXT,  dest_lat       REAL,  dest_lon       REAL,
    cached_at      TEXT
);
```

The cache is permanent (no TTL). Use `--flushCache` to clear all rows.

Only routes with both origin and destination populated are written to the cache. Airline-only results (no airports) are returned to the caller but not persisted.

---

### Services

#### 1. AirLabs: `https://airlabs.co/api/v9/`
Best free-tier option for direct route lookup.
Must create a (free) account at `https://airlabs.co`.
- Auth: `?api_key=` query param
- Route: `GET /flights?flight_icao={callsign}` → `dep_icao`, `arr_icao`
- Airport detail: `GET /airports?icao_code={code}` → name, city, country, lat, lng
- Rate limit signals: response body `{"error": {"message": "minute_limit_exceeded"|"hour_limit_exceeded"|"month_limit_exceeded"}}`

#### 2. AeroDataBox: `https://aerodatabox.p.rapidapi.com`
~500 req/month free via RapidAPI.
Must create a (free) account at `https://rapidapi.com` and go to get a key for the AeroDataBox API.
- Auth: `X-RapidAPI-Key` header
- Route: `GET /flights/callsign/{callsign}`
- Rate limit signals: HTTP 429, or `X-RateLimit-Requests-Remaining: 0`

#### 3. FlightAware: `https://aeroapi.flightaware.com/aeroapi/`
Paid; highest data quality.
- Auth: `x-apikey` header
- Route: `GET /flights/{callsign}`
- Rate limit signal: HTTP 429

#### 4. AviationStack: `https://api.aviationstack.com/v1/`
100 req/month free.
- Auth: `?access_key=` query param
- Route: `GET /flights?flight_icao={callsign}`
- Rate limit signals: HTTP 429 or `{"error": {"code": "usage_limit_reached"}}`

#### 5. OpenSky: `https://opensky-network.org/api`
400 credits/day free. No direct callsign→route API; route is estimated from trajectory.
- Auth: OAuth2 Bearer token (30-min TTL, refreshed automatically), or anonymous
- Step 1: `GET /states/all?callsign={callsign}` → find ICAO24 hex
- Step 2: `GET /flights/aircraft?icao24={hex}&begin=...&end=...` → estimated departure/arrival airports
- Rate limit signal: HTTP 429; HTTP 401 triggers token refresh

---

### Config file

`config.json` (copy from `config.example.json`):

```json
{
  "cacheDb": "~/.aircrafttracker/routes.db",
  "airlineCodesCsv": "data/List_of_airline_codes.csv",
  "services": [
    { "name": "airLabs",       "enabled": true,  "apiKey": "<key>",        "requestDelay": 1.0 },
    { "name": "aeroDataBox",   "enabled": false, "rapidApiKey": "",        "requestDelay": 1.0 },
    { "name": "flightAware",   "enabled": false, "apiKey": "",             "requestDelay": 0.5 },
    { "name": "aviationStack", "enabled": false, "apiKey": "",             "requestDelay": 2.0 },
    { "name": "openSky",       "enabled": false, "username": "", "password": "", "requestDelay": 5.0 }
  ]
}
```

Paths in the config are resolved relative to the config file's directory. `~` is expanded.
CLI flags override config values.

`requestDelay` (seconds, default `0.0`) is the minimum pause after each call to that service. Applied after every attempt — hit, miss, or error — so consecutive calls during `--fillCache` don't exceed the service's rate limit. Suggested starting values are shown above; tune to your plan's actual limits.

---

### CLI

```
# Single lookup
python callsignLookup.py AAL1599 --config config.json

# Lookup without a config (airline name only from CSV, no route)
python callsignLookup.py AAL1599 --airlineCodes data/List_of_airline_codes.csv

# Pass API key directly
python callsignLookup.py AAL1599 --airLabsKey YOUR_KEY

# Cache-only lookup (no cloud service calls)
python callsignLookup.py AAL1599 --cacheOnly --config config.json

# Bulk lookup using only the cache (never calls services, even on miss)
python callsignLookup.py --fillCache callsigns.txt --cacheOnly --config config.json

# Bulk-populate cache from a file of callsigns (one per line)
python callsignLookup.py --fillCache data/callsigns.txt --config config.json

# Print all cached routes
python callsignLookup.py --dumpCache --config config.json

# Delete all cached routes
python callsignLookup.py --flushCache --config config.json

# Enable debug logging to stdout
python callsignLookup.py AAL1599 --config config.json --logLevel DEBUG

# Log to a file
python callsignLookup.py AAL1599 --config config.json --logLevel DEBUG --logFile lookup.log
```

Exit code 0 on success, 1 on not-found.

All CLI flags:

| Flag | Description |
|------|-------------|
| `--config PATH` | JSON config file (auto-detected as `config.json` if present) |
| `--cache PATH` | SQLite cache file (overrides config) |
| `--airlineCodes PATH` | Airline codes CSV (overrides config) |
| `--airLabsKey KEY` | AirLabs API key |
| `--aeroDataBoxKey KEY` | AeroDataBox RapidAPI key |
| `--flightAwareKey KEY` | FlightAware API key |
| `--aviationStackKey KEY` | AviationStack API key |
| `--openSkyUser USER` | OpenSky username |
| `--openSkyPass PASS` | OpenSky password |
| `--dumpCache` | Print all cached routes and exit |
| `--flushCache` | Delete all cached routes and exit |
| `--fillCache FILE` | Bulk-populate cache from callsign list |
| `--cacheOnly` | Only consult the cache; never call cloud services (applies to `--fillCache` too) |
| `--logLevel LEVEL` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` (default: `WARNING`) |
| `--logFile FILE` | Write logs to a file instead of stdout |

---

### Using as a library

```python
import sys
sys.path.insert(0, "/home/jdn/Code/AircraftTracker")
from callsignLookup import FlightInfoLookup, FlightRoute, Airport

# From a config file
lookup = FlightInfoLookup(config="/home/jdn/Code/AircraftTracker/config.json")

# Or fully programmatic
lookup = FlightInfoLookup(
    cacheDb="~/.aircrafttracker/routes.db",
    airlineCodesCsv="/home/jdn/Code/AircraftTracker/data/List_of_airline_codes.csv",
    services=[
        {"name": "airLabs", "enabled": True, "apiKey": "YOUR_KEY"},
    ],
)

route = lookup.lookup("AAL1599")
# FlightRoute(
#   callsign="AAL1599",
#   airline="American Airlines",
#   origin=Airport(icao="KDFW", name="Dallas Fort Worth Intl", ...),
#   destination=Airport(icao="KLAX", name="Los Angeles Intl", ...),
# )

# Cache-only mode (applies to all lookups including fillCache)
lookup = FlightInfoLookup(config="...", cacheOnly=True)
route = lookup.lookup("AAL1599")  # returns None on miss, never calls services

# Or override per-call (does not affect fillCache)
route = lookup.lookup("AAL1599", cacheOnly=True)

# Dump all cached routes
routes = lookup.dumpCache()  # returns list[FlightRoute]

# Bulk cache fill
lookup.fillCache("/path/to/callsigns.txt")

# Flush cache
lookup.flushCache()
```

`FlightRoute.origin` and `FlightRoute.destination` are `None` when no route data is available (airline-only result). Check before accessing airport fields.

Only routes with both `origin` and `destination` are written to the cache. Airline-only results are returned to the caller but not persisted, so a subsequent call will re-query services.
