from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ─────────────────────────────────────────
# DATABASE CONNECTION
# ─────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./appointments.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}  # Required for SQLite
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# ─────────────────────────────────────────
# TABLE 1: DOCTORS
# ─────────────────────────────────────────

class Doctor(Base):
    __tablename__ = "doctors"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String(100), nullable=False)
    specialty   = Column(String(100), nullable=False)   # e.g. Cardiologist, General
    language    = Column(String(50), default="English") # Preferred language
    available   = Column(Boolean, default=True)         # Is doctor active?
    created_at  = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Doctor id={self.id} name={self.name} specialty={self.specialty}>"


# ─────────────────────────────────────────
# TABLE 2: APPOINTMENTS
# ─────────────────────────────────────────

class Appointment(Base):
    __tablename__ = "appointments"

    id              = Column(Integer, primary_key=True, index=True)
    patient_name    = Column(String(100), nullable=False)
    patient_phone   = Column(String(20), nullable=True)
    doctor_id       = Column(Integer, nullable=False)
    doctor_name     = Column(String(100), nullable=False)
    specialty       = Column(String(100), nullable=False)
    appointment_date = Column(DateTime, nullable=False)   # Date + time of appointment
    status          = Column(String(20), default="booked") # booked / cancelled / rescheduled
    language        = Column(String(20), default="en")    # en / hi / ta
    notes           = Column(Text, nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Appointment id={self.id} patient={self.patient_name} doctor={self.doctor_name} date={self.appointment_date}>"


# ─────────────────────────────────────────
# TABLE 3: CONVERSATION HISTORY (Persistent Memory)
# ─────────────────────────────────────────

class ConversationHistory(Base):
    __tablename__ = "conversation_history"

    id           = Column(Integer, primary_key=True, index=True)
    session_id   = Column(String(100), nullable=False, index=True)
    patient_name = Column(String(100), nullable=True)
    role         = Column(String(20), nullable=False)   # "user" or "assistant"
    message      = Column(Text, nullable=False)
    language     = Column(String(20), default="en")
    created_at   = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ConversationHistory session={self.session_id} role={self.role}>"


# ─────────────────────────────────────────
# CREATE ALL TABLES
# ─────────────────────────────────────────

def init_db():
    """Create all tables in the database"""
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created successfully!")


# ─────────────────────────────────────────
# DATABASE SESSION (Dependency Injection)
# ─────────────────────────────────────────

def get_db():
    """Get database session - use this in FastAPI routes"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─────────────────────────────────────────
# SEED SAMPLE DOCTORS (for testing)
# ─────────────────────────────────────────

def seed_doctors():
    """Add sample doctors to the database for testing"""
    db = SessionLocal()

    # Check if doctors already exist
    existing = db.query(Doctor).first()
    if existing:
        print("ℹ️  Doctors already seeded.")
        db.close()
        return

    sample_doctors = [
        Doctor(name="Dr. Ramesh Kumar",   specialty="Cardiologist",    language="English, Tamil"),
        Doctor(name="Dr. Priya Sharma",   specialty="General Physician", language="English, Hindi"),
        Doctor(name="Dr. Arjun Mehta",    specialty="Orthopedic",      language="English, Hindi"),
        Doctor(name="Dr. Kavitha Nair",   specialty="Dermatologist",   language="English, Tamil"),
        Doctor(name="Dr. Suresh Babu",    specialty="Neurologist",     language="English, Telugu"),
    ]

    db.add_all(sample_doctors)
    db.commit()
    print("✅ Sample doctors added to database!")
    db.close()


# ─────────────────────────────────────────
# RUN DIRECTLY TO INITIALIZE DATABASE
# ─────────────────────────────────────────

if __name__ == "__main__":
    print("🚀 Initializing database...")
    init_db()
    seed_doctors()
    print("🎉 Database ready!")