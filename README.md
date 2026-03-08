# 2Care.ai — Real-Time Multilingual Voice AI Agent

> Clinical appointment booking via voice — supports **English**, **Hindi**, and **Tamil**

<img width="3611" height="2351" alt="image" src="https://github.com/user-attachments/assets/60fe2444-3b7d-4543-99de-9c10e960b0c3" />


---

## Demo

- **Voice**: Speak into mic → agent understands → speaks back
- **Languages**: Auto-detects English / Hindi / Tamil
- **Booking**: Book, cancel, reschedule appointments with conflict detection

---

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| LLM | Groq LLaMA 3.3 70B | Free tier |
| STT | Groq Whisper large-v3-turbo | Free tier |
| TTS | gTTS | Free, no key needed |
| Language Detection | langdetect | Auto EN/HI/TA |
| Backend | FastAPI + Uvicorn | Streaming SSE |
| Session Memory | Redis / in-memory fallback | 30min TTL |
| Persistent Memory | SQLite | Full history |
| Database | SQLite + SQLAlchemy | Zero config |

---

## Project Structure

```
AI ChatBot/
├── backend/
│   ├── agent.py       # LLM agent — tool calling + streaming
│   ├── main.py        # FastAPI server + all endpoints + UI
│   ├── memory.py      # Session + persistent memory
│   └── tools.py       # 6 appointment booking tools
├── database/
│   └── models.py      # SQLAlchemy models, DB init, seed data
├── voice/
│   ├── stt.py         # Groq Whisper STT
│   └── tts.py         # gTTS text-to-speech
├── .env               # API keys (not committed)
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Clone
```bash
git clone https://github.com/YOUR_USERNAME/2care-voice-agent
cd 2care-voice-agent
```

### 2. Virtual environment
```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Create `.env`
```env
GROQ_API_KEY=your_groq_api_key_here
DATABASE_URL=sqlite:///./appointments.db
REDIS_URL=redis://localhost:6379
```

Get free Groq API key: https://console.groq.com

### 5. Run
```bash
python -m backend.main
```

### 6. Open browser
```
http://localhost:8000
```

---

## Architecture

```
User (Browser Mic)
       |
       | WebM audio
       v
  [STT — Groq Whisper]              ~300ms
       |
       | Transcribed text
       v
  [Language Detection — langdetect]
       |
       | Text + Language (EN/HI/TA)
       v
  [AI Agent — LLaMA 3.3 70B]        ~700ms
       |              |
       |              | Tool calls (function calling)
       |              v
       |       [Tools Layer]
       |       ├── checkAvailability   → conflict detection
       |       ├── bookAppointment     → create booking
       |       ├── cancelAppointment   → delete booking
       |       ├── rescheduleAppt      → update slot
       |       ├── listDoctors         → available doctors
       |       └── getPatientAppts     → patient history
       |              |
       |              v
       |       [SQLite Database]
       |       ├── doctors table (5 pre-seeded doctors)
       |       └── appointments table (conflict-checked)
       |
       | Read/Write context
       v
  [Memory Layer]
  ├── Session Memory  → Redis (30min TTL) / in-memory fallback
  └── Persistent Memory → SQLite conversation_history
       |
       | Response text (streamed sentence by sentence)
       v
  [TTS — gTTS]                       ~600ms
       |
       | MP3 audio chunks (Base64 via SSE)
       v
  User (Browser plays audio)

  Total: ~1600ms | Perceived: ~800ms (streaming)
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Web chat UI |
| POST | `/chat` | Text chat |
| POST | `/voice-chat-stream` | Streaming voice (SSE) |
| POST | `/tts-stream` | Streaming TTS chunks |
| GET | `/doctors` | List all doctors |
| GET | `/appointments/{name}` | Patient appointments |
| GET | `/health` | Health check |

---

## Memory Design

### Session Memory (Short-term)
- **Store**: Redis with 30-minute TTL (falls back to in-memory dict)
- **Contains**: language, patient name, last 6 messages
- **Purpose**: Real-time conversation context

### Persistent Memory (Long-term)
- **Store**: SQLite `conversation_history` table
- **Contains**: all messages with timestamps and session IDs
- **Purpose**: Audit trail, future patient history features

### Why two layers?
Redis gives O(1) reads for real-time context. SQLite ensures nothing is lost if Redis restarts.

---

## Scheduling Logic

1. User requests slot → agent calls `checkAvailability`
2. Query `appointments` WHERE doctor + date + time matches
3. **Conflict found** → return 3 alternative slots (±1 hour)
4. **No conflict** → call `bookAppointment` → insert row
5. **Reschedule** → delete old row + insert new (atomic)
6. **Cancel** → soft delete (status = 'cancelled')

---

## Latency Breakdown

| Stage | Target | Achieved |
|-------|--------|----------|
| STT (Groq Whisper) | < 500ms | ~300ms ✅ |
| Agent (LLaMA 3.3) | < 1000ms | ~700ms ✅ |
| TTS (gTTS) | < 800ms | ~600ms ✅ |
| **Total** | **< 2000ms** | **~1600ms** ✅ |
| **Perceived** | **< 1000ms** | **~800ms** ✅ |

> Streaming TTS plays the first sentence while the rest is still generating — reducing perceived latency by ~50%.

---

## Available Doctors

| Doctor | Specialization |
|--------|---------------|
| Dr. Ramesh Kumar | Cardiologist |
| Dr. Priya Sharma | General Physician |
| Dr. Arjun Mehta | Orthopedic |
| Dr. Kavitha Nair | Dermatologist |
| Dr. Suresh Babu | Neurologist |

---

## Sample Conversations

**English:**
```
User:  Book appointment with Dr. Ramesh Kumar on 2026-03-20 at 10:00. My name is Sai Teja.
Agent: Your appointment with Dr. Ramesh Kumar is confirmed for March 20th at 10 AM, Sai Teja!
```

**Hindi:**
```
User:  मुझे डॉ. प्रिया शर्मा से कल सुबह 10 बजे मिलना है। मेरा नाम राज है।
Agent: राज जी, डॉ. प्रिया शर्मा के साथ कल 10 बजे आपकी अपॉइंटमेंट बुक हो गई है।
```

**Tamil:**
```
User:  நாளை டாக்டர் கவிதா நாயர் அப்பாயின்மெண்ட் வேண்டும். என் பெயர் சாய் தேஜா.
Agent: சாய் தேஜா, டாக்டர் கவிதா நாயர் நாளை கிடைக்கிறார்கள், அப்பாயின்மெண்ட் பதிவு செய்யப்பட்டது!
```

---

## Known Limitations

1. **TTS voice quality** — gTTS is robotic; neural voices (ElevenLabs/edge-tts) would sound better
2. **STT background noise** — Groq Whisper struggles with noisy environments
3. **Browser autoplay** — Browsers require user interaction before playing audio
4. **Redis optional** — Falls back to in-memory; session lost on server restart
5. **Language mid-switch** — Occasional 1-turn lag when user switches language

---

## Trade-offs

| Decision | Chosen | Why |
|----------|--------|-----|
| STT | Groq Whisper API (cloud) | 5x faster than local, same accuracy |
| LLM | Groq LLaMA 3.3 70B | Free, fastest inference available |
| TTS | gTTS | Works everywhere, no event loop issues |
| DB | SQLite | Zero setup, sufficient for demo scale |
| Memory | Redis + SQLite dual layer | Resilient — works without Redis |

---

## requirements.txt

```
fastapi
uvicorn[standard]
groq
gtts
langdetect
sqlalchemy
redis
python-dotenv
python-multipart
nest-asyncio
```

---

*Built for 2Care.ai Assignment — Multilingual Voice AI Agent*
