#!/usr/bin/env python3
"""
Voice control for Unitree Go2 robot via Agent 2 Robot Protocol.

Push-to-talk: press Enter to start recording, Enter again to stop.
Audio is sent to a local whisper-server (Docker) for transcription,
then the recognized text is passed to the Cursor Agent CLI which
executes robot commands through the go2-control skill.

Requirements:
    pip install sounddevice numpy requests

Start whisper server first:
    docker compose -f docker/compose.yml up whisper -d
"""

import io
import os
import subprocess
import sys
import wave

import numpy as np
import requests
import sounddevice as sd

WHISPER_URL = os.environ.get("WHISPER_URL", "http://localhost:9000/v1/audio/transcriptions")
WHISPER_API_KEY = os.environ.get("WHISPER_API_KEY", "")
WORKSPACE = os.environ.get("GO2_WORKSPACE", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SAMPLE_RATE = 16000
CHANNELS = 1


def record_push_to_talk() -> np.ndarray:
    """Record audio until the user presses Enter again."""
    audio_chunks = []
    recording = True

    def callback(indata, frames, time_info, status):
        if recording:
            audio_chunks.append(indata.copy())

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        callback=callback,
    )

    print("\n    Recording... (press Enter to stop)")
    stream.start()
    input()
    recording = False
    stream.stop()
    stream.close()

    if not audio_chunks:
        return np.array([], dtype="int16")

    return np.concatenate(audio_chunks, axis=0)


def audio_to_wav_bytes(audio: np.ndarray) -> bytes:
    """Convert numpy audio array to WAV file bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


def transcribe(wav_bytes: bytes) -> str:
    """Send WAV audio to whisper-server and return transcribed text."""
    files = {"file": ("recording.wav", wav_bytes, "audio/wav")}
    data = {"model": "whisper-1"}
    headers = {}
    if WHISPER_API_KEY:
        headers["Authorization"] = f"Bearer {WHISPER_API_KEY}"

    resp = requests.post(WHISPER_URL, files=files, data=data, headers=headers, timeout=30)
    resp.raise_for_status()

    result = resp.json()
    return result.get("text", "").strip()


def send_to_agent(text: str) -> None:
    """Send recognized text to Cursor Agent CLI in print mode."""
    prompt = f"[sim mode] {text}"
    cmd = ["agent", "-p", "--trust", "--yolo", "--workspace", WORKSPACE, prompt]

    print(f"    Sending to agent: \"{text}\"")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.stdout:
            print(f"    Agent: {result.stdout.strip()}")
        if result.returncode != 0 and result.stderr:
            print(f"    Agent error: {result.stderr.strip()}")
    except subprocess.TimeoutExpired:
        print("    Agent timed out (120s)")
    except FileNotFoundError:
        print("    Error: 'agent' CLI not found. Install Cursor CLI: https://cursor.com/docs/cli")
        print(f"    Falling back to direct CLI execution...")
        fallback_direct(text)


def fallback_direct(text: str) -> None:
    """If Cursor Agent CLI is not available, try to parse simple commands directly."""
    print(f"    (Direct mode not implemented — install Cursor CLI for full support)")


def check_whisper_server() -> bool:
    """Check if whisper-server is reachable."""
    try:
        resp = requests.get(WHISPER_URL.replace("/v1/audio/transcriptions", "/"), timeout=5)
        return True
    except (requests.ConnectionError, requests.Timeout):
        return False


def main():
    print("=" * 60)
    print("  Agent 2 Robot Protocol — Voice Control")
    print("=" * 60)
    print()
    print(f"  Whisper server: {WHISPER_URL}")
    print(f"  Workspace: {WORKSPACE}")
    print()

    # Check whisper server
    print("  Checking whisper-server... ", end="", flush=True)
    if not check_whisper_server():
        print("NOT AVAILABLE")
        print()
        print("  Start it with:")
        print("    docker compose -f docker/compose.yml up whisper -d")
        print()
        print("  Waiting for whisper-server...")
        while not check_whisper_server():
            import time
            time.sleep(2)
    print("OK")
    print()
    print("  Ready! Press Enter to start recording, Enter to stop.")
    print("  Ctrl+C to exit.")
    print("-" * 60)

    try:
        while True:
            input("\n  >> Press Enter to speak...")

            audio = record_push_to_talk()

            if len(audio) < SAMPLE_RATE * 0.3:  # less than 0.3s
                print("    Too short, skipped.")
                continue

            wav_bytes = audio_to_wav_bytes(audio)
            duration = len(audio) / SAMPLE_RATE
            print(f"    Recorded {duration:.1f}s of audio")

            print("    Transcribing...", end=" ", flush=True)
            try:
                text = transcribe(wav_bytes)
            except requests.RequestException as e:
                print(f"FAILED: {e}")
                continue

            if not text:
                print("(empty result)")
                continue

            print(f"\"{text}\"")
            send_to_agent(text)

    except KeyboardInterrupt:
        print("\n\n  Exiting voice control. Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
