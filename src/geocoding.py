import os
import json
import time
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import requests
from PIL import Image, ExifTags

_LAST_NOMINATIM_CALL_TIME = 0.0

def get_geocache_path() -> Path:
    override = os.getenv("GEOCACHE_PATH")
    if override:
        return Path(override)
    return Path(__file__).parent.parent / "data" / "geocache.json"

def _load_geocache(cache_path: Path) -> Dict[str, Any]:
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_geocache(cache_path: Path, cache: Dict[str, Any]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = cache_path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)
    temp_path.replace(cache_path)

def extract_exif_gps(image: Image.Image) -> Optional[Tuple[float, float]]:
    """Extract GPS latitude and longitude (in decimal degrees) from an Image object."""
    try:
        exif = image.getexif()
        if not exif:
            return None
        
        # 34853 is GPSInfo tag
        gps_info = exif.get_ifd(0x8825)
        if not gps_info:
            return None
            
        def _to_decimal(dms, ref):
            deg = float(dms[0])
            minute = float(dms[1])
            sec = float(dms[2])
            dec = deg + (minute / 60.0) + (sec / 3600.0)
            if ref in ['S', 'W']:
                dec = -dec
            return dec
            
        lat_dms = gps_info.get(2)
        lat_ref = gps_info.get(1)
        lon_dms = gps_info.get(4)
        lon_ref = gps_info.get(3)
        
        if lat_dms and lat_ref and lon_dms and lon_ref:
            lat = _to_decimal(lat_dms, lat_ref)
            lon = _to_decimal(lon_dms, lon_ref)
            return (lat, lon)
    except Exception:
        pass
    return None

def reverse_geocode_nominatim(lat: float, lon: float, cache_file: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Reverse geocode GPS coordinates using OpenStreetMap Nominatim with strict rate-limiting and caching."""
    global _LAST_NOMINATIM_CALL_TIME
    
    cache_path = Path(cache_file) if cache_file else get_geocache_path()
    cache = _load_geocache(cache_path)
    
    # Key by 5 decimal places (approx 1 meter precision)
    coord_key = f"{lat:.5f},{lon:.5f}"
    if coord_key in cache:
        return cache[coord_key]
        
    # Rate limit: 1 request per second (1.1s buffer)
    now = time.time()
    elapsed = now - _LAST_NOMINATIM_CALL_TIME
    if elapsed < 1.1:
        time.sleep(1.1 - elapsed)
        
    user_agent = os.getenv("NOMINATIM_USER_AGENT", "CivicComplaintAgent/1.0 (contact@example.com)")
    headers = {"User-Agent": user_agent}
    params = {
        "lat": lat,
        "lon": lon,
        "format": "jsonv2",
        "zoom": 16,
        "addressdetails": 1
    }
    
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            headers=headers,
            params=params,
            timeout=10
        )
        _LAST_NOMINATIM_CALL_TIME = time.time()
        
        if response.status_code == 200:
            data = response.json()
            address = data.get("address", {})
            cache[coord_key] = address
            _save_geocache(cache_path, cache)
            return address
    except Exception:
        pass
    return None
