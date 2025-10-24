import os
import json
import base64
import asyncio
import requests
import websockets
from websockets.http import Headers
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import Response
from fastapi.websockets import WebSocketDisconnect
from dotenv import load_dotenv

# ------------------------------------------------------------
#  Load environment
# ------------------------------------------------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("Missing OpenAI API key. Please set it in .env")
    exit(1)

SYSTEM_MESSAGE = (
    "You are a cheerful and bubbly customer support agent who deals with "
    "customers efficiently and says haha now and then please."
)
VOICE = "alloy"
PORT = int(os.getenv("PORT", 5050))
WEBHOOK_URL = "https://0c4bed8a56d6.ngrok-free.app"

sessions = {}
LOG_EVENT_TYPES = [
    "response.content.done",
    "rate_limits.updated",
    "response.done",
    "input_audio_buffer.committed",
    "input_audio_buffer.speech_stopped",
    "input_audio_buffer.speech_started",
    "session.created",
    "response.text.done",
    "conversation.item.input_audio_transcription.completed",
]

app = FastAPI()

# ------------------------------------------------------------
#  Root route
# ------------------------------------------------------------
@app.get("/")
async def root():
    return {"message": "Twilio Media Stream Server is running!"}

# ------------------------------------------------------------
#  Twilio webhook
# ------------------------------------------------------------
@app.api_route("/incoming-call", methods=["GET", "POST"])
async def incoming_call(request: Request):
    print("Incoming call")
    host = request.headers.get("host", "localhost")
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Hi, you have called Bart's Automotive Centre. How can we help?</Say>
    <Connect>
        <Stream url="wss://{host}/media-stream" />
    </Connect>
</Response>"""
    return Response(content=twiml, media_type="text/xml")

# ------------------------------------------------------------
#  WebSocket: Twilio <-> OpenAI Realtime
# ------------------------------------------------------------
@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    print("Client connected")

    session_id = websocket.headers.get(
        "x-twilio-call-sid", f"session_{int(asyncio.get_event_loop().time()*1000)}"
    )
    session = sessions.get(session_id, {"transcript": "", "streamSid": None})
    sessions[session_id] = session

    openai_url = "wss://api.openai.com/v1/realtime?model=gpt-realtime"
    headers = Headers()
    headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"
    headers["OpenAI-Beta"] = "realtime=v1"

    try:
        async with websockets.connect(
            openai_url,
            additional_headers=headers
        ) as openai_ws:
            print("Connected to OpenAI Realtime API")

            async def send_session_update():
                try:
                    session_update = {
                        "type": "session.update",
                        "session": {
                            "turn_detection": {"type": "server_vad"},
                            "input_audio_format": "g711_ulaw",
                            "output_audio_format": "g711_ulaw",
                            "voice": VOICE,
                            "instructions": SYSTEM_MESSAGE,
                            "modalities": ["text", "audio"],
                            "temperature": 0.8,
                            "input_audio_transcription": {"model": "whisper-1"},
                        },
                    }

                    if not openai_ws.close_code:  # <-- use .open instead of .closed
                        await openai_ws.send(json.dumps(session_update))

                except websockets.exceptions.ConnectionClosedOK:
                    print("✅ OpenAI connection closed normally (1000). No action needed.")
                except websockets.exceptions.ConnectionClosedError as e:
                    print(f"⚠️ OpenAI connection closed unexpectedly: {e}")
                except Exception as e:
                    print(f"❌ Session update send error: {e}")


            # send configuration a moment after connect
            asyncio.create_task(send_session_update())

            async def receive_from_openai():
                try:
                    async for message in openai_ws:
                        response = json.loads(message)
                        if response.get("type") in LOG_EVENT_TYPES:
                            print(f"Event: {response['type']}", response)

                        if response.get("type") == "conversation.item.input_audio_transcription.completed":
                            user_msg = response.get("transcript", "").strip()
                            session["transcript"] += f"User: {user_msg}\n"
                            print(f"User({session_id}): {user_msg}")

                        if response.get("type") == "response.done":
                            out = response.get("response", {}).get("output", [])
                            agent_msg = "Agent message not found"
                            if out and isinstance(out, list):
                                for o in out[0].get("content", []):
                                    if "transcript" in o:
                                        agent_msg = o["transcript"]
                                        break
                            session["transcript"] += f"Agent: {agent_msg}\n"
                            print(f"Agent({session_id}): {agent_msg}")

                        if response.get("type") == "response.audio.delta" and "delta" in response:
                            audio_delta = {
                                "event": "media",
                                "streamSid": session["streamSid"],
                                "media": {
                                    "payload": base64.b64encode(
                                        base64.b64decode(response["delta"])
                                    ).decode("utf-8")
                                },
                            }
                            await websocket.send_json(audio_delta)
                except Exception as e:
                    print("Error reading OpenAI stream:", e)

            asyncio.create_task(receive_from_openai())

            # receive from Twilio and forward audio
            while True:
                try:
                    msg = await websocket.receive_text()
                    data = json.loads(msg)

                    if data["event"] == "media" and not openai_ws.close_code:
                        audio_append = {
                            "type": "input_audio_buffer.append",
                            "audio": data["media"]["payload"],
                        }
                        await openai_ws.send(json.dumps(audio_append))

                    elif data["event"] == "start":
                        session["streamSid"] = data["start"]["streamSid"]
                        print("Incoming stream started:", session["streamSid"])
                    else:
                        print("Non-media event:", data["event"])
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    print("Twilio receive error:", e)
                    break

    except Exception as e:
        print("OpenAI WS connection error:", e)

    print(f"Client disconnected ({session_id}).")
    print("Full Transcript:\n", session["transcript"])
    await process_transcript_and_send(session["transcript"], session_id)
    sessions.pop(session_id, None)

# ------------------------------------------------------------
#  Helper: ChatGPT completion + webhook
# ------------------------------------------------------------
def make_chatgpt_completion(transcript):
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-2024-08-06",
                "messages": [
                    {
                        "role": "system",
                        "content": "Extract customer details: name, availability, and special notes from the transcript.",
                    },
                    {"role": "user", "content": transcript},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "customer_details_extraction",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "customerName": {"type": "string"},
                                "customerAvailability": {"type": "string"},
                                "specialNotes": {"type": "string"},
                            },
                            "required": ["customerName", "customerAvailability", "specialNotes"],
                        },
                    },
                },
            },
        )
        print("ChatGPT response:", resp.status_code)
        return resp.json()
    except Exception as e:
        print("ChatGPT API error:", e)
        return None

def send_to_webhook(payload):
    try:
        # resp = requests.post(WEBHOOK_URL, json=payload)
        print("Webhook response:",{
            "payload": payload
        })
    except Exception as e:
        print("Webhook send error:", e)

async def process_transcript_and_send(transcript, session_id=None):
    result = make_chatgpt_completion(transcript)
    if not result:
        return
    try:
        msg = result["choices"][0]["message"]["content"]
        data = json.loads(msg)
        print("Extracted:", json.dumps(data, indent=2))
        send_to_webhook(data)
    except Exception as e:
        print("JSON parse/send error:", e)

# ------------------------------------------------------------
#  Run server
# ------------------------------------------------------------
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=PORT)
