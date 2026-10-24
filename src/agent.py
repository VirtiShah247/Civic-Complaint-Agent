import os
import re
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dotenv import load_dotenv

from src.tools import (
    resolve_ward,
    file_complaint,
    get_status,
    analyze_image,
    draft_social_post,
    _load_amc_data
)
from src.geocoding import extract_exif_gps

load_dotenv()

SYSTEM_PROMPT = """You are the Civic Complaint Agent for the Ahmedabad Municipal Corporation (AMC) Demo System.
Your job is to assist citizens in reporting civic issues (potholes, garbage dumps, broken streetlights, waterlogging),
identifying the correct ward and municipal department, filing complaints, checking complaint status, and drafting social posts.

STRICT OPERATING RULES & GUARDRAILS:
1. MOCK BOUNDARY: The AMC system is completely MOCKED in a local database. NEVER claim or imply you connect to a real municipal portal. Always state complaints are filed in the "Demo AMC System".
2. CONFIRMATION GATE: ALWAYS require citizen confirmation of the Issue, Ward, and Department before filing a complaint. Never file without explicit confirmation.
3. CONFIDENCE THRESHOLD: If issue confidence is < 0.7 or issue is 'unclear', DO NOT file. Describe what is visible and ask the user to clarify or upload a clearer photo.
4. WARD RESOLUTION: Never guess or invent a ward. If ward cannot be resolved confidently, ask the user for their area or landmark name.
5. GROUNDED STATUS: Status answers come ONLY from the get_status tool output. Never hallucinate or invent a status from memory. If an ID is unknown, state clearly that it was not found.
6. TOOL ORDER:
   analyze_image -> resolve_ward -> (citizen confirmation) -> file_complaint.
   get_status is available at any time.
7. TONE: Helpful, transparent, polite, and responsive.
"""

class CivicComplaintAgent:
    """Manual agent loop orchestrator tracking trace, confirmations, and tool execution."""
    
    def __init__(self):
        self.trace: List[Dict[str, Any]] = []
        self.pending_confirmation: Optional[Dict[str, Any]] = None
        self.pending_issue_details: Optional[Dict[str, Any]] = None
        self.last_tracking_id: Optional[str] = None
        self.confidence_threshold: float = 0.7  # Default from domain skill
        
    def add_trace(self, tool_name: str, input_args: Any, output_res: Any, status: str = "success") -> None:
        ist = timezone(timedelta(hours=5, minutes=30))
        now_str = datetime.now(ist).strftime("%H:%M:%S")
        self.trace.append({
            "timestamp": now_str,
            "tool": tool_name,
            "input": input_args,
            "output": output_res,
            "status": status
        })

    def run_turn(
        self,
        user_message: str = "",
        image_bytes: Optional[bytes] = None,
        image_obj: Optional[Any] = None
    ) -> str:
        text = user_message.strip()
        lower_text = text.lower()
        
        # 1. Image upload handling
        if image_bytes is not None:
            # Check EXIF GPS if PIL image provided
            gps_coords = None
            if image_obj:
                gps_coords = extract_exif_gps(image_obj)
                
            analysis = analyze_image(image_bytes)
            self.add_trace("analyze_image", {"image_bytes": f"{len(image_bytes)} bytes"}, analysis)
            
            issue = analysis.get("issue", "unclear")
            confidence = analysis.get("confidence", 0.0)
            description = analysis.get("description", "")
            
            # Confidence check
            if issue == "unclear" or confidence < self.confidence_threshold:
                self.pending_confirmation = None
                self.pending_issue_details = None
                return (
                    f"🔍 **Image Analysis**: {description}\n\n"
                    f"⚠️ **Cannot proceed with filing**: The detected issue is '{issue}' with confidence {confidence * 100:.0f}%, "
                    f"which is below our required confidence threshold ({self.confidence_threshold * 100:.0f}%).\n\n"
                    f"Could you please confirm the issue type (pothole, garbage, streetlight, waterlogging) or upload a clearer photo?"
                )
                
            # Issue is valid; attempt ward resolution
            ward_res = None
            if gps_coords:
                ward_res = resolve_ward(exif_gps=gps_coords)
                self.add_trace("resolve_ward", {"exif_gps": gps_coords}, ward_res)
                
            # If user also typed an area or text with image
            if (not ward_res or "error" in ward_res) and text:
                ward_res = resolve_ward(area_text=text)
                self.add_trace("resolve_ward", {"area_text": text}, ward_res)
                
            # Check department
            amc_data = _load_amc_data()
            dept = amc_data.get("departments", {}).get(issue, "General Administration")
            
            if ward_res and "error" not in ward_res:
                self.pending_confirmation = {
                    "issue": issue,
                    "confidence": confidence,
                    "description": description,
                    "ward_id": ward_res["ward_id"],
                    "ward_name": ward_res["ward_name"],
                    "zone": ward_res["zone"],
                    "department": dept
                }
                self.pending_issue_details = None
                
                return (
                    f"📸 **Civic Issue Identified!**\n\n"
                    f"- **Issue**: `{issue.capitalize()}` (Confidence: {confidence * 100:.0f}%)\n"
                    f"- **Department**: {dept}\n"
                    f"- **Ward**: {ward_res['ward_name']} ({ward_res['ward_id']}, {ward_res['zone']} Zone)\n"
                    f"- **Matched Area**: {ward_res.get('matched_area', ward_res['ward_name'])}\n"
                    f"- **Description**: {description}\n\n"
                    f"⚠️ *Demo Notice: This will be filed into the Mock AMC System.*\n\n"
                    f"👉 **Please confirm if you would like me to file this complaint.** (Type 'Confirm' or 'Yes')"
                )
            else:
                self.pending_issue_details = {
                    "issue": issue,
                    "confidence": confidence,
                    "description": description,
                    "department": dept
                }
                self.pending_confirmation = None
                gps_note = ""
                if ward_res and "detected_area" in ward_res:
                    gps_note = f" (GPS suggested '{ward_res['detected_area']}', but confidence was low)"
                    
                return (
                    f"📸 **Identified Issue**: `{issue.capitalize()}` (Confidence: {confidence * 100:.0f}%)\n"
                    f"- **Department**: {dept}\n"
                    f"- **Description**: {description}\n\n"
                    f"📍 **Ward Location Needed**{gps_note}: Please enter your area name or landmark in Ahmedabad (e.g., Navrangpura, Maninagar, CG Road, Bodakdev) so I can route this to the correct ward office."
                )

        # 2. Check for explicit confirmation to file
        confirmation_phrases = ["confirm", "yes", "proceed", "file it", "file complaint", "please file", "sure", "ok", "go ahead"]
        if self.pending_confirmation and any(phrase == lower_text or lower_text.startswith(phrase) for phrase in confirmation_phrases):
            p = self.pending_confirmation
            result = file_complaint(
                ward_id=p["ward_id"],
                issue=p["issue"],
                description=p["description"]
            )
            self.add_trace("file_complaint", p, result)
            
            tracking_id = result.get("trackingId")
            self.last_tracking_id = tracking_id
            self.pending_confirmation = None
            self.pending_issue_details = None
            
            if result.get("is_duplicate"):
                return (
                    f"ℹ️ **Existing Active Complaint Found**\n\n"
                    f"An active complaint already exists for **{p['issue'].capitalize()}** in **{p['ward_name']}** ({p['ward_id']}).\n"
                    f"- **Tracking ID**: `{tracking_id}`\n"
                    f"- **Department**: {result.get('department')}\n"
                    f"- **Status**: `{result.get('status')}`\n\n"
                    f"You can ask *'what's the status?'* or request a *'draft social post'*."
                )
            else:
                return (
                    f"✅ **Complaint Successfully Filed in Demo AMC System!**\n\n"
                    f"- **Tracking ID**: `{tracking_id}`\n"
                    f"- **Ward**: {p['ward_name']} ({p['ward_id']}, {p['zone']} Zone)\n"
                    f"- **Department**: {result.get('department')}\n"
                    f"- **Status**: `{result.get('status')}`\n"
                    f"- **Filed At**: {result.get('filedAt')}\n\n"
                    f"You can check back anytime by asking *'what's the status?'* or draft an escalation message with *'draft social post'*."
                )

        # 3. Status queries
        if "status" in lower_text or "track" in lower_text:
            # Check for AMC-2026-NNNNNN
            id_match = re.search(r"AMC-2026-\d{6}", text, re.IGNORECASE)
            target_id = id_match.group(0).upper() if id_match else None
            
            status_res = get_status(tracking_id=target_id, session_last_id=self.last_tracking_id)
            self.add_trace("get_status", {"tracking_id": target_id, "session_last_id": self.last_tracking_id}, status_res)
            
            if "error" in status_res:
                return f"❌ {status_res['error']}"
            else:
                return (
                    f"📋 **Complaint Status Record (Demo AMC System)**\n\n"
                    f"- **Tracking ID**: `{status_res.get('trackingId')}`\n"
                    f"- **Status**: `{status_res.get('status')}`\n"
                    f"- **Issue**: {status_res.get('issue', '').capitalize()}\n"
                    f"- **Department**: {status_res.get('department')}\n"
                    f"- **Ward**: {status_res.get('ward_name')} ({status_res.get('ward_id')}, {status_res.get('zone')} Zone)\n"
                    f"- **Filed At**: {status_res.get('filedAt')}\n"
                    f"- **Description**: {status_res.get('description')}"
                )

        # 4. Draft social post query
        if any(term in lower_text for term in ["social post", "social", "tweet", "post", "escalate"]):
            id_match = re.search(r"AMC-2026-\d{6}", text, re.IGNORECASE)
            target_id = id_match.group(0).upper() if id_match else self.last_tracking_id
            
            if not target_id:
                return "Please provide a tracking ID (e.g., 'draft social post for AMC-2026-000123') or file a complaint first."
                
            post_res = draft_social_post(tracking_id=target_id)
            self.add_trace("draft_social_post", {"tracking_id": target_id}, post_res)
            
            if "error" in post_res:
                return f"❌ {post_res['error']}"
            else:
                return (
                    f"📝 **Drafted Social Post (Demo / Mock Handles)**\n\n"
                    f"```text\n{post_res['post_text']}\n```\n\n"
                    f"*(Mock action only: nothing is posted to real social networks. You can copy this text.)*"
                )

        # 5. Location resolution if pending issue
        if self.pending_issue_details:
            ward_res = resolve_ward(area_text=text)
            self.add_trace("resolve_ward", {"area_text": text}, ward_res)
            
            if ward_res and "error" not in ward_res:
                p = self.pending_issue_details
                self.pending_confirmation = {
                    "issue": p["issue"],
                    "confidence": p["confidence"],
                    "description": p["description"],
                    "ward_id": ward_res["ward_id"],
                    "ward_name": ward_res["ward_name"],
                    "zone": ward_res["zone"],
                    "department": p["department"]
                }
                self.pending_issue_details = None
                
                return (
                    f"📍 **Ward Resolved**: **{ward_res['ward_name']}** ({ward_res['ward_id']}, {ward_res['zone']} Zone)\n"
                    f"- **Matched Landmark**: {ward_res.get('matched_area')}\n"
                    f"- **Issue**: `{p['issue'].capitalize()}`\n"
                    f"- **Department**: {p['department']}\n\n"
                    f"⚠️ *Demo Notice: This will be filed into the Mock AMC System.*\n\n"
                    f"👉 **Please confirm if you would like me to file this complaint.** (Type 'Confirm' or 'Yes')"
                )
            else:
                return (
                    f"❌ {ward_res.get('error')}\n"
                    f"Please try another nearby area or landmark in Ahmedabad (e.g., Navrangpura, Maninagar, CG Road, Vastrapur)."
                )

        # 6. Direct location resolution inquiry
        ward_query = resolve_ward(area_text=text)
        if "error" not in ward_query and ward_query.get("match_score", 0) >= 80:
            self.add_trace("resolve_ward", {"area_text": text}, ward_query)
            return (
                f"📍 Area '{text}' resolves to **{ward_query['ward_name']}** "
                f"(Ward ID: `{ward_query['ward_id']}`, {ward_query['zone']} Zone). "
                f"To report an issue here, please upload a photo!"
            )

        # 7. General LLM assistance using Gemini
        return self._call_gemini_conversational(text)

    def _call_gemini_conversational(self, user_text: str) -> str:
        """Call Gemini for general civic guidance while strictly adhering to system rules."""
        from google import genai
        
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return "Hello! I am your Civic Complaint Agent. Please upload a photo of a civic issue (pothole, garbage, streetlight, or waterlogging) to get started."
            
        model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        client = genai.Client(api_key=api_key)
        
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=user_text,
                    config={"system_instruction": SYSTEM_PROMPT, "temperature": 0.3}
                )
                self.add_trace("gemini_chat", {"input": user_text}, {"response": response.text})
                return response.text.strip()
            except Exception as e:
                time.sleep(2 ** attempt)
                
        return "I am here to help with civic grievances in Ahmedabad. Please upload a photo of a pothole, garbage dump, broken streetlight, or waterlogging to file a complaint."
