import base64
import os
import unittest
from unittest.mock import Mock, patch

import requests
from lambda_transcribe import handler, transcribe, MAX_AUDIO_BYTES


class TranscriptionTests(unittest.TestCase):
    def test_invalid_uploads_never_call_provider(self):
        with patch("lambda_transcribe.transcribe") as provider:
            for value in ("", "!bad!", "a" * (MAX_AUDIO_BYTES * 2)):
                with self.assertRaises(ValueError):
                    handler({"audio_base64": value}, None)
            provider.assert_not_called()

    def test_decodes_audio(self):
        with patch("lambda_transcribe.transcribe", return_value={"text": "hello"}) as provider:
            self.assertEqual(handler({"audio_base64": base64.b64encode(b"audio").decode()}, None),
                             {"text": "hello"})
            provider.assert_called_once_with(b"audio")

    def test_provider_fallback(self):
        import lambda_transcribe
        lambda_transcribe.provider_keys.cache_clear()
        response = Mock()
        response.json.return_value = {"results": {"channels": [{"alternatives": [{"transcript": "hello"}]}]}}
        with patch.dict(os.environ, {"GROQ_API_KEY": "test", "DEEPGRAM_API_KEY": "test"}), \
             patch("lambda_transcribe.requests.post", side_effect=[requests.Timeout(), response]) as post:
            self.assertEqual(transcribe(b"audio"), {"text": "hello", "stt_source": "deepgram"})
            self.assertEqual(post.call_count, 2)

    def test_no_keys(self):
        import lambda_transcribe
        lambda_transcribe.provider_keys.cache_clear()
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(transcribe(b"audio"), {"text": "", "stt_source": "error"})

    def test_keys_are_loaded_from_parameter_store(self):
        import lambda_transcribe
        lambda_transcribe.provider_keys.cache_clear()
        client = Mock()
        client.get_parameters.return_value = {"Parameters": [
            {"Name": "/edumesh/groq", "Value": "groq"},
            {"Name": "/edumesh/deepgram", "Value": "deepgram"},
        ]}
        with patch.dict(os.environ, {"GROQ_API_KEY_PARAMETER": "/edumesh/groq", "DEEPGRAM_API_KEY_PARAMETER": "/edumesh/deepgram"}, clear=True), \
             patch("boto3.client", return_value=client) as boto_client:
            self.assertEqual(lambda_transcribe.provider_keys(), ("groq", "deepgram"))
            boto_client.assert_called_once_with("ssm", region_name="ap-south-1")


if __name__ == "__main__":
    unittest.main()
