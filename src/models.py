from typing import Literal, Optional, List
from pydantic import BaseModel, Field

IssueType = Literal["pothole", "garbage", "streetlight", "waterlogging", "unclear"]
ComplaintStatus = Literal["Assigned", "In Progress", "Resolved"]

class ImageAnalysisResult(BaseModel):
    issue: IssueType = Field(description="The detected civic issue type, or 'unclear'")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    description: str = Field(description="Detailed description of what is seen in the image")

class WardResolutionResult(BaseModel):
    ward_id: str
    ward_name: str
    zone: str
    match_score: float
    source: Literal["text", "gps"] = "text"

class ComplaintRecord(BaseModel):
    trackingId: str
    ward_id: str
    ward_name: str
    zone: str
    issue: IssueType
    department: str
    description: str
    status: ComplaintStatus
    filedAt: str

class ComplaintResponse(BaseModel):
    trackingId: str
    department: str
    status: ComplaintStatus
    is_duplicate: bool = False
    message: Optional[str] = None
