import os
import re
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, Union
from rapidfuzz import fuzz, process
from dotenv import load_dotenv

load_dotenv()

def get_amc_data_path() -> Path:
    override = os.getenv("AMC_DATA_PATH")
    if override:
        return Path(override)
    return Path(__file__).parent.parent / "data" / "amc.json"

def _load_amc_data() -> Dict[str, Any]:
    path = get_amc_data_path()
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _save_amc_data(data: Dict[str, Any]) -> None:
    path = get_amc_data_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    temp_path.replace(path)

def _normalize_string(text: str) -> str:
    """Normalize text by lowercasing and stripping punctuation for robust matching."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def resolve_ward(
    area_text: Optional[str] = None,
    exif_gps: Optional[Union[Tuple[float, float], Dict[str, float]]] = None
) -> Dict[str, Any]:
    """
    Resolve municipal ward based on typed area text (primary) or EXIF GPS (secondary).
    Returns ward details or an error message prompting user input.
    """
    amc_data = _load_amc_data()
    wards = amc_data.get("wards", [])
    
    # Path A: User typed area text (primary path)
    if area_text and area_text.strip():
        user_input = area_text.strip()
        norm_user_input = _normalize_string(user_input)
        
        best_match = None
        best_score = 0.0
        best_ward = None
        
        for ward in wards:
            # Check ward name
            candidates = [ward["name"]] + ward.get("areas", [])
            for cand in candidates:
                norm_cand = _normalize_string(cand)
                
                # Check direct containment or token set ratio
                if norm_user_input == norm_cand:
                    score = 100.0
                elif norm_cand in norm_user_input or norm_user_input in norm_cand:
                    score = 90.0
                else:
                    score = fuzz.token_set_ratio(norm_user_input, norm_cand)
                    
                if score > best_score:
                    best_score = score
                    best_match = cand
                    best_ward = ward
                    
        # Threshold for typed text
        if best_score >= 70 and best_ward:
            return {
                "ward_id": best_ward["id"],
                "ward_name": best_ward["name"],
                "zone": best_ward["zone"],
                "matched_area": best_match,
                "match_score": round(best_score, 1),
                "source": "text"
            }
        else:
            return {
                "error": f"Could not confidently resolve ward for '{user_input}'. Please specify the landmark or area name (e.g., Navrangpura, Maninagar, CG Road)."
            }
            
    # Path B: EXIF GPS coordinates (secondary hint)
    if exif_gps:
        if isinstance(exif_gps, dict):
            lat = exif_gps.get("lat")
            lon = exif_gps.get("lon")
        else:
            lat, lon = exif_gps
            
        if lat is not None and lon is not None:
            from src.geocoding import reverse_geocode_nominatim
            address = reverse_geocode_nominatim(float(lat), float(lon))
            
            if address:
                # First available of: suburb, neighbourhood, city_district, quarter
                gps_area = (
                    address.get("suburb")
                    or address.get("neighbourhood")
                    or address.get("city_district")
                    or address.get("quarter")
                )
                
                if gps_area:
                    norm_gps_area = _normalize_string(gps_area)
                    best_score = 0.0
                    best_ward = None
                    best_match = None
                    
                    for ward in wards:
                        candidates = [ward["name"]] + ward.get("areas", [])
                        for cand in candidates:
                            norm_cand = _normalize_string(cand)
                            score = fuzz.token_set_ratio(norm_gps_area, norm_cand)
                            if score > best_score:
                                best_score = score
                                best_match = cand
                                best_ward = ward
                                
                    # Policy rule: If score < 85, do NOT guess; ask user to confirm/type area
                    if best_score >= 85 and best_ward:
                        return {
                            "ward_id": best_ward["id"],
                            "ward_name": best_ward["name"],
                            "zone": best_ward["zone"],
                            "matched_area": best_match,
                            "match_score": round(best_score, 1),
                            "source": "gps",
                            "detected_area": gps_area
                        }
                    else:
                        return {
                            "error": f"Photo GPS detected area '{gps_area}', but ward match confidence is low ({best_score:.0f}/100). Please confirm or enter your area name.",
                            "detected_area": gps_area,
                            "gps": {"lat": lat, "lon": lon}
                        }

    return {
        "error": "No area name or GPS coordinates provided. Please enter your location (e.g. CG Road, Navrangpura, Maninagar)."
    }


def file_complaint(
    ward_id: str,
    issue: str,
    description: str
) -> Dict[str, Any]:
    """
    File a complaint in the mock AMC system.
    Atomically generates AMC-2026-NNNNNN, rejects active duplicates, and writes to amc.json.
    """
    amc_data = _load_amc_data()
    complaints = amc_data.get("complaints", [])
    departments = amc_data.get("departments", {})
    wards = amc_data.get("wards", [])
    
    # Check duplicate: same ward + issue + status not Resolved
    issue_clean = issue.strip().lower()
    for existing in complaints:
        if (
            existing.get("ward_id") == ward_id
            and existing.get("issue", "").strip().lower() == issue_clean
            and existing.get("status") != "Resolved"
        ):
            return {
                "trackingId": existing["trackingId"],
                "department": existing.get("department", departments.get(issue_clean, "General Administration")),
                "status": existing.get("status", "Assigned"),
                "is_duplicate": True,
                "message": f"An active complaint ({existing['trackingId']}) already exists for this issue in ward {ward_id}."
            }
            
    # Generate sequential tracking ID
    max_id_num = 123
    id_pattern = re.compile(r"AMC-2026-(\d+)")
    for c in complaints:
        match = id_pattern.match(c.get("trackingId", ""))
        if match:
            num = int(match.group(1))
            if num > max_id_num:
                max_id_num = num
                
    new_tracking_id = f"AMC-2026-{max_id_num + 1:06d}"
    
    # Find ward info
    ward_info = next((w for w in wards if w["id"] == ward_id), None)
    ward_name = ward_info["name"] if ward_info else "Unknown Ward"
    zone = ward_info["zone"] if ward_info else "Unknown Zone"
    dept_name = departments.get(issue_clean, "General Administration")
    
    # Local timestamp with +05:30 offset
    ist = timezone(timedelta(hours=5, minutes=30))
    filed_at = datetime.now(ist).isoformat(timespec="seconds")
    
    new_complaint = {
        "trackingId": new_tracking_id,
        "ward_id": ward_id,
        "ward_name": ward_name,
        "zone": zone,
        "issue": issue_clean,
        "department": dept_name,
        "description": description.strip(),
        "status": "Assigned",
        "filedAt": filed_at
    }
    
    complaints.append(new_complaint)
    amc_data["complaints"] = complaints
    _save_amc_data(amc_data)
    
    return {
        "trackingId": new_tracking_id,
        "department": dept_name,
        "status": "Assigned",
        "is_duplicate": False,
        "filedAt": filed_at
    }


def get_status(
    tracking_id: Optional[str] = None,
    session_last_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get the status of a complaint by tracking ID.
    If tracking_id is None, uses session_last_id.
    """
    target_id = tracking_id.strip() if tracking_id else session_last_id
    if not target_id:
        return {
            "error": "Please provide a complaint tracking ID (e.g., AMC-2026-000123) to check status."
        }
        
    amc_data = _load_amc_data()
    complaints = amc_data.get("complaints", [])
    
    clean_target = target_id.strip().upper()
    for c in complaints:
        if c.get("trackingId", "").strip().upper() == clean_target:
            return c
            
    return {
        "error": f"Complaint ID '{target_id}' not found in the AMC mock system. Please verify the ID."
    }


def analyze_image(image_bytes: bytes) -> Dict[str, Any]:
    """
    Zero-shot Gemini vision analysis using google-genai SDK.
    Enforces structured JSON output and exponential backoff on 429/5xx.
    """
    from google import genai
    from google.genai import types
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {
            "issue": "unclear",
            "confidence": 0.0,
            "description": "Error: GEMINI_API_KEY is not set in environment or .env."
        }
        
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    client = genai.Client(api_key=api_key)
    
    prompt = """Analyze this image for civic infrastructure complaints in Ahmedabad.
Identify if there is one of the following civic issues:
- 'pothole': Road damage, asphalt crater, broken road surface
- 'garbage': Overflowing dumpster, roadside garbage dump, accumulated debris/litter
- 'streetlight': Broken, leaning, damaged, or unlit streetlight pole/fixture
- 'waterlogging': Standing rainwater on streets, flooded roadway, overflowing storm drain
- 'unclear': The image is blurry, ambiguous, normal street with no issue, or something else.

Respond in strict JSON with:
{
  "issue": "pothole" | "garbage" | "streetlight" | "waterlogging" | "unclear",
  "confidence": <float from 0.0 to 1.0>,
  "description": "<Concise 1-2 sentence description of the visible condition>"
}
"""
    
    # Exponential backoff (up to 3 retries)
    last_error = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[
                    prompt,
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type="image/jpeg",
                    ),
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            
            raw_text = response.text.strip()
            # Clean possible markdown wrapping if any
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            data = json.loads(raw_text.strip())
            
            # Normalize issue
            issue = data.get("issue", "unclear").lower()
            if issue not in ["pothole", "garbage", "streetlight", "waterlogging"]:
                issue = "unclear"
                
            conf = float(data.get("confidence", 0.0))
            desc = data.get("description", "Civic issue photo analyzed.")
            
            return {
                "issue": issue,
                "confidence": max(0.0, min(1.0, conf)),
                "description": desc
            }
        except Exception as e:
            last_error = e
            time.sleep(2 ** attempt)
            
    return {
        "issue": "unclear",
        "confidence": 0.0,
        "description": f"Analysis temporarily unavailable after retries: {str(last_error)}"
    }


def draft_social_post(tracking_id: str) -> Dict[str, Any]:
    """
    Draft an accountability social media post for a complaint with mock ward handles.
    """
    record = get_status(tracking_id=tracking_id)
    if "error" in record:
        return record
        
    amc_data = _load_amc_data()
    wards = amc_data.get("wards", [])
    ward_info = next((w for w in wards if w["id"] == record.get("ward_id")), None)
    handles = ward_info.get("mock_social_handles", ["@AMC_Mock_Eng"]) if ward_info else ["@AMC_Mock_Eng"]
    handles_str = " ".join(handles)
    
    post_text = (
        f"📢 Civic Grievance Alert - Ahmedabad Municipal Corporation (Mock Demo)\n\n"
        f"Issue: {record.get('issue', '').capitalize()} ({record.get('department')})\n"
        f"Ward: {record.get('ward_name')} ({record.get('ward_id')}, {record.get('zone')} Zone)\n"
        f"Tracking ID: #{record.get('trackingId')}\n"
        f"Status: {record.get('status')}\n\n"
        f"Requesting attention from civic authorities {handles_str}. "
        f"Please resolve this hazard for citizens.\n\n"
        f"#CivicCare #Ahmedabad #PublicGrievance #DemoSystem"
    )
    
    return {
        "tracking_id": record.get("trackingId"),
        "post_text": post_text,
        "mock_handles": handles
    }
