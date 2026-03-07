import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import redis
from datetime import datetime
from dotenv import load_dotenv
from database.models import ConversationHistory, SessionLocal

load_dotenv()

# ─────────────────────────────────────────
# REDIS CONNECTION (Session Memory)
# ─────────────────────────────────────────

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

def get_redis_client():
    """Get Redis client — returns None if Redis is not available"""
    try:
        r = redis.from_url(REDIS_URL, decode_responses=True)
        r.ping()  # Test connection
        return r
    except Exception as e:
        print(f"⚠️  Redis not available: {e}")
        print("ℹ️  Falling back to in-memory session storage")
        return None


# In-memory fallback if Redis is not running
IN_MEMORY_SESSIONS = {}

# ─────────────────────────────────────────
# SESSION MEMORY (Current Conversation)
# Uses Redis — fast, temporary
# ─────────────────────────────────────────

class SessionMemory:
    """
    Stores the current conversation context in Redis.
    Data expires after 30 minutes of inactivity.
    """

    SESSION_TTL = 1800  # 30 minutes in seconds

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.redis = get_redis_client()
        self.key = f"session:{session_id}"

    def get_context(self) -> dict:
        """Get full session context"""
        try:
            if self.redis:
                data = self.redis.get(self.key)
                if data:
                    return json.loads(data)
            else:
                return IN_MEMORY_SESSIONS.get(self.session_id, {})
        except Exception as e:
            print(f"❌ Error getting session context: {e}")

        return {}

    def save_context(self, context: dict):
        """Save session context"""
        try:
            if self.redis:
                self.redis.setex(
                    self.key,
                    self.SESSION_TTL,
                    json.dumps(context)
                )
            else:
                IN_MEMORY_SESSIONS[self.session_id] = context
        except Exception as e:
            print(f"❌ Error saving session context: {e}")

    def get_conversation_history(self) -> list:
        """Get conversation history for this session"""
        context = self.get_context()
        return context.get("history", [])

    def add_message(self, role: str, message: str, language: str = "en"):
        """Add a message to conversation history"""
        context = self.get_context()
        if "history" not in context:
            context["history"] = []

        context["history"].append({
            "role": role,
            "content": message,
            "language": language,
            "timestamp": datetime.utcnow().isoformat()
        })

        # Keep only last 20 messages in session
        if len(context["history"]) > 20:
            context["history"] = context["history"][-20:]

        self.save_context(context)

    def get_patient_name(self) -> str:
        """Get patient name from session"""
        context = self.get_context()
        return context.get("patient_name", "")

    def set_patient_name(self, name: str):
        """Save patient name to session"""
        context = self.get_context()
        context["patient_name"] = name
        self.save_context(context)

    def get_language(self) -> str:
        """Get detected language for this session"""
        context = self.get_context()
        return context.get("language", "en")

    def set_language(self, language: str):
        """Save detected language"""
        context = self.get_context()
        context["language"] = language
        self.save_context(context)

    def get_pending_intent(self) -> dict:
        """Get pending intent (e.g. booking in progress)"""
        context = self.get_context()
        return context.get("pending_intent", {})

    def set_pending_intent(self, intent: dict):
        """Save pending intent"""
        context = self.get_context()
        context["pending_intent"] = intent
        self.save_context(context)

    def clear_pending_intent(self):
        """Clear pending intent after completion"""
        context = self.get_context()
        context["pending_intent"] = {}
        self.save_context(context)

    def clear_session(self):
        """Clear entire session"""
        try:
            if self.redis:
                self.redis.delete(self.key)
            else:
                IN_MEMORY_SESSIONS.pop(self.session_id, None)
            print(f"🗑️  Session {self.session_id} cleared")
        except Exception as e:
            print(f"❌ Error clearing session: {e}")

    def get_full_summary(self) -> dict:
        """Get full session summary for debugging"""
        context = self.get_context()
        return {
            "session_id": self.session_id,
            "patient_name": context.get("patient_name", "Unknown"),
            "language": context.get("language", "en"),
            "message_count": len(context.get("history", [])),
            "pending_intent": context.get("pending_intent", {}),
            "last_messages": context.get("history", [])[-3:]
        }


# ─────────────────────────────────────────
# PERSISTENT MEMORY (Long-term History)
# Uses SQLite DB — permanent storage
# ─────────────────────────────────────────

class PersistentMemory:
    """
    Stores long-term conversation history in SQLite database.
    Survives server restarts.
    """

    def save_message(
        self,
        session_id: str,
        role: str,
        message: str,
        language: str = "en",
        patient_name: str = ""
    ):
        """Save a message to permanent database"""
        db = SessionLocal()
        try:
            record = ConversationHistory(
                session_id=session_id,
                patient_name=patient_name,
                role=role,
                message=message,
                language=language
            )
            db.add(record)
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"❌ Error saving to persistent memory: {e}")
        finally:
            db.close()

    def get_patient_history(self, patient_name: str, limit: int = 20) -> list:
        """Get past conversation history for a patient"""
        db = SessionLocal()
        try:
            records = db.query(ConversationHistory).filter(
                ConversationHistory.patient_name.ilike(f"%{patient_name}%")
            ).order_by(
                ConversationHistory.created_at.desc()
            ).limit(limit).all()

            return [{
                "role": r.role,
                "message": r.message,
                "language": r.language,
                "timestamp": r.created_at.isoformat(),
                "session_id": r.session_id
            } for r in reversed(records)]

        except Exception as e:
            print(f"❌ Error getting patient history: {e}")
            return []
        finally:
            db.close()

    def get_session_history(self, session_id: str) -> list:
        """Get full history for a session"""
        db = SessionLocal()
        try:
            records = db.query(ConversationHistory).filter(
                ConversationHistory.session_id == session_id
            ).order_by(ConversationHistory.created_at).all()

            return [{
                "role": r.role,
                "content": r.message,
                "language": r.language
            } for r in records]

        except Exception as e:
            print(f"❌ Error getting session history: {e}")
            return []
        finally:
            db.close()


# ─────────────────────────────────────────
# COMBINED MEMORY MANAGER
# Easy interface used by the agent
# ─────────────────────────────────────────

class MemoryManager:
    """
    Single interface for all memory operations.
    Used by the FastAPI server and agent.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.session = SessionMemory(session_id)
        self.persistent = PersistentMemory()

    def add_user_message(self, message: str, language: str = "en"):
        """Save user message to both session and persistent memory"""
        patient_name = self.session.get_patient_name()

        # Save to session (Redis)
        self.session.add_message("user", message, language)

        # Save to DB
        self.persistent.save_message(
            session_id=self.session_id,
            role="user",
            message=message,
            language=language,
            patient_name=patient_name
        )

    def add_agent_message(self, message: str, language: str = "en"):
        """Save agent response to both session and persistent memory"""
        patient_name = self.session.get_patient_name()

        # Save to session (Redis)
        self.session.add_message("assistant", message, language)

        # Save to DB
        self.persistent.save_message(
            session_id=self.session_id,
            role="assistant",
            message=message,
            language=language,
            patient_name=patient_name
        )

    def get_history_for_agent(self) -> list:
        """Get conversation history formatted for LLM agent"""
        history = self.session.get_conversation_history()
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in history
        ]

    def get_patient_name(self) -> str:
        return self.session.get_patient_name()

    def set_patient_name(self, name: str):
        self.session.set_patient_name(name)

    def get_language(self) -> str:
        return self.session.get_language()

    def set_language(self, language: str):
        self.session.set_language(language)

    def get_summary(self) -> dict:
        return self.session.get_full_summary()


# ─────────────────────────────────────────
# TEST MEMORY
# ─────────────────────────────────────────

if __name__ == "__main__":
    print("🧪 Testing Memory System...\n")

    # Create a memory manager
    memory = MemoryManager(session_id="test-session-001")

    # Set patient info
    memory.set_patient_name("Sai Teja")
    memory.set_language("en")

    # Simulate conversation
    memory.add_user_message("I want to book an appointment", "en")
    memory.add_agent_message("Sure! Which doctor would you like to see?", "en")
    memory.add_user_message("Dr. Ramesh Kumar please", "en")
    memory.add_agent_message("What date and time works for you?", "en")

    # Check session summary
    print("📋 Session Summary:")
    print(json.dumps(memory.get_summary(), indent=2))
    print()

    # Check history for agent
    print("🤖 History for Agent:")
    for msg in memory.get_history_for_agent():
        print(f"  [{msg['role']}]: {msg['content']}")
    print()

    # Test persistent memory
    print("💾 Persistent History for Sai Teja:")
    persistent = PersistentMemory()
    history = persistent.get_patient_history("Sai Teja")
    for msg in history:
        print(f"  [{msg['role']}]: {msg['message']}")

    print("\n✅ Memory tests done!")