import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import json
import uuid
import base64
import asyncio
import concurrent.futures
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

from database.models import init_db, seed_doctors
from backend.agent import run_agent, run_agent_streaming
from backend.memory import MemoryManager
from backend.tools import listDoctors, getPatientAppointments
from voice.tts import text_to_speech_bytes, stream_tts_bytes, split_into_sentences
from voice.stt import transcribe_audio_bytes

load_dotenv()

executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting 2Care.ai Voice AI Agent...")
    init_db()
    seed_doctors()
    print("Server ready!")
    yield

app = FastAPI(title="2Care.ai Voice AI Agent", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    language: Optional[str] = "en"
    patient_name: Optional[str] = ""

class ChatResponse(BaseModel):
    response: str
    session_id: str
    language: str
    latency_ms: int
    tool_calls: list = []

def log_latency(stage, ms):
    print(f"{'OK' if ms < 800 else 'SLOW'} [{stage}] {ms}ms")

HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>2Care.ai Voice AI Agent</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',sans-serif;background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;color:white;padding:20px}
.container{width:100%;max-width:650px;display:flex;flex-direction:column;gap:14px}
.header{text-align:center}
.header h1{font-size:26px;color:#00d4ff}
.header p{font-size:13px;color:#aaa;margin-top:4px}
.lang-row{display:flex;gap:8px;justify-content:center;flex-wrap:wrap}
.lang-btn{padding:6px 16px;border-radius:20px;border:1px solid #00d4ff;background:rgba(0,212,255,0.1);color:#00d4ff;cursor:pointer;font-size:13px}
.lang-btn:hover{background:rgba(0,212,255,0.3)}
.chat-box{width:100%;height:360px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:15px;overflow-y:auto;display:flex;flex-direction:column;gap:10px}
.message{max-width:82%;padding:10px 14px;border-radius:12px;font-size:14px;line-height:1.6}
.user-msg{background:#0f3460;border:1px solid rgba(0,212,255,.3);align-self:flex-end;color:#e0f7ff}
.agent-msg{background:rgba(0,212,255,.08);border:1px solid rgba(0,212,255,.15);align-self:flex-start}
.tag{font-size:10px;color:#00d4ff88;margin-top:5px}
.input-row{display:flex;gap:10px;align-items:center}
.text-input{flex:1;padding:14px 16px;border-radius:12px;border:1px solid rgba(255,255,255,.15);background:rgba(255,255,255,.07);color:white;font-size:15px;outline:none}
.text-input::placeholder{color:#666}
.text-input:focus{border-color:#00d4ff}
.send-btn{padding:14px 24px;border-radius:12px;border:none;background:#00d4ff;color:#0f3460;font-weight:700;font-size:15px;cursor:pointer}
.send-btn:hover{background:#00b8d9}
.mic-btn{width:54px;height:54px;border-radius:50%;border:2px solid #00d4ff;background:rgba(0,212,255,.1);font-size:22px;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.mic-btn:hover{background:rgba(0,212,255,.25)}
.mic-btn.rec{border-color:#ff4444;background:rgba(255,68,68,.2);animation:pulse 1s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(255,68,68,.5)}70%{box-shadow:0 0 0 12px rgba(255,68,68,0)}100%{box-shadow:0 0 0 0 rgba(255,68,68,0)}}
.viz{display:none;justify-content:center;gap:5px;align-items:center;height:28px}
.viz.on{display:flex}
.dot{width:6px;border-radius:3px;background:#ff4444;animation:wave 1s ease-in-out infinite}
.dot:nth-child(1){height:8px;animation-delay:.0s}.dot:nth-child(2){height:16px;animation-delay:.1s}.dot:nth-child(3){height:22px;animation-delay:.2s}.dot:nth-child(4){height:16px;animation-delay:.3s}.dot:nth-child(5){height:8px;animation-delay:.4s}
@keyframes wave{0%,100%{transform:scaleY(.5)}50%{transform:scaleY(1.3)}}
.status{text-align:center;font-size:12px;color:#aaa;min-height:18px}
.status.on{color:#00d4ff}.status.err{color:#ff6b6b}
.latency-row{display:none;gap:8px;justify-content:center;flex-wrap:wrap;font-size:11px}
.latency-row.on{display:flex}
.pill{padding:3px 12px;border-radius:10px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);color:#aaa}
.pill.good{color:#00d4ff;border-color:rgba(0,212,255,.3)}
.pill.warn{color:#ffaa00;border-color:rgba(255,170,0,.3)}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>2Care.ai Voice AI Agent</h1>
    <p>Multilingual Clinical Appointment Booking - English | Hindi | Tamil</p>
  </div>
  <div class="lang-row">
    <button class="lang-btn" id="btnEn">English Example</button>
    <button class="lang-btn" id="btnHi">Hindi Example</button>
    <button class="lang-btn" id="btnTa">Tamil Example</button>
  </div>
  <div class="chat-box" id="chatBox">
    <div class="message agent-msg">Hello! I am your clinical appointment assistant. Type or press the mic button to speak.</div>
  </div>
  <div class="viz" id="viz">
    <div class="dot"></div><div class="dot"></div><div class="dot"></div><div class="dot"></div><div class="dot"></div>
  </div>
  <div class="latency-row" id="latencyRow">
    <div class="pill" id="pSTT">STT: --</div>
    <div class="pill" id="pAgent">Agent: --</div>
    <div class="pill" id="pTTS">TTS: --</div>
    <div class="pill" id="pTotal">Total: --</div>
  </div>
  <div class="status" id="statusBar">Ready - type or speak</div>
  <div class="input-row">
    <input type="text" class="text-input" id="msgInput" placeholder="Type your message here..." />
    <button class="mic-btn" id="micBtn">MIC</button>
    <button class="send-btn" id="sendBtn">Send</button>
  </div>
</div>
<script>
var sessionId=null,isRecording=false,mediaRecorder=null,audioChunks=[],audioQueue=[],isPlaying=false;
function qs(id){return document.getElementById(id)}
function setStatus(msg,cls){var el=qs('statusBar');el.textContent=msg;el.className='status '+(cls||'')}
function addMsg(text,role,latency){
  var box=qs('chatBox'),d=document.createElement('div');
  d.className='message '+(role==='user'?'user-msg':'agent-msg');
  d.textContent=text;
  if(latency){var t=document.createElement('div');t.className='tag';t.textContent='Latency: '+latency+'ms';d.appendChild(t)}
  box.appendChild(d);box.scrollTop=box.scrollHeight;return d
}
function updateLatency(stt,agent,tts,total){
  qs('latencyRow').className='latency-row on';
  function sp(id,label,val,thr){var el=qs(id);el.textContent=label+': '+val+'ms';el.className='pill '+(val<thr?'good':'warn')}
  if(stt!=null)sp('pSTT','STT',stt,800);
  if(agent!=null)sp('pAgent','Agent',agent,1000);
  if(tts!=null)sp('pTTS','TTS',tts,800);
  if(total!=null)sp('pTotal','Total',total,2000)
}
function playAudio(b64){audioQueue.push(b64);if(!isPlaying)playNext()}
function playNext(){
  if(!audioQueue.length){isPlaying=false;return}
  isPlaying=true;
  var b64=audioQueue.shift();
  var bytes=Uint8Array.from(atob(b64),function(c){return c.charCodeAt(0)});
  var blob=new Blob([bytes],{type:'audio/mp3'});
  var url=URL.createObjectURL(blob);
  var audio=new Audio(url);
  audio.onended=function(){URL.revokeObjectURL(url);playNext()};
  audio.onerror=function(){URL.revokeObjectURL(url);playNext()};
  audio.play().catch(function(){playNext()})
}
function sendText(){
  var message=qs('msgInput').value.trim();
  if(!message)return;
  addMsg(message,'user');qs('msgInput').value='';
  setStatus('Agent is thinking...','on');
  audioQueue=[];isPlaying=false;
  fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:message,session_id:sessionId})})
  .then(function(r){return r.json()})
  .then(function(d){
    sessionId=d.session_id;
    addMsg(d.response,'agent',d.latency_ms);
    updateLatency(null,d.latency_ms,null,d.latency_ms);
    setStatus('Ready - type or speak');
    speakText(d.response,d.language)
  })
  .catch(function(){addMsg('Error. Try again.','agent');setStatus('Error','err')})
}
function speakText(text,lang){
  fetch('/tts-stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:text,language:lang||'en'})})
  .then(function(r){return r.json()})
  .then(function(d){if(d.chunks)d.chunks.forEach(function(c){playAudio(c)})})
  .catch(function(e){console.warn('TTS error',e)})
}
function toggleMic(){if(!isRecording)startRec();else stopRec()}
function startRec(){
  navigator.mediaDevices.getUserMedia({audio:true})
  .then(function(stream){
    mediaRecorder=new MediaRecorder(stream);audioChunks=[];
    mediaRecorder.ondataavailable=function(e){if(e.data.size>0)audioChunks.push(e.data)};
    mediaRecorder.onstop=function(){
      var blob=new Blob(audioChunks,{type:'audio/webm'});
      sendVoice(blob);
      stream.getTracks().forEach(function(t){t.stop()})
    };
    mediaRecorder.start();isRecording=true;
    qs('micBtn').classList.add('rec');qs('micBtn').textContent='STOP';
    qs('viz').classList.add('on');
    setStatus('Recording... click mic to stop','on');
    audioQueue=[];isPlaying=false
  })
  .catch(function(){setStatus('Microphone access denied','err')})
}
function stopRec(){
  if(mediaRecorder&&isRecording){
    mediaRecorder.stop();isRecording=false;
    qs('micBtn').classList.remove('rec');qs('micBtn').textContent='MIC';
    qs('viz').classList.remove('on');
    setStatus('Processing voice...','on')
  }
}
function sendVoice(audioBlob){
  var form=new FormData();
  form.append('audio',audioBlob,'recording.webm');
  if(sessionId)form.append('session_id',sessionId);
  fetch('/voice-chat-stream',{method:'POST',body:form})
  .then(function(res){
    var reader=res.body.getReader(),decoder=new TextDecoder();
    var agentEl=null,fullText='',sttMs=0,agentMs=0,ttsMs=0;
    function read(){
      reader.read().then(function(result){
        if(result.done)return;
        var lines=decoder.decode(result.value).split(String.fromCharCode(10));
        lines.forEach(function(line){
          if(!line.startsWith('data: '))return;
          try{
            var ev=JSON.parse(line.slice(6));
            if(ev.type==='transcription'){addMsg('You said: '+ev.text,'user');setStatus('Agent responding...','on');sttMs=ev.latency_ms||0}
            else if(ev.type==='sentence'){
              fullText+=(fullText?' ':'')+ev.text;
              if(!agentEl){agentEl=addMsg(fullText,'agent')}
              else{agentEl.childNodes[0].textContent=fullText}
              if(ev.audio_b64)playAudio(ev.audio_b64);
              ttsMs+=ev.tts_ms||0
            }
            else if(ev.type==='done'){
              sessionId=ev.session_id;agentMs=ev.agent_ms||0;
              updateLatency(sttMs,agentMs,ttsMs,ev.total_ms||0);
              setStatus('Done - '+(ev.language==='hi'?'Hindi':ev.language==='ta'?'Tamil':'English')+' detected')
            }
            else if(ev.type==='error'){addMsg(ev.text||'Error','agent');setStatus('Error','err')}
          }catch(e){}
        });
        read()
      }).catch(function(){setStatus('Connection error','err')})
    }
    read()
  })
  .catch(function(){addMsg('Voice failed.','agent');setStatus('Error','err')})
}
qs('sendBtn').addEventListener('click',sendText);
qs('micBtn').addEventListener('click',toggleMic);
qs('msgInput').addEventListener('keypress',function(e){if(e.key==='Enter')sendText()});
qs('btnEn').addEventListener('click',function(){qs('msgInput').value='Book appointment with Dr. Ramesh Kumar on 2026-03-20 at 10:00. My name is Sai Teja'});
qs('btnHi').addEventListener('click',function(){qs('msgInput').value='मुझे डॉ. प्रिया शर्मा से कल सुबह 10 बजे मिलना है। मेरा नाम राज है।'});
qs('btnTa').addEventListener('click',function(){qs('msgInput').value='நாளை டாக்டர் கவிதா நாயர் அப்பாயின்மெண்ட் வேண்டும். என் பெயர் சாய் தேஜா.'});
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def root():
    return HTML_PAGE

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    total_start = time.time()
    session_id  = request.session_id or str(uuid.uuid4())
    memory      = MemoryManager(session_id)
    if request.patient_name:
        memory.set_patient_name(request.patient_name)
    history  = memory.get_history_for_agent()
    language = memory.get_language() or request.language
    memory.add_user_message(request.message, language)
    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, lambda: run_agent(
        user_message=request.message, conversation_history=history,
        language=language, patient_name=memory.get_patient_name()
    ))
    if result.get("language"):
        memory.set_language(result["language"])
    memory.add_agent_message(result["response"], result.get("language", language))
    total_latency = round((time.time() - total_start) * 1000)
    log_latency("Total /chat", total_latency)
    return ChatResponse(response=result["response"], session_id=session_id,
        language=result.get("language", language), latency_ms=total_latency,
        tool_calls=result.get("tool_calls", []))

@app.post("/tts-stream")
async def tts_stream(request: dict):
    text     = request.get("text", "")
    language = request.get("language", "en")
    loop     = asyncio.get_event_loop()
    chunks   = await loop.run_in_executor(executor, lambda: stream_tts_bytes(text, language))
    return JSONResponse({"success": True, "chunks": [base64.b64encode(c["bytes"]).decode() for c in chunks], "count": len(chunks)})

@app.post("/tts")
async def tts_endpoint(request: dict):
    text     = request.get("text", "")
    language = request.get("language", "en")
    loop     = asyncio.get_event_loop()
    result   = await loop.run_in_executor(executor, lambda: text_to_speech_bytes(text, language))
    if result["success"]:
        return Response(content=result["audio_bytes"], media_type="audio/mp3")
    return JSONResponse(status_code=500, content={"error": "TTS failed"})

@app.post("/voice-chat-stream")
async def voice_chat_stream(audio: UploadFile = File(...), session_id: Optional[str] = Form(None)):
    total_start = time.time()
    session_id  = session_id or str(uuid.uuid4())
    memory      = MemoryManager(session_id)
    audio_bytes = await audio.read()

    async def stream_response():
        loop = asyncio.get_event_loop()
        stt_start   = time.time()
        stt_result  = await loop.run_in_executor(executor, lambda: transcribe_audio_bytes(audio_bytes))
        stt_latency = round((time.time() - stt_start) * 1000)
        if not stt_result["success"] or not stt_result["text"].strip():
            yield 'data: ' + json.dumps({"type": "error", "text": "Could not hear you."}) + '\n\n'
            return
        user_text = stt_result["text"]
        language  = stt_result["language"]
        memory.set_language(language)
        memory.add_user_message(user_text, language)
        yield 'data: ' + json.dumps({"type": "transcription", "text": user_text, "language": language, "latency_ms": stt_latency}) + '\n\n'
        agent_start  = time.time()
        agent_result = await loop.run_in_executor(executor, lambda: run_agent(
            user_message=user_text, conversation_history=memory.get_history_for_agent(),
            language=language, patient_name=memory.get_patient_name()
        ))
        agent_latency = round((time.time() - agent_start) * 1000)
        response_text = agent_result["response"]
        memory.add_agent_message(response_text, language)
        sentences    = split_into_sentences(response_text) or [response_text]
        total_tts_ms = 0
        for sentence in sentences:
            tts_start  = time.time()
            tts_result = await loop.run_in_executor(executor, lambda s=sentence: text_to_speech_bytes(s, language))
            tts_ms     = round((time.time() - tts_start) * 1000)
            total_tts_ms += tts_ms
            audio_b64 = base64.b64encode(tts_result["audio_bytes"]).decode() if tts_result["success"] else None
            yield 'data: ' + json.dumps({"type": "sentence", "text": sentence, "audio_b64": audio_b64, "tts_ms": tts_ms}) + '\n\n'
        total_ms = round((time.time() - total_start) * 1000)
        log_latency("STT",   stt_latency)
        log_latency("Agent", agent_latency)
        log_latency("TTS",   total_tts_ms)
        log_latency("Total", total_ms)
        yield 'data: ' + json.dumps({"type": "done", "session_id": session_id, "language": language,
            "stt_ms": stt_latency, "agent_ms": agent_latency, "tts_ms": total_tts_ms, "total_ms": total_ms}) + '\n\n'

    return StreamingResponse(stream_response(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.get("/doctors")
async def get_doctors():
    return json.loads(listDoctors())

@app.get("/appointments/{patient_name}")
async def get_appointments(patient_name: str):
    return json.loads(getPatientAppointments(patient_name))

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "2Care.ai Voice AI Agent", "version": "1.0.0"}

@app.get("/session/{session_id}")
async def get_session(session_id: str):
    return MemoryManager(session_id).get_summary()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)