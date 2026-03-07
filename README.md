# Voice AI Agent - Clinical Appointment Booking

## Setup Instructions
1. Clone the repo
2. Create virtual environment: `python -m venv venv`
3. Activate: `venv\Scripts\activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Add your GROQ_API_KEY in `.env`
6. Run: `uvicorn backend.main:app --reload`

## Architecture
- STT: Whisper (local)
- LLM: Groq (Llama 3) 
- TTS: gTTS
- Memory: Redis
- Database: SQLite
```

---

## ✅ Your Final Structure Should Look Like:
```
AI ChatBot/
├── backend/
├── database/
├── voice/
├── venv/
├── .env          ← new
├── README.md     ← new
└── requirements.txt 
