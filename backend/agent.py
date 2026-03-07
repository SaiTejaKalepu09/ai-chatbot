import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import time
from groq import Groq
from dotenv import load_dotenv
from backend.tools import TOOLS, execute_tool

load_dotenv()

# ─────────────────────────────────────────
# GROQ CLIENT
# ─────────────────────────────────────────

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL  = "llama-3.3-70b-versatile"


# ─────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────

SYSTEM_PROMPT = """You are a multilingual clinical appointment booking assistant for 2Care.ai.

CRITICAL LANGUAGE RULE:
- If the user writes in Hindi (Devanagari script like मुझे, आप, डॉक्टर) → You MUST reply in Hindi using Devanagari script
- If the user writes in Tamil (Tamil script like நான், மருத்துவர்) → You MUST reply in Tamil using Tamil script  
- If the user writes in English → reply in English
- NEVER respond in transliteration (DO NOT write "Namaste" or "Vanakkam" — use actual scripts)
- NEVER mix languages in one response

Your tasks:
1. Book appointments
2. Cancel appointments
3. Reschedule appointments
4. Check doctor availability
5. List available doctors

Available Doctors:
- Dr. Ramesh Kumar (Cardiologist)
- Dr. Priya Sharma (General Physician)
- Dr. Arjun Mehta (Orthopedic)
- Dr. Kavitha Nair (Dermatologist)
- Dr. Suresh Babu (Neurologist)

Rules:
- Always confirm patient name before booking
- Use YYYY-MM-DD HH:MM format for dates internally
- Keep responses SHORT — max 2 sentences for voice
- Suggest alternatives if slot unavailable

Examples:
User: "मुझे डॉक्टर से मिलना है" → Reply: "आप किस डॉक्टर से मिलना चाहते हैं?"
User: "நாளை அப்பாயின்மெண்ட் வேண்டும்" → Reply: "எந்த டாக்டரிடம் அப்பாயின்மெண்ட் வேண்டும்?"
User: "Book appointment" → Reply: "Which doctor would you like to see?"
"""


# ─────────────────────────────────────────
# STREAMING AGENT
# Yields text chunks as they are generated
# ─────────────────────────────────────────

def run_agent_streaming(
    user_message: str,
    conversation_history: list = [],
    language: str = "en",
    patient_name: str = ""
):
    """
    Streaming agent — yields text as it's generated.
    Used by the streaming voice endpoint.

    Yields:
        dict with type: 'text_chunk', 'tool_call', 'done', 'error'
    """
    start_time = time.time()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if conversation_history:
        messages.extend(conversation_history[-6:])
    messages.append({"role": "user", "content": user_message})

    tool_calls_made = []

    try:
        # ── First call — check for tool use (non-streaming) ──
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=512,
            temperature=0.2
        )

        response_message = response.choices[0].message

        # ── Handle tool calls ──
        if response_message.tool_calls:
            messages.append({
                "role": "assistant",
                "content": response_message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in response_message.tool_calls
                ]
            })

            for tool_call in response_message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)
                if not tool_args:
                    tool_args = {}

                print(f"🔧 Tool: {tool_name}")
                yield {"type": "tool_call", "tool": tool_name}

                tool_result = execute_tool(tool_name, tool_args)
                tool_calls_made.append({"tool": tool_name, "args": tool_args, "result": tool_result})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result
                })

            # ── Streaming second call after tool results ──
            stream = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                max_tokens=256,
                temperature=0.2,
                stream=True   # ✅ Enable streaming
            )

        else:
            # ── Streaming direct response ──
            stream = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}]
                         + (conversation_history[-6:] if conversation_history else [])
                         + [{"role": "user", "content": user_message}],
                max_tokens=256,
                temperature=0.2,
                stream=True   # ✅ Enable streaming
            )

        # ── Stream text chunks ──
        full_response   = ""
        sentence_buffer = ""
        first_chunk_time = None

        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                text_piece = delta.content

                if first_chunk_time is None:
                    first_chunk_time = round((time.time() - start_time) * 1000)
                    print(f"⚡ First token: {first_chunk_time}ms")

                full_response   += text_piece
                sentence_buffer += text_piece

                # Yield complete sentences immediately for TTS
                import re
                sentences = re.split(r'(?<=[.!?।])\s+', sentence_buffer)

                if len(sentences) > 1:
                    # Yield all complete sentences
                    for sentence in sentences[:-1]:
                        if sentence.strip():
                            yield {
                                "type": "sentence",
                                "text": sentence.strip(),
                                "language": language
                            }
                    # Keep incomplete sentence in buffer
                    sentence_buffer = sentences[-1]

        # Yield any remaining text
        if sentence_buffer.strip():
            yield {
                "type": "sentence",
                "text": sentence_buffer.strip(),
                "language": language
            }

        total_latency = round((time.time() - start_time) * 1000)
        print(f"⏱️  Total agent: {total_latency}ms")

        # Update history
        updated_history = conversation_history.copy()
        updated_history.append({"role": "user",      "content": user_message})
        updated_history.append({"role": "assistant", "content": full_response})
        if len(updated_history) > 6:
            updated_history = updated_history[-6:]

        yield {
            "type": "done",
            "full_response": full_response,
            "language": language,
            "latency_ms": total_latency,
            "first_token_ms": first_chunk_time,
            "tool_calls": tool_calls_made,
            "updated_history": updated_history
        }

    except Exception as e:
        print(f"❌ Agent error: {e}")
        if language == "hi":
            error_msg = "माफ करें, कुछ गड़बड़ हो गई।"
        elif language == "ta":
            error_msg = "மன்னிக்கவும், ஏதோ தவறு நடந்தது."
        else:
            error_msg = "I'm sorry, I encountered an error. Please try again."

        yield {
            "type": "error",
            "text": error_msg,
            "language": language,
            "error": str(e)
        }


# ─────────────────────────────────────────
# STANDARD AGENT (non-streaming, for text chat)
# ─────────────────────────────────────────

def run_agent(
    user_message: str,
    conversation_history: list = [],
    language: str = "en",
    patient_name: str = ""
) -> dict:
    """Standard non-streaming agent for text chat endpoint"""
    start_time      = time.time()
    messages        = [{"role": "system", "content": SYSTEM_PROMPT}]
    tool_calls_made = []

    if conversation_history:
        messages.extend(conversation_history[-6:])
    messages.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=512,
            temperature=0.2
        )

        response_message = response.choices[0].message

        if response_message.tool_calls:
            messages.append({
                "role": "assistant",
                "content": response_message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                    }
                    for tc in response_message.tool_calls
                ]
            })

            for tool_call in response_message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)
                if not tool_args:
                    tool_args = {}

                print(f"🔧 Tool: {tool_name} args: {tool_args}")
                tool_result = execute_tool(tool_name, tool_args)
                tool_calls_made.append({"tool": tool_name, "args": tool_args, "result": tool_result})
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": tool_result})

            second = client.chat.completions.create(
                model=MODEL, messages=messages, max_tokens=256, temperature=0.2
            )
            final_response = second.choices[0].message.content
        else:
            final_response = response_message.content

        latency_ms = round((time.time() - start_time) * 1000)
        print(f"⏱️  Agent: {latency_ms}ms")

        updated_history = conversation_history.copy()
        updated_history.append({"role": "user",      "content": user_message})
        updated_history.append({"role": "assistant", "content": final_response})
        if len(updated_history) > 6:
            updated_history = updated_history[-6:]

        return {
            "success": True,
            "response": final_response,
            "language": language,
            "latency_ms": latency_ms,
            "tool_calls": tool_calls_made,
            "updated_history": updated_history
        }

    except Exception as e:
        if language == "hi":
            error_msg = "माफ करें, कुछ गड़बड़ हो गई। कृपया दोबारा कोशिश करें।"
        elif language == "ta":
            error_msg = "மன்னிக்கவும், ஏதோ தவறு நடந்தது. மீண்டும் முயற்சிக்கவும்."
        else:
            error_msg = "I'm sorry, I encountered an error. Please try again."

        print(f"❌ Agent error: {e}")
        return {
            "success": False,
            "response": error_msg,
            "language": language,
            "latency_ms": round((time.time() - start_time) * 1000),
            "tool_calls": [],
            "updated_history": conversation_history,
            "error": str(e)
        }


if __name__ == "__main__":
    print("🧪 Testing Streaming Agent...\n")

    print("Streaming test:")
    for event in run_agent_streaming("What doctors are available?"):
        if event["type"] == "sentence":
            print(f"  🔊 Speak now: '{event['text']}'")
        elif event["type"] == "done":
            print(f"  ✅ Done! Total: {event['latency_ms']}ms, First token: {event['first_token_ms']}ms")
        elif event["type"] == "error":
            print(f"  ❌ Error: {event['text']}")