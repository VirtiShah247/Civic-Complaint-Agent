# 🏛️ Civic Complaint Agent (AMC Demo System)

An autonomous, AI-powered civic grievance agent built for the Ahmedabad Municipal Corporation (AMC) simulation. 

Citizens upload a photo of a civic issue (**pothole, garbage dump, broken streetlight, or waterlogging**). The agent analyzes the photo with zero-shot Gemini Vision, automatically resolves the Ahmedabad municipal ward and assigned department, requires explicit citizen confirmation, atomically files the complaint with a unique tracking ID into the local mock municipal registry (`data/amc.json`), and provides live grounded status lookups and social escalation drafts.

> **⚠️ Notice**: This system operates on a local mock municipal system (`data/amc.json`). It does not connect to any real government or municipal production systems.

---

## 🚀 Key Features

- **Zero-Shot Vision Analysis**: Classifies potholes, garbage, streetlights, and waterlogging using Google Gemini 3.8 Flash with structured JSON output and exponential backoff retry.
- **Robust Ward Resolution**:
  - **Path A (Primary)**: RapidFuzz case/punctuation-insensitive fuzzy matching ("CG Road", "C.G. Road", "cg road" all resolve to Ward 12 Navrangpura).
  - **Path B (EXIF GPS)**: Reverse geocodes coordinates via OpenStreetMap Nominatim with strict rate limiting (1.1s) and persistent disk caching (`data/geocache.json`).
- **Human-in-the-Loop Confirmation Gate**: The agent never files a complaint without explicit citizen confirmation of the detected Issue, Ward, and Department.
- **Quality & Safety Guardrails**:
  - Ambiguous / blurry photos (< 0.70 confidence or "unclear") are refused for filing, prompting the citizen for clarification.
  - Never guesses or hallucinates an unknown ward.
  - Duplicate complaints in the same ward with an active status return the existing tracking ID.
  - Grounded status checking: Status answers are strictly sourced from `get_status()`, never from LLM memory.
- **Mobile-First Streamlit UI**:
  - Live **Agent Trace** sidebar showing inputs, outputs, timestamps, and tool calls.
  - Dynamic **AMC Complaints Registry** table that reloads in real time.
  - Interactive OpenStreetMap pin via Leaflet/Folium.
  - Social media escalation post drafter with mock handles.

---

## 🛠️ Stack & Architecture

- **Language**: Python 3.11+
- **LLM / Vision**: Google Gemini API via official `google-genai` Python SDK
- **Web UI**: Streamlit + Folium + Streamlit-Folium
- **Fuzzy Matching**: RapidFuzz
- **Image & EXIF**: Pillow
- **Testing**: Pytest (15 unit and integration tests passing)

---

## 📋 Installation & Setup

### 1. Clone the repository
```bash
git clone https://github.com/VirtiShah247/Civic-Complaint-Agent.git
cd Civic-Complaint-Agent
```

### 2. Create and activate a virtual environment (optional but recommended)
```bash
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Edit `.env` and fill in your Gemini API key:
```env
# Gemini API Key (Free tier via Google AI Studio: https://aistudio.google.com/)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.8-flash

# OpenStreetMap Nominatim Compliance
NOMINATIM_USER_AGENT=CivicComplaintAgent/1.0 (contact@example.com)
```

#### How to get a Free Gemini API Key:
1. Visit [Google AI Studio](https://aistudio.google.com/).
2. Sign in with your Google account.
3. Click **"Get API key"** -> **"Create API key"**.
4. Paste the key into `.env`. No billing or credit card is required on the free tier.

---

## 🏃 Running the Application

Launch the Streamlit web dashboard:
```bash
streamlit run app.py
```
Open your browser to `http://localhost:8501`.

---

## 🧪 Running Automated Tests

Run the full test suite covering all deterministic tools, ward resolution, caching, duplicate prevention, and agent state machine:
```bash
python -m pytest tests/ -v
```

### Vision Dataset Evaluation Script
Evaluate Gemini Vision zero-shot accuracy across test datasets and compute the optimal confidence threshold:
```bash
python scripts/eval_vision.py
```
*(If folders in `data/eval/` are missing, the script gracefully reports skipped categories and defaults to the 0.70 domain baseline).*

---

## 🎬 Demo Walkthrough Script (Sample Prompts)

### Scenario 1: Filing a New Civic Complaint
1. **Action**: In the UI, upload a road damage photo (or `data/samples/sample_pothole.jpg`) and type `CG Road` in the Area box (or chat).
2. **Agent Response**:
   > 📸 **Civic Issue Identified!**
   > - **Issue**: `Pothole` (Confidence: 95%)
   > - **Department**: Roads & Buildings
   > - **Ward**: Navrangpura (W12, West Zone)
   > - **Matched Area**: CG Road
   > 
   > 👉 **Please confirm if you would like me to file this complaint.**
3. **Action**: Click **"✅ Yes, Confirm & File Complaint"** (or type `Confirm`).
4. **Agent Response**:
   > ✅ **Complaint Successfully Filed in Demo AMC System!**
   > - **Tracking ID**: `AMC-2026-000124`
   > - **Ward**: Navrangpura (W12)
   > - **Status**: `Assigned`
   > - *(The sidebar complaints table updates immediately!)*

### Scenario 2: Checking Live Complaint Status
1. **Prompt**: `what's the status?`
   - **Response**: Returns the status of the session's most recent complaint (`AMC-2026-000124`).
2. **Prompt**: `status of AMC-2026-000123`
   - **Response**: Returns the seed complaint: `Assigned` in Ward W12 (Roads & Buildings).
3. **Prompt**: `status of AMC-2026-999999`
   - **Response**: `❌ Complaint ID 'AMC-2026-999999' not found in the AMC mock system.` (Strictly grounded, never hallucinated).

### Scenario 3: Duplicate Complaint Guardrail & Ambiguity Rejection
1. **Prompt**: Try to file another `pothole` in `Navrangpura` (W12).
   - **Agent Response**: Detects that an active complaint already exists for this ward and issue, and returns the existing tracking ID `AMC-2026-000123` instead of creating redundant work.
2. **Action**: Upload an ambiguous or blurry photo without a clear issue.
   - **Agent Response**: Refuses to file, states what was detected, and prompts the user to confirm or upload a clearer photo.

### Scenario 4: Drafting an Escalation Social Post
1. **Prompt**: `draft social post`
   - **Agent Response**: Generates a formatted accountability post tagging mock ward handles (e.g. `@AMC_Mock_West @AMC_Ward12_Eng`) with tracking ID and department details.

---

## 📑 Dataset & Service Citations

This project adheres to ethical research and open-source licensing standards. We gratefully acknowledge:

1. **QR4Change Dataset**:
   > Lokhande et al., *QR4Change Civic Issues Dataset*, Mendeley Data, DOI: [10.17632/zndzygc3p3.2](https://doi.org/10.17632/zndzygc3p3.2), licensed under CC BY 4.0.
2. **Pothole Detection Dataset**:
   > Atikur Rahman Chitholian via Roboflow Universe, licensed under Open Database License (ODbL v1.0).
3. **OpenStreetMap**:
   > Reverse geocoding data and map tiles © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), accessed in accordance with Nominatim usage guidelines.

---

## ✂️ Scope Management & Cuts Log

As budgeted under the 2-hour hackathon timeframe:
- **Social post drafter**: ✅ Kept and fully implemented.
- **Real-time complaints table**: ✅ Kept and fully implemented in the sidebar.
- **Mobile-first UI polish**: ✅ Kept with responsive cards, badges, and layout.
- **Folium map pin**: ✅ Kept for EXIF GPS visualization.
- **Features Cut**: **None!** All core requirements and optional amendments were delivered within the time box.
