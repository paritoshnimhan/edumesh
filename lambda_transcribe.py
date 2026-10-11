"""Private, synchronous Lambda handler for short audio recordings."""
import base64
import binascii
import os
from functools import lru_cache

import requests

MAX_AUDIO_BYTES = 4 * 1024 * 1024

@lru_cache(maxsize=1)
def provider_keys():
    groq_key = os.environ.get("GROQ_API_KEY")
    deepgram_key = os.environ.get("DEEPGRAM_API_KEY")
    parameter_names = [name for name in (
        os.environ.get("GROQ_API_KEY_PARAMETER"),
        os.environ.get("DEEPGRAM_API_KEY_PARAMETER"),
    ) if name]
    if parameter_names and (not groq_key or not deepgram_key):
        import boto3
        parameters = boto3.client(
            "ssm", region_name=os.environ.get("AWS_REGION", "ap-south-1")
        ).get_parameters(
            Names=parameter_names, WithDecryption=True
        )["Parameters"]
        values = {item["Name"]: item["Value"] for item in parameters}
        groq_key = groq_key or values.get(os.environ.get("GROQ_API_KEY_PARAMETER"))
        deepgram_key = deepgram_key or values.get(os.environ.get("DEEPGRAM_API_KEY_PARAMETER"))
    return groq_key, deepgram_key


def transcribe(audio, filename="audio.webm", content_type="audio/webm"):
    """Shared by the local subject service and Lambda; never persists audio."""
    groq_key, deepgram_key = provider_keys()
    if groq_key:
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {groq_key}"},
                files={"file": (filename, audio, content_type)},
                data={"model": "whisper-large-v3"}, timeout=(3, 15),
            )
            response.raise_for_status()
            return {"text": response.json()["text"], "stt_source": "groq_whisper"}
        except (requests.RequestException, ValueError, KeyError):
            print("Groq transcription failed; trying Deepgram")
    if deepgram_key:
        try:
            response = requests.post(
                "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true",
                headers={"Authorization": f"Token {deepgram_key}", "Content-Type": content_type},
                data=audio, timeout=(3, 15),
            )
            response.raise_for_status()
            text = response.json()["results"]["channels"][0]["alternatives"][0]["transcript"]
            return {"text": text, "stt_source": "deepgram"}
        except (requests.RequestException, ValueError, KeyError, IndexError):
            print("Deepgram transcription failed")
    return {"text": "", "stt_source": "error"}


def handler(event, context):
    encoded = event.get("audio_base64", "")
    if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_AUDIO_BYTES + 2) // 3):
        raise ValueError("Invalid or oversized audio")
    try:
        audio = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("Invalid base64 audio") from error
    if not audio or len(audio) > MAX_AUDIO_BYTES:
        raise ValueError("Audio must be between 1 byte and 4 MiB")
    return transcribe(audio)
