import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import tempfile
import re
from gtts import gTTS
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────
# gTTS — simple, reliable, works everywhere
# English, Hindi, Tamil
# ─────────────────────────────────────────

TTS_LANG_MAP = {
    "en": "en",
    "hi": "hi",
    "ta": "ta",
}

LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi",
    "ta": "Tamil"
}


def split_into_sentences(text: str) -> list:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in sentences if s.strip()]


def _gtts_to_bytes(text: str, language: str) -> bytes:
    """Convert text to mp3 bytes using gTTS"""
    lang = TTS_LANG_MAP.get(language, "en")
    tts  = gTTS(text=text, lang=lang, slow=False)
    temp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    temp.close()
    tts.save(temp.name)
    with open(temp.name, "rb") as f:
        data = f.read()
    try:
        os.unlink(temp.name)
    except Exception:
        pass
    return data


def text_to_speech_bytes(text: str, language: str = "en") -> dict:
    """Convert text to audio bytes — used by all endpoints"""
    start = time.time()
    try:
        audio_bytes = _gtts_to_bytes(text, language)
        ms = round((time.time() - start) * 1000)
        print(f"TTS {LANGUAGE_NAMES.get(language, 'en')}: {ms}ms")
        return {"success": True, "audio_bytes": audio_bytes, "language": language, "latency_ms": ms}
    except Exception as e:
        ms = round((time.time() - start) * 1000)
        print(f"TTS error: {e}")
        return {"success": False, "audio_bytes": None, "language": language, "latency_ms": ms, "error": str(e)}


def stream_tts_bytes(text: str, language: str = "en") -> list:
    """Convert sentence by sentence — returns list of audio chunks"""
    total_start = time.time()
    sentences   = split_into_sentences(text)
    if not sentences:
        sentences = [text]

    chunks = []
    for i, sentence in enumerate(sentences):
        chunk_start = time.time()
        try:
            audio_bytes   = _gtts_to_bytes(sentence, language)
            chunk_latency = round((time.time() - chunk_start) * 1000)
            print(f"Chunk {i+1}/{len(sentences)}: {chunk_latency}ms")
            chunks.append({"index": i, "bytes": audio_bytes, "text": sentence, "latency": chunk_latency})
        except Exception as e:
            print(f"Chunk {i+1} error: {e}")

    print(f"Total TTS: {round((time.time()-total_start)*1000)}ms")
    return chunks


def text_to_speech_file(text: str, language: str = "en") -> dict:
    """Convert text to speech file"""
    start = time.time()
    try:
        lang = TTS_LANG_MAP.get(language, "en")
        tts  = gTTS(text=text, lang=lang, slow=False)
        temp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        temp.close()
        tts.save(temp.name)
        ms = round((time.time() - start) * 1000)
        return {"success": True, "audio_path": temp.name, "language": language, "latency_ms": ms}
    except Exception as e:
        return {"success": False, "audio_path": None, "language": language, "latency_ms": round((time.time()-start)*1000), "error": str(e)}


def play_audio(audio_path: str):
    try:
        if sys.platform == "win32":
            os.system(f'start "" "{audio_path}"')
    except Exception as e:
        print(f"Could not play audio: {e}")


def speak(text: str, language: str = "en", play: bool = True) -> dict:
    result = text_to_speech_file(text, language)
    if result["success"] and play:
        play_audio(result["audio_path"])
    return result


RESPONSES = {
    "greeting": {
        "en": "Hello! I am your clinical appointment assistant.",
        "hi": "Namaste! Main aapka appointment assistant hoon.",
        "ta": "Vanakkam! Naan ungal appointment assistant."
    },
    "error": {
        "en": "I am sorry, something went wrong. Please try again.",
        "hi": "Maaf karen, kuch gadbad ho gayi.",
        "ta": "Mannikkavum, etho thavaru nadanthathu."
    },
    "goodbye": {
        "en": "Thank you! Take care. Goodbye!",
        "hi": "Dhanyavaad! Alvida!",
        "ta": "Nandri! Vidai!"
    }
}

def get_response_template(key: str, language: str = "en") -> str:
    return RESPONSES.get(key, {}).get(language, RESPONSES.get(key, {}).get("en", ""))


if __name__ == "__main__":
    print("Testing gTTS...")
    r = text_to_speech_bytes("Your appointment is confirmed for tomorrow at 10 AM.", "en")
    print(f"Success: {r['success']}, Bytes: {len(r['audio_bytes'] or b'')}, ms: {r['latency_ms']}")
    r2 = text_to_speech_bytes("Aapki appointment kal subah 10 baje hai.", "hi")
    print(f"Hindi - Success: {r2['success']}, ms: {r2['latency_ms']}")
    r3 = text_to_speech_bytes("Ungal appointment naalai kaalaai 10 manikku.", "ta")
    print(f"Tamil - Success: {r3['success']}, ms: {r3['latency_ms']}")