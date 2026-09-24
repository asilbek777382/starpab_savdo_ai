"""Yetkazib berish hududi va narxini do'kon sozlamalaridagi delivery_zones bo'yicha aniqlash.

Zona formati:
  {"name": "Toshkent shahri", "keywords": ["toshkent", "chilonzor"], "fee": 20000, "eta": "1 kun",
   "center": [41.31, 69.27], "radius_km": 15}
"""

import math

from app.services.text import normalize


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def find_zone(zones: list[dict], address: str | None = None, location: dict | None = None) -> dict | None:
    if location and "latitude" in location and "longitude" in location:
        point = (float(location["latitude"]), float(location["longitude"]))
        best: tuple[float, dict] | None = None
        for zone in zones:
            center, radius = zone.get("center"), zone.get("radius_km")
            if center and radius:
                dist = _haversine_km(point, (float(center[0]), float(center[1])))
                if dist <= float(radius) and (best is None or dist < best[0]):
                    best = (dist, zone)
        if best:
            return best[1]
    if address:
        text = f" {normalize(address)} "
        for zone in zones:
            names = [zone.get("name", ""), *zone.get("keywords", [])]
            for kw in names:
                kw_norm = normalize(kw)
                if kw_norm and f" {kw_norm}" in text:
                    return zone
    return None


def delivery_info(zones: list[dict], address: str | None = None, location: dict | None = None) -> dict:
    zone = find_zone(zones, address, location)
    if zone:
        return {"found": True, "zone": zone.get("name"), "fee": int(zone.get("fee", 0)), "eta": zone.get("eta")}
    return {
        "found": False,
        "note": "Manzil hech bir yetkazib berish hududiga mos kelmadi",
        "zones": [{"zone": z.get("name"), "fee": int(z.get("fee", 0)), "eta": z.get("eta")} for z in zones],
    }
