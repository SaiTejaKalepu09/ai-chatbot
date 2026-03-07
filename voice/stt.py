import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import tempfile
import sounddevice as sd
import numpy as np
import wave
from groq import Groq
from langdetect import detect
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────
# GROQ CLIENT (for Whisper API)
# ─────────────────────────────────────────

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ─────────────────────────────────────────
# AUDIO SETTINGS
# ─────────────────────────────────────────

SAMPLE_RATE    = 16000
CHANNELS       = 1
RECORD_SECONDS = 5

# ─────────────────────────────────────────
# LANGUAGE MAP — English, Hindi, Tamil
# ─────────────────────────────────────────

LANGUAGE_MAP = {
    "en": "en",
    "hi": "hi",
    "ta": "ta",   # Tamil
}

def detect_language(text: str) -> str:
    """Detect language from transcribed text"""
    try:
        detected = detect(text)
        return LANGUAGE_MAP.get(detected, "en")
    except Exception:
        return "en"


# ─────────────────────────────────────────
# TRANSCRIBE USING GROQ WHISPER API
# Much faster than local Whisper (~200ms vs ~1500ms)
# ─────────────────────────────────────────

def transcribe_audio_file(audio_path: str) -> dict:
    """
    Transcribe audio file using Groq Whisper API.
    Free and ~10x faster than local Whisper.
    """
    start_time = time.time()

    try:
        with open(audio_path, "rb") as audio_file:
            result = client.audio.transcriptions.create(
                file=(os.path.basename(audio_path), audio_file.read()),
                model="whisper-large-v3-turbo",  # fastest free Groq Whisper model
                response_format="verbose_json",
                language=None  # auto-detect
            )

        text      = result.text.strip()
        groq_lang = getattr(result, "language", None)
        language  = LANGUAGE_MAP.get(groq_lang, None)

        # Fallback to langdetect
        if not language:
            language = detect_language(text)

        end_time   = time.time()
        latency_ms = round((end_time - start_time) * 1000)

        print(f"📝 Transcribed: '{text}'")
        print(f"🌐 Language detected: {language}")
        print(f"⏱️  STT Latency: {latency_ms}ms")

        return {
            "success": True,
            "text": text,
            "language": language,
            "latency_ms": latency_ms
        }

    except Exception as e:
        end_time = time.time()
        print(f"❌ STT error: {e}")
        return {
            "success": False,
            "text": "",
            "language": "en",
            "latency_ms": round((end_time - start_time) * 1000),
            "error": str(e)
        }


# ─────────────────────────────────────────
# TRANSCRIBE FROM BYTES — Windows safe
# ─────────────────────────────────────────

def transcribe_audio_bytes(audio_bytes: bytes) -> dict:
    """
    Transcribe audio from raw bytes.
    Saves to temp file, transcribes via Groq API, cleans up.
    """
    temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    temp_path = temp_file.name
    temp_file.write(audio_bytes)
    temp_file.close()  # Close before reading (Windows fix)

    try:
        return transcribe_audio_file(temp_path)
    finally:
        try:
            time.sleep(0.1)
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        except Exception:
            pass


# ─────────────────────────────────────────
# RECORD AUDIO FROM MIC
# ─────────────────────────────────────────

def record_audio(duration: int = RECORD_SECONDS) -> np.ndarray:
    print(f"🎙️  Recording for {duration} seconds... Speak now!")
    audio_data = sd.rec(
        int(duration * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32"
    )
    sd.wait()
    print("✅ Recording complete!")
    return audio_data.flatten()


def save_audio_to_temp_file(audio_data: np.ndarray) -> str:
    temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    temp_path = temp_file.name

    with wave.open(temp_path, "w") as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        audio_int16 = (audio_data * 32767).astype(np.int16)
        wav_file.writeframes(audio_int16.tobytes())

    return temp_path


def listen_and_transcribe(duration: int = RECORD_SECONDS) -> dict:
    """Record from mic and transcribe — full pipeline"""
    total_start = time.time()
    audio_data  = record_audio(duration)
    temp_path   = save_audio_to_temp_file(audio_data)

    try:
        result = transcribe_audio_file(temp_path)
        result["total_latency_ms"] = round((time.time() - total_start) * 1000)
        return result
    finally:
        try:
            time.sleep(0.1)
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        except Exception:
            pass


# ─────────────────────────────────────────
# TEST STT
# ─────────────────────────────────────────

if __name__ == "__main__":
    print("🧪 Testing Groq Whisper STT...\n")
    print("Speak in English, Hindi, or Tamil!\n")

    input("Press ENTER to start recording...")

    result = listen_and_transcribe(duration=5)

    print(f"\n📊 Results:")
    print(f"  Text     : {result['text']}")
    print(f"  Language : {result['language']}")
    print(f"  Latency  : {result['latency_ms']}ms")

    lang_names = {"en": "English 🇬🇧", "hi": "Hindi 🇮🇳", "ta": "Tamil 🙏"}
    print(f"  Detected : {lang_names.get(result['language'], 'Unknown')}")