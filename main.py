import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr
from bson import ObjectId
from datetime import datetime

from database import db, create_document, get_documents

app = FastAPI(title="Geaux Driving API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# Utility helpers
# ----------------------------

def oid_str(value):
    try:
        return str(value)
    except Exception:
        return value


def serialize_doc(doc: dict):
    if not doc:
        return doc
    out = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            out[k] = str(v)
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


# ----------------------------
# Schemas
# ----------------------------
class BookingCreate(BaseModel):
    student_name: str = Field(..., description="Full name of the student")
    email: EmailStr
    phone: str = Field(..., description="Contact phone number")
    service: str = Field(..., description="Service name e.g., Behind-the-Wheel, Road Test Prep")
    instructor: Optional[str] = Field(None, description="Preferred instructor name or ID")
    date: str = Field(..., description="Preferred lesson date (ISO or friendly)")
    time: str = Field(..., description="Preferred time slot")
    pickup_location: Optional[str] = None
    notes: Optional[str] = None


class LeadCreate(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    source: str = Field("website", description="Lead source: website, chat, booking")
    message: Optional[str] = None
    tag: Optional[str] = Field(None, description="Optional tag for CRM segmentation")


class ContactMessage(BaseModel):
    name: str
    email: EmailStr
    subject: str
    message: str


class EmailTemplate(BaseModel):
    key: str
    subject: str
    html: str


# ----------------------------
# Basic routes
# ----------------------------
@app.get("/")
def read_root():
    return {"message": "Geaux Driving API is running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:15]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:120]}"

    return response


# ----------------------------
# Booking endpoints
# ----------------------------
@app.post("/api/bookings")
def create_booking(payload: BookingCreate):
    try:
        booking_id = create_document("booking", payload)
        # Also create a CRM lead entry
        lead = payload.model_dump()
        lead_doc = {
            "name": lead.get("student_name"),
            "email": lead.get("email"),
            "phone": lead.get("phone"),
            "source": "booking",
            "tag": lead.get("service"),
            "message": f"Booking requested for {lead.get('service')} on {lead.get('date')} at {lead.get('time')} with instructor {lead.get('instructor') or 'Any'}."
        }
        create_document("lead", lead_doc)
        return {"success": True, "booking_id": booking_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bookings")
def list_bookings(limit: int = 50):
    try:
        docs = get_documents("booking", limit=limit)
        return [serialize_doc(d) for d in docs]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------
# CRM Lead endpoints
# ----------------------------
@app.post("/api/leads")
def create_lead(payload: LeadCreate):
    try:
        lead_id = create_document("lead", payload)
        return {"success": True, "lead_id": lead_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/leads")
def list_leads(limit: int = 100):
    try:
        docs = get_documents("lead", limit=limit)
        return [serialize_doc(d) for d in docs]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------
# Contact form endpoint
# ----------------------------
@app.post("/api/contact")
def contact(payload: ContactMessage):
    try:
        doc = payload.model_dump()
        doc["source"] = "contact"
        lead_id = create_document("lead", doc)
        return {"success": True, "lead_id": lead_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------
# Email templates (for automations)
# ----------------------------
@app.get("/api/email-templates", response_model=List[EmailTemplate])
def email_templates():
    brand = "Geaux Driving"
    zutobi_url = "https://www.zutobi.com/"
    templates = [
        EmailTemplate(
            key="welcome",
            subject=f"Welcome to {brand}! Your Path to Safe, Confident Driving",
            html=f"""
            <h2>Welcome to {brand}!</h2>
            <p>We're excited to help you become a safe, confident driver. You can book or manage your lessons anytime on our website.</p>
            <p>Before your first lesson, spend 10 minutes reviewing your <a href='{zutobi_url}'>Zutobi</a> modules to maximize your time in the car.</p>
            <p>Questions? Just reply to this email. We're here to help!</p>
            <p>— The {brand} Team</p>
            """.strip()
        ),
        EmailTemplate(
            key="booking_confirmation",
            subject=f"{brand}: Your Driving Lesson is Confirmed",
            html=f"""
            <h2>Your lesson is confirmed!</h2>
            <p>Thank you for booking with {brand}. You'll receive a reminder 24 hours before your lesson.</p>
            <p>Bring your permit/license and wear comfortable shoes. Review your <a href='{zutobi_url}'>Zutobi</a> module beforehand.</p>
            <p>Need to reschedule? Use the link in your confirmation or contact support.</p>
            """.strip()
        ),
        EmailTemplate(
            key="post_lesson",
            subject=f"{brand}: Great work today — review your evaluation in Zutobi",
            html=f"""
            <h2>Great job behind the wheel!</h2>
            <p>Your instructor has submitted your evaluation in Zutobi. Log in to review your progress and next steps.</p>
            <p><a href='{zutobi_url}'>Access your evaluation</a></p>
            <p>Keep practicing and see you soon!</p>
            """.strip()
        )
    ]
    return templates


# ----------------------------
# Schema explorer (optional)
# ----------------------------
@app.get("/schema")
def get_schema():
    # Expose basic schema info for the database viewer
    return {
        "collections": [
            {
                "name": "booking",
                "fields": [
                    "student_name", "email", "phone", "service", "instructor", "date", "time", "pickup_location", "notes"
                ]
            },
            {
                "name": "lead",
                "fields": [
                    "name", "email", "phone", "source", "tag", "message"
                ]
            }
        ]
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
