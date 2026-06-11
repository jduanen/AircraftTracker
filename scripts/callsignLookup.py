#!/usr/bin/env python3
"""
Airline and route lookup for aircraft callsigns.

Importable:
    from callsignLookup import FlightInfoLookup
    lookup = FlightInfoLookup(config="config.json")
    route = lookup.lookup("AAL1599")

CLI:
    python callsignLookup.py AAL1599 --config config.json
    python callsignLookup.py --fillCache callsigns.txt --config config.json
    python callsignLookup.py --flushCache --config config.json
"""

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
import time
from dataclasses import dataclass

import requests


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class Airport:
    icao: str
    name: str
    city: str
    country: str
    lat: float
    lon: float


@dataclass
class FlightRoute:
    callsign: str
    airline: str
    origin: Airport | None
    destination: Airport | None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class RateLimitError(Exception):
    pass


class ServiceUnavailableError(Exception):
    pass


# ---------------------------------------------------------------------------
# Persistent cache
# ---------------------------------------------------------------------------

class RouteCache:
    _CREATE = """
        CREATE TABLE IF NOT EXISTS routes (
            callsign      TEXT PRIMARY KEY,
            airline       TEXT,
            origin_icao   TEXT, origin_name    TEXT, origin_city    TEXT,
            origin_country TEXT, origin_lat    REAL, origin_lon     REAL,
            dest_icao     TEXT, dest_name      TEXT, dest_city      TEXT,
            dest_country  TEXT, dest_lat       REAL, dest_lon       REAL,
            cached_at     TEXT
        )
    """

    def __init__(self, dbPath: str):
        dbPath = os.path.expanduser(dbPath)
        os.makedirs(os.path.dirname(dbPath) or ".", exist_ok=True)
        self._conn = sqlite3.connect(dbPath)
        self._conn.execute(self._CREATE)
        self._conn.commit()

    def get(self, callsign: str) -> FlightRoute | None:
        row = self._conn.execute(
            "SELECT * FROM routes WHERE callsign = ?", (callsign,)
        ).fetchone()
        if row is None:
            return None
        (cs, airline,
         o_icao, o_name, o_city, o_country, o_lat, o_lon,
         d_icao, d_name, d_city, d_country, d_lat, d_lon, _) = row
        origin = Airport(o_icao, o_name, o_city, o_country, o_lat or 0.0, o_lon or 0.0) if o_icao else None
        dest = Airport(d_icao, d_name, d_city, d_country, d_lat or 0.0, d_lon or 0.0) if d_icao else None
        return FlightRoute(cs, airline or "", origin, dest)

    def put(self, route: FlightRoute):
        o, d = route.origin, route.destination
        self._conn.execute(
            """INSERT OR REPLACE INTO routes VALUES
               (?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))""",
            (
                route.callsign, route.airline,
                o.icao if o else None, o.name if o else None,
                o.city if o else None, o.country if o else None,
                o.lat if o else None, o.lon if o else None,
                d.icao if d else None, d.name if d else None,
                d.city if d else None, d.country if d else None,
                d.lat if d else None, d.lon if d else None,
            ),
        )
        self._conn.commit()

    def flush(self):
        self._conn.execute("DELETE FROM routes")
        self._conn.commit()


# ---------------------------------------------------------------------------
# Service adapters
# ---------------------------------------------------------------------------

class AirLabsService:
    name = "airLabs"
    _BASE = "https://airlabs.co/api/v9"

    def __init__(self, apiKey: str):
        self.apiKey = apiKey
        self.available = True
        self._session = requests.Session()

    def _get(self, path: str, params: dict) -> dict:
        params["api_key"] = self.apiKey
        try:
            resp = self._session.get(f"{self._BASE}{path}", params=params, timeout=10)
        except requests.RequestException as e:
            raise ServiceUnavailableError(str(e))
        if resp.status_code == 429:
            raise RateLimitError("HTTP 429")
        if not resp.ok:
            raise ServiceUnavailableError(f"HTTP {resp.status_code}")
        data = resp.json()
        err = data.get("error", {}).get("message", "")
        if "limit_exceeded" in err:
            raise RateLimitError(err)
        return data

    def _resolveAirport(self, icao: str) -> Airport | None:
        if not icao:
            return None
        try:
            data = self._get("/airports", {"icao_code": icao})
        except (RateLimitError, ServiceUnavailableError):
            return Airport(icao, "", "", "", 0.0, 0.0)
        rows = data.get("response", [])
        if not rows:
            return Airport(icao, "", "", "", 0.0, 0.0)
        r = rows[0]
        return Airport(
            icao=icao,
            name=r.get("name", ""),
            city=r.get("city", ""),
            country=r.get("country_code", ""),
            lat=float(r.get("lat", 0.0) or 0.0),
            lon=float(r.get("lng", 0.0) or 0.0),
        )

    def lookup(self, callsign: str) -> FlightRoute | None:
        data = self._get("/flights", {"flight_icao": callsign})
        rows = data.get("response", [])
        if not rows:
            return None
        r = rows[0]
        dep_icao = r.get("dep_icao") or ""
        arr_icao = r.get("arr_icao") or ""
        airline = r.get("airline_icao", "") or ""
        origin = self._resolveAirport(dep_icao)
        dest = self._resolveAirport(arr_icao)
        return FlightRoute(callsign=callsign, airline=airline, origin=origin, destination=dest)


class AeroDataBoxService:
    name = "aeroDataBox"
    _BASE = "https://aerodatabox.p.rapidapi.com"

    def __init__(self, rapidApiKey: str):
        self.rapidApiKey = rapidApiKey
        self.available = True
        self._session = requests.Session()
        self._session.headers.update({
            "X-RapidAPI-Key": rapidApiKey,
            "X-RapidAPI-Host": "aerodatabox.p.rapidapi.com",
        })

    def lookup(self, callsign: str) -> FlightRoute | None:
        try:
            resp = self._session.get(
                f"{self._BASE}/flights/callsign/{callsign}", timeout=10
            )
        except requests.RequestException as e:
            raise ServiceUnavailableError(str(e))
        if resp.status_code == 429 or resp.headers.get("X-RateLimit-Requests-Remaining") == "0":
            raise RateLimitError("rate limit")
        if resp.status_code == 404:
            return None
        if not resp.ok:
            raise ServiceUnavailableError(f"HTTP {resp.status_code}")
        data = resp.json()
        flights = data if isinstance(data, list) else data.get("items", [])
        if not flights:
            return None
        f = flights[0]
        dep = f.get("departure", {}).get("airport", {})
        arr = f.get("arrival", {}).get("airport", {})
        origin = Airport(
            icao=dep.get("icao", ""), name=dep.get("name", ""),
            city=dep.get("municipalityName", ""), country="",
            lat=float((dep.get("location") or {}).get("lat", 0.0)),
            lon=float((dep.get("location") or {}).get("lon", 0.0)),
        ) if dep else None
        dest = Airport(
            icao=arr.get("icao", ""), name=arr.get("name", ""),
            city=arr.get("municipalityName", ""), country="",
            lat=float((arr.get("location") or {}).get("lat", 0.0)),
            lon=float((arr.get("location") or {}).get("lon", 0.0)),
        ) if arr else None
        return FlightRoute(callsign=callsign, airline="", origin=origin, destination=dest)


class FlightAwareService:
    name = "flightAware"
    _BASE = "https://aeroapi.flightaware.com/aeroapi"

    def __init__(self, apiKey: str):
        self.apiKey = apiKey
        self.available = True
        self._session = requests.Session()
        self._session.headers.update({"x-apikey": apiKey})

    def lookup(self, callsign: str) -> FlightRoute | None:
        try:
            resp = self._session.get(
                f"{self._BASE}/flights/{callsign}", timeout=10
            )
        except requests.RequestException as e:
            raise ServiceUnavailableError(str(e))
        if resp.status_code == 429:
            raise RateLimitError("HTTP 429")
        if resp.status_code == 404:
            return None
        if not resp.ok:
            raise ServiceUnavailableError(f"HTTP {resp.status_code}")
        data = resp.json()
        flights = data.get("flights", [])
        if not flights:
            return None
        f = flights[0]
        dep = f.get("origin", {})
        arr = f.get("destination", {})
        origin = Airport(
            icao=dep.get("code_icao", "") or dep.get("code", ""),
            name=dep.get("name", ""), city=dep.get("city", ""),
            country=dep.get("country_code", ""),
            lat=float(dep.get("latitude", 0.0) or 0.0),
            lon=float(dep.get("longitude", 0.0) or 0.0),
        ) if dep else None
        dest = Airport(
            icao=arr.get("code_icao", "") or arr.get("code", ""),
            name=arr.get("name", ""), city=arr.get("city", ""),
            country=arr.get("country_code", ""),
            lat=float(arr.get("latitude", 0.0) or 0.0),
            lon=float(arr.get("longitude", 0.0) or 0.0),
        ) if arr else None
        return FlightRoute(callsign=callsign, airline="", origin=origin, destination=dest)


class AviationStackService:
    name = "aviationStack"
    _BASE = "https://api.aviationstack.com/v1"

    def __init__(self, apiKey: str):
        self.apiKey = apiKey
        self.available = True
        self._session = requests.Session()

    def lookup(self, callsign: str) -> FlightRoute | None:
        try:
            resp = self._session.get(
                f"{self._BASE}/flights",
                params={"access_key": self.apiKey, "flight_icao": callsign},
                timeout=10,
            )
        except requests.RequestException as e:
            raise ServiceUnavailableError(str(e))
        if resp.status_code == 429:
            raise RateLimitError("HTTP 429")
        if not resp.ok:
            raise ServiceUnavailableError(f"HTTP {resp.status_code}")
        data = resp.json()
        if data.get("error", {}).get("code") == "usage_limit_reached":
            raise RateLimitError("usage_limit_reached")
        rows = data.get("data", [])
        if not rows:
            return None
        f = rows[0]
        dep = f.get("departure", {})
        arr = f.get("arrival", {})
        origin = Airport(
            icao=dep.get("icao", ""), name=dep.get("airport", ""),
            city="", country="",
            lat=float(dep.get("latitude", 0.0) or 0.0),
            lon=float(dep.get("longitude", 0.0) or 0.0),
        ) if dep.get("icao") else None
        dest = Airport(
            icao=arr.get("icao", ""), name=arr.get("airport", ""),
            city="", country="",
            lat=float(arr.get("latitude", 0.0) or 0.0),
            lon=float(arr.get("longitude", 0.0) or 0.0),
        ) if arr.get("icao") else None
        airline = (f.get("airline") or {}).get("icao", "")
        return FlightRoute(callsign=callsign, airline=airline or "", origin=origin, destination=dest)


class OpenSkyService:
    """
    Last-resort adapter. OpenSky has no direct callsign→route API; this uses
    /states/all to find the aircraft ICAO24 hex, then /flights/aircraft for
    estimated departure/arrival airports. Expect a high miss rate.
    """
    name = "openSky"
    _BASE = "https://opensky-network.org/api"
    _TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"

    def __init__(self, username: str = "", password: str = ""):
        self.username = username
        self.password = password
        self.available = True
        self._session = requests.Session()
        self._token: str | None = None
        self._tokenExpiry: float = 0.0

    def _refreshToken(self):
        if not self.username:
            return
        try:
            resp = requests.post(
                self._TOKEN_URL,
                data={
                    "grant_type": "password",
                    "client_id": "opensky-api",
                    "username": self.username,
                    "password": self.password,
                },
                timeout=10,
            )
            if resp.ok:
                d = resp.json()
                self._token = d["access_token"]
                self._tokenExpiry = time.time() + d.get("expires_in", 1800) - 60
        except Exception:
            pass

    def _headers(self) -> dict:
        if self.username:
            if time.time() >= self._tokenExpiry:
                self._refreshToken()
            if self._token:
                return {"Authorization": f"Bearer {self._token}"}
        return {}

    def _get(self, path: str, params: dict = {}) -> dict | None:
        try:
            resp = self._session.get(
                f"{self._BASE}{path}", params=params,
                headers=self._headers(), timeout=15
            )
        except requests.RequestException as e:
            raise ServiceUnavailableError(str(e))
        if resp.status_code == 429:
            raise RateLimitError("HTTP 429")
        if resp.status_code == 401:
            self._tokenExpiry = 0.0  # force refresh next call
            raise ServiceUnavailableError("HTTP 401 — token expired")
        if resp.status_code == 404 or resp.status_code == 204:
            return None
        if not resp.ok:
            raise ServiceUnavailableError(f"HTTP {resp.status_code}")
        return resp.json()

    def lookup(self, callsign: str) -> FlightRoute | None:
        # Step 1: find ICAO24 from live state vectors
        data = self._get("/states/all", {"callsign": callsign.ljust(8)})
        if not data or not data.get("states"):
            return None
        icao24 = data["states"][0][0]

        # Step 2: look up recent flight records for that aircraft
        now = int(time.time())
        data = self._get("/flights/aircraft", {
            "icao24": icao24,
            "begin": now - 7200,
            "end": now,
        })
        if not data:
            return None
        flights = [f for f in data if f.get("callsign", "").strip() == callsign]
        if not flights:
            flights = data
        f = flights[-1]
        dep_icao = f.get("estDepartureAirport") or ""
        arr_icao = f.get("estArrivalAirport") or ""
        if not dep_icao and not arr_icao:
            return None
        origin = Airport(dep_icao, "", "", "", 0.0, 0.0) if dep_icao else None
        dest = Airport(arr_icao, "", "", "", 0.0, 0.0) if arr_icao else None
        return FlightRoute(callsign=callsign, airline="", origin=origin, destination=dest)


# ---------------------------------------------------------------------------
# Airline name lookup from local CSV
# ---------------------------------------------------------------------------

def _loadAirlineLookup(csvPath: str) -> dict[str, str]:
    lookup: dict[str, str] = {}
    with open(csvPath, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            icao = row["ICAO"].strip()
            if icao:
                lookup[icao] = row["Airline"].strip()
    return lookup


def _callsignPrefix(callsign: str) -> str:
    m = re.match(r"^([A-Z]+)", callsign.strip().upper())
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

def _buildService(cfg: dict):
    name = cfg.get("name", "")
    if name == "airLabs":
        return AirLabsService(apiKey=cfg.get("apiKey", ""))
    if name == "aeroDataBox":
        return AeroDataBoxService(rapidApiKey=cfg.get("rapidApiKey", ""))
    if name == "flightAware":
        return FlightAwareService(apiKey=cfg.get("apiKey", ""))
    if name == "aviationStack":
        return AviationStackService(apiKey=cfg.get("apiKey", ""))
    if name == "openSky":
        return OpenSkyService(username=cfg.get("username", ""), password=cfg.get("password", ""))
    raise ValueError(f"Unknown service: {name!r}")


class FlightInfoLookup:
    def __init__(
        self,
        config: str | None = None,
        cacheDb: str | None = None,
        services: list[dict] | None = None,
        airlineCodesCsv: str | None = None,
    ):
        cfg = {}
        configDir = "."
        if config:
            configPath = os.path.expanduser(config)
            configDir = os.path.dirname(os.path.abspath(configPath))
            with open(configPath) as f:
                cfg = json.load(f)

        def _resolve(path: str) -> str:
            path = os.path.expanduser(path)
            return path if os.path.isabs(path) else os.path.join(configDir, path)

        dbPath = cacheDb or cfg.get("cacheDb") or "~/.aircrafttracker/routes.db"
        self._cache = RouteCache(_resolve(dbPath))

        csvPath = airlineCodesCsv or cfg.get("airlineCodesCsv")
        self._airlineLookup: dict[str, str] = {}
        if csvPath:
            resolved = _resolve(csvPath)
            if os.path.exists(resolved):
                self._airlineLookup = _loadAirlineLookup(resolved)

        serviceCfgs = services if services is not None else cfg.get("services", [])
        self._services = [
            _buildService(s) for s in serviceCfgs if s.get("enabled", True)
        ]

    def lookup(self, callsign: str) -> FlightRoute | None:
        callsign = callsign.strip().upper()

        cached = self._cache.get(callsign)
        if cached is not None:
            return cached

        route = None
        for svc in self._services:
            if not svc.available:
                continue
            try:
                route = svc.lookup(callsign)
            except RateLimitError:
                svc.available = False
                continue
            except ServiceUnavailableError:
                continue
            if route is not None:
                break

        airline = (route.airline if route else "") or self._airlineLookup.get(_callsignPrefix(callsign), "")

        if route is not None:
            route.airline = airline
            self._cache.put(route)
            return route

        if airline:
            partial = FlightRoute(callsign=callsign, airline=airline, origin=None, destination=None)
            self._cache.put(partial)
            return partial

        return None

    def fillCache(self, callsignsFile: str):
        with open(callsignsFile, encoding="utf-8") as f:
            callsigns = [line.strip() for line in f if line.strip()]
        hits = 0
        for i, cs in enumerate(callsigns, 1):
            result = self.lookup(cs)
            if result and (result.origin or result.airline):
                hits += 1
            print(f"[{i}/{len(callsigns)}] {cs}: {'found' if result else 'not found'}")
        print(f"\nDone: {hits}/{len(callsigns)} resolved")

    def flushCache(self):
        self._cache.flush()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _makeParser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Look up airline and route for an aircraft callsign."
    )
    p.add_argument("callsign", nargs="?", help="Callsign to look up (e.g. AAL1599)")
    p.add_argument("--config",          metavar="PATH", help="JSON config file")
    p.add_argument("--cache",           metavar="PATH", help="SQLite cache file")
    p.add_argument("--airlineCodes",    metavar="PATH", help="Airline codes CSV")
    p.add_argument("--airLabsKey",      metavar="KEY")
    p.add_argument("--aeroDataBoxKey",  metavar="KEY")
    p.add_argument("--flightAwareKey",  metavar="KEY")
    p.add_argument("--aviationStackKey",metavar="KEY")
    p.add_argument("--openSkyUser",     metavar="USER")
    p.add_argument("--openSkyPass",     metavar="PASS")
    p.add_argument("--flushCache",      action="store_true", help="Delete all cached routes and exit")
    p.add_argument("--fillCache",       metavar="FILE", help="Bulk-populate cache from callsign list file")
    return p


def _serviceOverrides(args: argparse.Namespace) -> list[dict] | None:
    overrides = {
        "airLabs":       {"apiKey": args.airLabsKey},
        "aeroDataBox":   {"rapidApiKey": args.aeroDataBoxKey},
        "flightAware":   {"apiKey": args.flightAwareKey},
        "aviationStack": {"apiKey": args.aviationStackKey},
        "openSky":       {"username": args.openSkyUser, "password": args.openSkyPass},
    }
    if not any(v for d in overrides.values() for v in d.values()):
        return None
    return [
        {"name": name, "enabled": any(v for v in keys.values()), **{k: v for k, v in keys.items() if v}}
        for name, keys in overrides.items()
    ]


def main():
    args = _makeParser().parse_args()

    lookup = FlightInfoLookup(
        config=args.config,
        cacheDb=args.cache,
        airlineCodesCsv=args.airlineCodes,
        services=_serviceOverrides(args),
    )

    if args.flushCache:
        lookup.flushCache()
        print("Cache flushed.")
        return

    if args.fillCache:
        lookup.fillCache(args.fillCache)
        return

    if not args.callsign:
        _makeParser().print_help()
        sys.exit(1)

    route = lookup.lookup(args.callsign)
    if route is None:
        print(f"{args.callsign}: not found")
        sys.exit(1)

    print(f"Callsign : {route.callsign}")
    print(f"Airline  : {route.airline or '(unknown)'}")
    if route.origin:
        loc = f"{route.origin.city}, {route.origin.country}".strip(", ")
        print(f"Origin   : {route.origin.icao}  {route.origin.name}  {loc}")
    else:
        print("Origin   : (unknown)")
    if route.destination:
        loc = f"{route.destination.city}, {route.destination.country}".strip(", ")
        print(f"Dest     : {route.destination.icao}  {route.destination.name}  {loc}")
    else:
        print("Dest     : (unknown)")


if __name__ == "__main__":
    main()
