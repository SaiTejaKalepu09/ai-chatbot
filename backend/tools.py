from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from database.models import Appointment, Doctor, SessionLocal
import json

# ─────────────────────────────────────────
# HELPER: Get DB Session
# ─────────────────────────────────────────

def get_db_session():
    return SessionLocal()


# ─────────────────────────────────────────
# TOOL 1: CHECK DOCTOR AVAILABILITY
# ─────────────────────────────────────────

def checkAvailability(doctor_name: str, appointment_date: str) -> str:
    """
    Check if a doctor is available at a given date and time.
    
    Args:
        doctor_name: Name of the doctor (e.g. "Dr. Ramesh Kumar")
        appointment_date: Date and time string (e.g. "2026-03-10 10:00")
    
    Returns:
        JSON string with availability status
    """
    db = get_db_session()
    try:
        # Parse the date
        try:
            appt_datetime = datetime.strptime(appointment_date, "%Y-%m-%d %H:%M")
        except ValueError:
            return json.dumps({
                "available": False,
                "message": f"Invalid date format. Use YYYY-MM-DD HH:MM (e.g. 2026-03-10 10:00)"
            })

        # Check if date is in the past
        if appt_datetime < datetime.now():
            return json.dumps({
                "available": False,
                "message": "Cannot book appointments in the past. Please choose a future date."
            })

        # Find doctor in DB
        doctor = db.query(Doctor).filter(
            Doctor.name.ilike(f"%{doctor_name}%")
        ).first()

        if not doctor:
            # List available doctors
            all_doctors = db.query(Doctor).filter(Doctor.available == True).all()
            doctor_list = [f"{d.name} ({d.specialty})" for d in all_doctors]
            return json.dumps({
                "available": False,
                "message": f"Doctor '{doctor_name}' not found.",
                "available_doctors": doctor_list
            })

        if not doctor.available:
            return json.dumps({
                "available": False,
                "message": f"{doctor.name} is currently not available."
            })

        # Check if slot is already booked
        existing = db.query(Appointment).filter(
            Appointment.doctor_name.ilike(f"%{doctor_name}%"),
            Appointment.appointment_date == appt_datetime,
            Appointment.status == "booked"
        ).first()

        if existing:
            # Suggest alternative slots (next 3 available hours)
            alternatives = []
            for i in range(1, 4):
                alt_time = appt_datetime + timedelta(hours=i)
                alt_conflict = db.query(Appointment).filter(
                    Appointment.doctor_name.ilike(f"%{doctor_name}%"),
                    Appointment.appointment_date == alt_time,
                    Appointment.status == "booked"
                ).first()
                if not alt_conflict:
                    alternatives.append(alt_time.strftime("%Y-%m-%d %H:%M"))

            return json.dumps({
                "available": False,
                "message": f"{doctor.name} is already booked at {appointment_date}.",
                "alternative_slots": alternatives
            })

        # All good — slot is available!
        return json.dumps({
            "available": True,
            "message": f"{doctor.name} ({doctor.specialty}) is available on {appointment_date}.",
            "doctor_id": doctor.id,
            "doctor_name": doctor.name,
            "specialty": doctor.specialty
        })

    finally:
        db.close()


# ─────────────────────────────────────────
# TOOL 2: BOOK APPOINTMENT
# ─────────────────────────────────────────

def bookAppointment(
    patient_name: str,
    doctor_name: str,
    appointment_date: str,
    language: str = "en",
    notes: str = "",
    patient_phone: str = ""
) -> str:
    """
    Book a new appointment for a patient.

    Args:
        patient_name: Name of the patient
        doctor_name: Name of the doctor
        appointment_date: Date and time (YYYY-MM-DD HH:MM)
        language: Language code - en, hi, ta
        notes: Any additional notes
        patient_phone: Patient phone number (optional)

    Returns:
        JSON string with booking confirmation
    """
    db = get_db_session()
    try:
        # First check availability
        availability = json.loads(checkAvailability(doctor_name, appointment_date))

        if not availability["available"]:
            return json.dumps({
                "success": False,
                "message": availability["message"],
                "alternatives": availability.get("alternative_slots", [])
            })

        # Parse date
        appt_datetime = datetime.strptime(appointment_date, "%Y-%m-%d %H:%M")

        # Create appointment
        new_appointment = Appointment(
            patient_name=patient_name,
            patient_phone=patient_phone,
            doctor_id=availability["doctor_id"],
            doctor_name=availability["doctor_name"],
            specialty=availability["specialty"],
            appointment_date=appt_datetime,
            status="booked",
            language=language,
            notes=notes
        )

        db.add(new_appointment)
        db.commit()
        db.refresh(new_appointment)

        # Success response with multilingual message
        messages = {
            "en": f"✅ Appointment booked! {patient_name} with {availability['doctor_name']} on {appointment_date}. Appointment ID: {new_appointment.id}",
            "hi": f"✅ अपॉइंटमेंट बुक हो गई! {patient_name} की {availability['doctor_name']} से {appointment_date} को मुलाकात। ID: {new_appointment.id}",
            "ta": f"✅ சந்திப்பு முன்பதிவு செய்யப்பட்டது! {patient_name} {availability['doctor_name']} உடன் {appointment_date}. ID: {new_appointment.id}"
        }

        return json.dumps({
            "success": True,
            "appointment_id": new_appointment.id,
            "message": messages.get(language, messages["en"]),
            "details": {
                "patient": patient_name,
                "doctor": availability["doctor_name"],
                "specialty": availability["specialty"],
                "date": appointment_date,
                "status": "booked"
            }
        })

    except Exception as e:
        db.rollback()
        return json.dumps({
            "success": False,
            "message": f"Error booking appointment: {str(e)}"
        })
    finally:
        db.close()


# ─────────────────────────────────────────
# TOOL 3: CANCEL APPOINTMENT
# ─────────────────────────────────────────

def cancelAppointment(appointment_id: int, patient_name: str) -> str:
    """
    Cancel an existing appointment.

    Args:
        appointment_id: The ID of the appointment to cancel
        patient_name: Name of the patient (for verification)

    Returns:
        JSON string with cancellation status
    """
    db = get_db_session()
    try:
        # Find the appointment
        appointment = db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.patient_name.ilike(f"%{patient_name}%")
        ).first()

        if not appointment:
            # Try finding by patient name only
            appointments = db.query(Appointment).filter(
                Appointment.patient_name.ilike(f"%{patient_name}%"),
                Appointment.status == "booked"
            ).all()

            if appointments:
                appt_list = [{
                    "id": a.id,
                    "doctor": a.doctor_name,
                    "date": a.appointment_date.strftime("%Y-%m-%d %H:%M")
                } for a in appointments]
                return json.dumps({
                    "success": False,
                    "message": f"Appointment ID {appointment_id} not found. Here are {patient_name}'s bookings:",
                    "appointments": appt_list
                })

            return json.dumps({
                "success": False,
                "message": f"No appointments found for {patient_name}."
            })

        if appointment.status == "cancelled":
            return json.dumps({
                "success": False,
                "message": f"Appointment {appointment_id} is already cancelled."
            })

        # Cancel it
        appointment.status = "cancelled"
        appointment.updated_at = datetime.utcnow()
        db.commit()

        return json.dumps({
            "success": True,
            "message": f"✅ Appointment {appointment_id} cancelled successfully. {appointment.patient_name}'s appointment with {appointment.doctor_name} on {appointment.appointment_date.strftime('%Y-%m-%d %H:%M')} has been cancelled.",
            "appointment_id": appointment_id
        })

    except Exception as e:
        db.rollback()
        return json.dumps({
            "success": False,
            "message": f"Error cancelling appointment: {str(e)}"
        })
    finally:
        db.close()


# ─────────────────────────────────────────
# TOOL 4: RESCHEDULE APPOINTMENT
# ─────────────────────────────────────────

def rescheduleAppointment(
    appointment_id: int,
    patient_name: str,
    new_date: str
) -> str:
    """
    Reschedule an existing appointment to a new date/time.

    Args:
        appointment_id: The ID of the appointment
        patient_name: Name of the patient (for verification)
        new_date: New date and time (YYYY-MM-DD HH:MM)

    Returns:
        JSON string with reschedule status
    """
    db = get_db_session()
    try:
        # Find the appointment
        appointment = db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.patient_name.ilike(f"%{patient_name}%"),
            Appointment.status == "booked"
        ).first()

        if not appointment:
            return json.dumps({
                "success": False,
                "message": f"Active appointment {appointment_id} not found for {patient_name}."
            })

        # Check new slot availability
        availability = json.loads(checkAvailability(appointment.doctor_name, new_date))

        if not availability["available"]:
            return json.dumps({
                "success": False,
                "message": availability["message"],
                "alternatives": availability.get("alternative_slots", [])
            })

        # Parse new date
        new_datetime = datetime.strptime(new_date, "%Y-%m-%d %H:%M")

        old_date = appointment.appointment_date.strftime("%Y-%m-%d %H:%M")

        # Update appointment
        appointment.appointment_date = new_datetime
        appointment.status = "rescheduled"
        appointment.updated_at = datetime.utcnow()
        db.commit()

        # Re-set to booked after reschedule
        appointment.status = "booked"
        db.commit()

        return json.dumps({
            "success": True,
            "message": f"✅ Appointment rescheduled! {patient_name}'s appointment with {appointment.doctor_name} moved from {old_date} to {new_date}.",
            "appointment_id": appointment_id,
            "old_date": old_date,
            "new_date": new_date
        })

    except Exception as e:
        db.rollback()
        return json.dumps({
            "success": False,
            "message": f"Error rescheduling appointment: {str(e)}"
        })
    finally:
        db.close()


# ─────────────────────────────────────────
# TOOL 5: LIST ALL DOCTORS
# ─────────────────────────────────────────

def listDoctors() -> str:
    """
    Get all available doctors.

    Returns:
        JSON string with list of doctors
    """
    db = get_db_session()
    try:
        doctors = db.query(Doctor).filter(Doctor.available == True).all()
        doctor_list = [{
            "id": d.id,
            "name": d.name,
            "specialty": d.specialty,
            "languages": d.language
        } for d in doctors]

        return json.dumps({
            "success": True,
            "doctors": doctor_list,
            "total": len(doctor_list)
        })
    finally:
        db.close()


# ─────────────────────────────────────────
# TOOL 6: GET PATIENT APPOINTMENTS
# ─────────────────────────────────────────

def getPatientAppointments(patient_name: str) -> str:
    """
    Get all appointments for a patient.

    Args:
        patient_name: Name of the patient

    Returns:
        JSON string with list of appointments
    """
    db = get_db_session()
    try:
        appointments = db.query(Appointment).filter(
            Appointment.patient_name.ilike(f"%{patient_name}%"),
            Appointment.status == "booked"
        ).order_by(Appointment.appointment_date).all()

        if not appointments:
            return json.dumps({
                "success": True,
                "message": f"No active appointments found for {patient_name}.",
                "appointments": []
            })

        appt_list = [{
            "id": a.id,
            "doctor": a.doctor_name,
            "specialty": a.specialty,
            "date": a.appointment_date.strftime("%Y-%m-%d %H:%M"),
            "status": a.status
        } for a in appointments]

        return json.dumps({
            "success": True,
            "patient": patient_name,
            "appointments": appt_list,
            "total": len(appt_list)
        })
    finally:
        db.close()


# ─────────────────────────────────────────
# TOOLS LIST (used by LLM Agent in Step 3)
# ─────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "checkAvailability",
            "description": "Check if a doctor is available at a specific date and time",
            "parameters": {
                "type": "object",
                "properties": {
                    "doctor_name": {"type": "string", "description": "Full name of the doctor"},
                    "appointment_date": {"type": "string", "description": "Date and time in YYYY-MM-DD HH:MM format"}
                },
                "required": ["doctor_name", "appointment_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "bookAppointment",
            "description": "Book a new clinical appointment for a patient",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_name": {"type": "string", "description": "Full name of the patient"},
                    "doctor_name": {"type": "string", "description": "Full name of the doctor"},
                    "appointment_date": {"type": "string", "description": "Date and time in YYYY-MM-DD HH:MM format"},
                    "language": {"type": "string", "description": "Language code: en, hi, ta", "default": "en"},
                    "notes": {"type": "string", "description": "Additional notes", "default": ""},
                    "patient_phone": {"type": "string", "description": "Patient phone number", "default": ""}
                },
                "required": ["patient_name", "doctor_name", "appointment_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancelAppointment",
            "description": "Cancel an existing appointment",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {"type": "integer", "description": "The appointment ID to cancel"},
                    "patient_name": {"type": "string", "description": "Name of the patient"}
                },
                "required": ["appointment_id", "patient_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rescheduleAppointment",
            "description": "Reschedule an existing appointment to a new date and time",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {"type": "integer", "description": "The appointment ID to reschedule"},
                    "patient_name": {"type": "string", "description": "Name of the patient"},
                    "new_date": {"type": "string", "description": "New date and time in YYYY-MM-DD HH:MM format"}
                },
                "required": ["appointment_id", "patient_name", "new_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "listDoctors",
            "description": "Get list of all available doctors and their specialties",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "getPatientAppointments",
            "description": "Get all active appointments for a specific patient",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_name": {"type": "string", "description": "Name of the patient"}
                },
                "required": ["patient_name"]
            }
        }
    }
]


# ─────────────────────────────────────────
# TOOL EXECUTOR (called by Agent)
# ─────────────────────────────────────────

TOOL_MAP = {
    "checkAvailability": checkAvailability,
    "bookAppointment": bookAppointment,
    "cancelAppointment": cancelAppointment,
    "rescheduleAppointment": rescheduleAppointment,
    "listDoctors": listDoctors,
    "getPatientAppointments": getPatientAppointments
}

def execute_tool(tool_name: str, tool_args: dict) -> str:
    """Execute a tool by name with given arguments"""
    if tool_name not in TOOL_MAP:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    # ✅ Fix: handle None or empty args safely
    if not tool_args:
        tool_args = {}

    tool_func = TOOL_MAP[tool_name]
    return tool_func(**tool_args)


# ─────────────────────────────────────────
# TEST TOOLS DIRECTLY
# ─────────────────────────────────────────

if __name__ == "__main__":
    print("🧪 Testing tools...\n")

    # Test 1: List doctors
    print("1️⃣ List Doctors:")
    print(listDoctors())
    print()

    # Test 2: Check availability
    print("2️⃣ Check Availability:")
    print(checkAvailability("Dr. Ramesh Kumar", "2026-03-15 10:00"))
    print()

    # Test 3: Book appointment
    print("3️⃣ Book Appointment:")
    print(bookAppointment("Sai Teja", "Dr. Ramesh Kumar", "2026-03-15 10:00", "en"))
    print()

    # Test 4: Get patient appointments
    print("4️⃣ Get Patient Appointments:")
    print(getPatientAppointments("Sai Teja"))
    print()

    print("✅ All tools tested!")