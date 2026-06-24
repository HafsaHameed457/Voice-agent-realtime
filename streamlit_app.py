from __future__ import annotations

import base64
import json
import threading
import time
from queue import Empty, Queue
from typing import Any

import streamlit as st
from websockets.sync.client import connect

from src.utils.audio import mulaw_to_wav

st.set_page_config(page_title="Voice Agent", page_icon="🎙️", layout="centered")
st.title("Voice Agent — Browser Test Client")


def _ws_worker(
    uri: str,
    session_id: str,
    send_queue: Queue,
    recv_queue: Queue,
) -> None:
    url = f"{uri}/browser-stream?session_id={session_id}"
    try:
        with connect(url) as ws:
            recv_queue.put({"type": "$connected"})
            recv_queue.put({"type": "$session_id", "session_id": session_id})

            stop = False
            while not stop:
                try:
                    msg = send_queue.get_nowait()
                    if msg.get("type") == "$disconnect":
                        stop = True
                        break
                    ws.send(json.dumps(msg))
                except Empty:
                    pass

                try:
                    raw = ws.recv(timeout=0.1)
                    data = json.loads(raw)
                    recv_queue.put(data)
                except TimeoutError:
                    pass

    except Exception as exc:
        recv_queue.put({"type": "$error", "message": str(exc)})
    finally:
        recv_queue.put({"type": "$disconnected"})


def _init_state() -> None:
    if "session_id" not in st.session_state:
        st.session_state.session_id = f"streamlit_{int(time.time() * 1000)}"
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "connected" not in st.session_state:
        st.session_state.connected = False
    if "send_queue" not in st.session_state:
        st.session_state.send_queue = Queue()
    if "recv_queue" not in st.session_state:
        st.session_state.recv_queue = Queue()
    if "ws_thread" not in st.session_state:
        st.session_state.ws_thread = None
    if "audio_buffer" not in st.session_state:
        st.session_state.audio_buffer = bytearray()
    if "pending_audio" not in st.session_state:
        st.session_state.pending_audio = None


def _handle_event(event: dict[str, Any]) -> None:
    t = event.get("type", "")

    if t == "$connected":
        st.session_state.connected = True
    elif t == "$disconnected":
        st.session_state.connected = False
        st.session_state.ws_thread = None
    elif t == "$error":
        st.error(f"Connection error: {event['message']}")
        st.session_state.connected = False
    elif t == "$session_id":
        st.session_state.session_id = event["session_id"]
    elif t == "session.ready":
        st.info("Session ready on server")
    elif t == "transcript":
        role = event.get("role", "assistant")
        text = event.get("text", "")
        st.session_state.messages.append({"role": role, "text": text})
        if role == "assistant" and st.session_state.audio_buffer:
            wav_bytes = mulaw_to_wav(bytes(st.session_state.audio_buffer))
            st.session_state.pending_audio = wav_bytes
            st.session_state.audio_buffer = bytearray()
    elif t == "audio.delta":
        audio_b64 = event.get("audio", "")
        if audio_b64:
            mulaw_bytes = base64.b64decode(audio_b64)
            st.session_state.audio_buffer.extend(mulaw_bytes)
    elif t == "error":
        st.error(f"Server error: {event.get('message', '')}")


def _drain_queue() -> None:
    q: Queue = st.session_state.recv_queue
    while True:
        try:
            event = q.get_nowait()
        except Empty:
            break
        _handle_event(event)


_init_state()
_drain_queue()


with st.sidebar:
    st.header("Connection")
    server_host = st.text_input("Server host", value="localhost")
    server_port = st.text_input("Server port", value="5050")
    ws_uri = f"ws://{server_host}:{server_port}"

    col1, col2 = st.columns(2)
    with col1:
        can_connect = not st.session_state.connected
        if can_connect and st.button("Connect", use_container_width=True):
            st.session_state.send_queue = Queue()
            st.session_state.recv_queue = Queue()
            thread = threading.Thread(
                target=_ws_worker,
                args=(
                    ws_uri,
                    st.session_state.session_id,
                    st.session_state.send_queue,
                    st.session_state.recv_queue,
                ),
                daemon=True,
            )
            thread.start()
            st.session_state.ws_thread = thread
            st.rerun()
    with col2:
        if st.session_state.connected and st.button("Disconnect", use_container_width=True):
            st.session_state.send_queue.put({"type": "$disconnect"})
            st.rerun()

    status = "🟢 Connected" if st.session_state.connected else "🔴 Disconnected"
    st.caption(f"Status: {status}")
    st.caption(f"Session: `{st.session_state.session_id}`")

    if st.button("New Session", use_container_width=True):
        st.session_state.session_id = f"streamlit_{int(time.time() * 1000)}"
        st.session_state.messages = []
        st.session_state.connected = False
        st.session_state.ws_thread = None
        st.session_state.audio_buffer = bytearray()
        st.session_state.pending_audio = None
        st.rerun()

    if st.button("Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()


st.divider()


for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["text"])


if st.session_state.pending_audio:
    st.audio(st.session_state.pending_audio, format="audio/wav")
    st.session_state.pending_audio = None


if prompt := st.chat_input(
    "Type a message...",
    disabled=not st.session_state.connected,
):
    st.session_state.messages.append({"role": "user", "text": prompt})
    st.session_state.send_queue.put({"type": "text", "text": prompt})
    st.rerun()


st.divider()
st.subheader("🎤 Audio Input")

audio_bytes = st.audio_input(
    "Record a message",
    key="audio_recorder",
    disabled=not st.session_state.connected,
)

if audio_bytes is not None:
    try:
        from src.utils.audio import encode_base64, webm_to_pcm16

        with st.spinner("Processing audio..."):
            pcm16 = webm_to_pcm16(audio_bytes, target_sample_rate=24000)
            audio_b64 = encode_base64(pcm16)

        st.session_state.send_queue.put({"type": "audio", "audio": audio_b64})
        st.success("Audio sent! Waiting for response...")
        st.rerun()
    except Exception as e:
        st.error(f"Audio processing failed: {e}")
