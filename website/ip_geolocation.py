"""Local, time-independent IP region lookup for the protected OB page.

The MMDB is queried only while building an authenticated OB response. Region
labels are not written back to page-view logs, and latitude/longitude fields
from the source database are deliberately ignored.
"""
from __future__ import annotations

import ipaddress
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SOURCE_NAME = "DB-IP Lite"

_READER_LOCK = threading.RLock()
_READER: Any = None
_READER_SIGNATURE: tuple[str, int, int] | None = None


def _open_database(path: Path):
    import maxminddb

    return maxminddb.open_database(str(path))


def _reader_for(path: Path):
    global _READER, _READER_SIGNATURE

    stat = path.stat()
    signature = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    if _READER is not None and _READER_SIGNATURE == signature:
        return _READER

    next_reader = _open_database(path)
    previous_reader = _READER
    _READER = next_reader
    _READER_SIGNATURE = signature
    if previous_reader is not None:
        previous_reader.close()
    return next_reader


def _names(value: Any) -> tuple[str, list[str]]:
    if not isinstance(value, dict):
        return "", []
    raw_names = value.get("names")
    if not isinstance(raw_names, dict):
        return "", []
    names = [
        str(item).strip()
        for item in raw_names.values()
        if item is not None and str(item).strip()
    ]
    preferred = ""
    for key in ("zh-CN", "zh", "en"):
        candidate = raw_names.get(key)
        if candidate:
            preferred = str(candidate).strip()
            break
    if not preferred and names:
        preferred = names[0]
    return preferred, names


def _location_from_record(record: Any) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        return None

    country, country_names = _names(record.get("country"))
    city, city_names = _names(record.get("city"))
    country_data = record.get("country") if isinstance(record.get("country"), dict) else {}
    subdivisions = record.get("subdivisions")
    subdivision = subdivisions[0] if isinstance(subdivisions, list) and subdivisions else {}
    region, region_names = _names(subdivision)

    values = [value for value in (country, region, city) if value]
    if not values:
        return None

    search_terms: list[str] = []
    for value in (
        *country_names,
        *region_names,
        *city_names,
        country_data.get("iso_code", ""),
        subdivision.get("iso_code", "") if isinstance(subdivision, dict) else "",
    ):
        text = str(value).strip()
        if text and text not in search_terms:
            search_terms.append(text)

    return {
        "country": country,
        "country_code": str(country_data.get("iso_code", "")),
        "region": region,
        "region_code": str(subdivision.get("iso_code", "")) if isinstance(subdivision, dict) else "",
        "city": city,
        "label": " · ".join(values),
        "search_terms": search_terms,
    }


def _build_date(reader: Any) -> str:
    try:
        build_epoch = int(reader.metadata().build_epoch)
    except (AttributeError, TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(build_epoch, tz=timezone.utc).date().isoformat()


def lookup_ip_locations(
    ip_values: Iterable[str],
    database_path: str | Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Resolve public IPs locally and return labels plus non-sensitive status."""
    path = Path(database_path)
    observed_values: list[str] = []
    observed_set: set[str] = set()
    for raw_value in ip_values:
        value = str(raw_value).strip()
        if value and value not in observed_set:
            observed_set.add(value)
            observed_values.append(value)

    public_ips: list[str] = []
    valid_ip_count = 0
    non_global_ip_count = 0
    invalid_ip_count = 0
    for value in observed_values:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            invalid_ip_count += 1
            continue
        valid_ip_count += 1
        if address.is_global:
            public_ips.append(value)
        else:
            non_global_ip_count += 1

    status: dict[str, Any] = {
        "available": False,
        "source": SOURCE_NAME,
        "database_build_date": "",
        "observed_ip_count": len(observed_values),
        "valid_ip_count": valid_ip_count,
        "eligible_ip_count": len(public_ips),
        "located_ip_count": 0,
        "unresolved_ip_count": len(public_ips),
        "non_global_ip_count": non_global_ip_count,
        "invalid_ip_count": invalid_ip_count,
    }
    if not path.is_file():
        status["status"] = "database_missing"
        return {}, status

    try:
        with _READER_LOCK:
            reader = _reader_for(path)
            locations = {}
            for ip in public_ips:
                location = _location_from_record(reader.get(ip))
                if location:
                    locations[ip] = location
            status.update({
                "available": True,
                "status": "ready",
                "database_build_date": _build_date(reader),
                "located_ip_count": len(locations),
                "unresolved_ip_count": len(public_ips) - len(locations),
            })
            return locations, status
    except (ImportError, OSError, RuntimeError, ValueError):
        status["status"] = "reader_unavailable"
        return {}, status
