"""IAM-authenticated Lambda invocation; no AWS client is created in local mode."""
import base64
import json
import os
from functools import lru_cache


@lru_cache(maxsize=1)
def lambda_client():
    import boto3
    from botocore.config import Config
    return boto3.client("lambda", region_name=os.environ.get("AWS_REGION", "ap-south-1"),
                        config=Config(connect_timeout=3, read_timeout=65,
                                      retries={"mode": "standard", "total_max_attempts": 1}))


def invoke_transcription(audio):
    response = lambda_client().invoke(
        FunctionName=os.environ["TRANSCRIBE_LAMBDA_FUNCTION"],
        InvocationType="RequestResponse",
        Payload=json.dumps({"audio_base64": base64.b64encode(audio).decode("ascii")}).encode(),
    )
    with response["Payload"] as stream:
        result = json.loads(stream.read())
    if response.get("FunctionError"):
        raise RuntimeError("Lambda transcription failed")
    if not isinstance(result, dict) or not isinstance(result.get("text"), str):
        raise ValueError("Invalid transcription response")
    return {"text": result["text"], "stt_source": result.get("stt_source", "error")}
