import os
import re
import hashlib
import requests
import json
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from lexicons import LEXICONS
from lambda_transcribe import provider_keys

# Load environment variables
load_dotenv()

# Subject selection at import time
SUBJECT = os.environ.get("SUBJECT")
if not SUBJECT or SUBJECT not in LEXICONS:
    raise ValueError(f"SUBJECT environment variable must be set to one of {list(LEXICONS.keys())}")

lexicon = LEXICONS[SUBJECT]

app = FastAPI(title=f"EduMesh {SUBJECT} Service")

# Module-level cache keyed by sha256 of normalized question
# Maps hash_key -> {"answer": str, "answer_source": str}
cache = {}

def normalize(text: str) -> str:
    """Normalize text: lowercase, alphanumeric characters only, collapsed whitespace, stripped."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9 ]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def match_term(normalized_question: str, term: str) -> bool:
    """Check if a single term matches the normalized question using regex rule."""
    normalized_term = normalize(term)
    words = normalized_term.split()
    if not words:
        return False
    escaped_words = [re.escape(w) for w in words]
    pattern_str = r'\b' + r'\s+'.join(escaped_words) + r's?\b'
    pattern = re.compile(pattern_str)
    return bool(pattern.search(normalized_question))

def find_match_spans(normalized_question: str, term: str):
    """Find all match spans of a term in the normalized question."""
    normalized_term = normalize(term)
    words = normalized_term.split()
    if not words:
        return []
    escaped_words = [re.escape(w) for w in words]
    pattern_str = r'\b' + r'\s+'.join(escaped_words) + r's?\b'
    pattern = re.compile(pattern_str)
    return [match.span() for match in pattern.finditer(normalized_question)]

class CanHandleRequest(BaseModel):
    query_id: str
    question: str

class AnswerRequest(BaseModel):
    query_id: str
    question: str
    matched_topic: str

@app.get("/health")
def health():
    terms_loaded = len(lexicon["tier1"]) + len(lexicon["tier2"]) + len(lexicon["tier3"])
    return {
        "service": SUBJECT,
        "status": "up",
        "terms_loaded": terms_loaded
    }

@app.post("/can_handle")
def can_handle(payload: CanHandleRequest):
    print(f"[{SUBJECT} Service] [query_id={payload.query_id}] Received POST /can_handle for: '{payload.question}'")
    normalized_question = normalize(payload.question)
    
    # Build a flat list of (term, tier)
    term_tier_list = []
    for t in lexicon["tier1"]:
        term_tier_list.append((t, "tier1"))
    for t in lexicon["tier2"]:
        term_tier_list.append((t, "tier2"))
    for t in lexicon["tier3"]:
        term_tier_list.append((t, "tier3"))
        
    # Normalize all terms first so that word-count/char-length sorting is based on matching form
    normalized_term_tier_list = []
    for term, tier in term_tier_list:
        norm_term = normalize(term)
        if norm_term:
            normalized_term_tier_list.append((norm_term, tier, term))
            
    # Sort by word-count descending, then character-length descending
    normalized_term_tier_list.sort(key=lambda x: (len(x[0].split()), len(x[0])), reverse=True)
    
    consumed_spans = []
    matched_by_tier = {"tier1": [], "tier2": [], "tier3": []}
    
    for norm_term, tier, original_term in normalized_term_tier_list:
        # Prevent matching duplicate terms
        if (original_term in matched_by_tier["tier1"] or 
            original_term in matched_by_tier["tier2"] or 
            original_term in matched_by_tier["tier3"]):
            continue
            
        spans = find_match_spans(normalized_question, norm_term)
        for span in spans:
            # Check overlap
            overlaps = False
            for c_start, c_end in consumed_spans:
                if max(span[0], c_start) < min(span[1], c_end):
                    overlaps = True
                    break
            if not overlaps:
                consumed_spans.append(span)
                matched_by_tier[tier].append(original_term)
                break
                
    n1 = len(matched_by_tier["tier1"])
    n2 = len(matched_by_tier["tier2"])
    n3 = len(matched_by_tier["tier3"])
    
    # Blocker penalty
    penalty = 0
    for blocker_key, blocker_words in lexicon["blockers"].items():
        if match_term(normalized_question, blocker_key):
            for blocker_word in blocker_words:
                if match_term(normalized_question, blocker_word):
                    penalty += 45
                    break
                    
    raw = 60 * n1 + min(25 * n2, 50) + min(8 * n3, 24) - penalty
    score = max(0, min(100, raw))
    
    response_data = {
        "service": SUBJECT,
        "display_name": lexicon["display_name"],
        "score": score,
        "matched": {
            "tier1": matched_by_tier["tier1"],
            "tier2": matched_by_tier["tier2"],
            "tier3": matched_by_tier["tier3"]
        },
        "scoring_version": "1.0"
    }
    print(f"[{SUBJECT} Service] [query_id={payload.query_id}] Responding to /can_handle: score={score}, matched_t1={matched_by_tier['tier1']}")
    return response_data

@app.post("/answer")
def answer(payload: AnswerRequest):
    print(f"[{SUBJECT} Service] [query_id={payload.query_id}] Received POST /answer for: '{payload.question}' (Topic: {payload.matched_topic})")
    normalized_question = normalize(payload.question)
    hash_key = hashlib.sha256(normalized_question.encode('utf-8')).hexdigest()
    
    if hash_key in cache:
        cached_data = cache[hash_key]
        print(f"[{SUBJECT} Service] [query_id={payload.query_id}] Cache hit for answer!")
        return {
            "service": SUBJECT,
            "display_name": lexicon["display_name"],
            "answer": cached_data["answer"],
            "answer_source": cached_data["answer_source"],
            "cached": True
        }
        
    answer_mode = os.environ.get("ANSWER_MODE", "groq")
    display_name = lexicon["display_name"]
    matched_topic = payload.matched_topic
    question = payload.question
    
    if answer_mode == "groq":
        groq_api_key, _ = provider_keys()
        model_name = os.environ.get("MODEL_NAME", "openai/gpt-oss-20b")
        
        if not groq_api_key:
            # Missing key, fallback to error source
            fallback_answer = f"[{display_name}] I identified this as a {matched_topic} question, but the answer service is currently unavailable."
            cache[hash_key] = {"answer": fallback_answer, "answer_source": "error"}
            print(f"[{SUBJECT} Service] [query_id={payload.query_id}] Missing GROQ_API_KEY. Using error fallback.")
            return {
                "service": SUBJECT,
                "display_name": display_name,
                "answer": fallback_answer,
                "answer_source": "error",
                "cached": False
            }
            
        try:
            headers = {
                "Authorization": f"Bearer {groq_api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": lexicon["system_prompt"]},
                    {"role": "user", "content": f"Topic detected: {matched_topic}\n\nQuestion: {question}"}
                ],
                "temperature": 0.3,
                "max_tokens": 800
            }
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            )
            response.raise_for_status()
            res_json = response.json()
            reply = res_json["choices"][0]["message"]["content"]
            
            cache[hash_key] = {"answer": reply, "answer_source": "groq"}
            print(f"[{SUBJECT} Service] [query_id={payload.query_id}] Responding with Groq answer.")
            return {
                "service": SUBJECT,
                "display_name": display_name,
                "answer": reply,
                "answer_source": "groq",
                "cached": False
            }
        except Exception as e:
            print(f"[{SUBJECT} Service] [query_id={payload.query_id}] Groq API Call failed: {e}. Falling back to error.")
            fallback_answer = f"[{display_name}] I identified this as a {matched_topic} question, but the answer service is currently unavailable."
            cache[hash_key] = {"answer": fallback_answer, "answer_source": "error"}
            return {
                "service": SUBJECT,
                "display_name": display_name,
                "answer": fallback_answer,
                "answer_source": "error",
                "cached": False
            }
    else:
        # Template mode
        fallback_answer = f"[{display_name}] I identified this as a {matched_topic} question, but the answer service is currently unavailable."
        cache[hash_key] = {"answer": fallback_answer, "answer_source": "template"}
        print(f"[{SUBJECT} Service] [query_id={payload.query_id}] Responding with Template fallback.")
        return {
            "service": SUBJECT,
            "display_name": display_name,
            "answer": fallback_answer,
            "answer_source": "template",
            "cached": False
        }

@app.post("/transcribe_audio")
def transcribe_audio(file: UploadFile = File(...)):
    from fastapi import HTTPException
    from lambda_transcribe import MAX_AUDIO_BYTES, transcribe
    audio = file.file.read(MAX_AUDIO_BYTES + 1)
    if not audio or len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="Audio must be between 1 byte and 4 MiB")
    return transcribe(audio, file.filename or "audio.webm", file.content_type or "audio/webm")

@app.post("/answer_stream")
def answer_stream(payload: AnswerRequest):
    print(f"[{SUBJECT} Service] [query_id={payload.query_id}] Received POST /answer_stream for: '{payload.question}'")
    display_name = lexicon["display_name"]
    matched_topic = payload.matched_topic
    question = payload.question
    answer_mode = os.environ.get("ANSWER_MODE", "groq")
    
    if answer_mode != "groq":
        fallback_answer = f"[{display_name}] I identified this as a {matched_topic} question, but the answer service is currently unavailable."
        def single_chunk():
            yield fallback_answer
        return StreamingResponse(single_chunk(), media_type="text/plain")

    groq_api_key, _ = provider_keys()
    model_name = os.environ.get("MODEL_NAME", "openai/gpt-oss-20b")
    
    def generate_tokens():
        if not groq_api_key:
            yield f"[{display_name}] I identified this as a {matched_topic} question, but the answer service is currently unavailable."
            return
            
        try:
            headers = {
                "Authorization": f"Bearer {groq_api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": lexicon["system_prompt"]},
                    {"role": "user", "content": f"Topic detected: {matched_topic}\n\nQuestion: {question}"}
                ],
                "temperature": 0.3,
                "max_tokens": 800,
                "stream": True
            }
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=data,
                stream=True,
                timeout=30
            )
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith("data: ") and line_str != "data: [DONE]":
                        try:
                            chunk_json = json.loads(line_str[6:])
                            token = chunk_json["choices"][0]["delta"].get("content", "")
                            if token:
                                yield token
                        except Exception:
                            pass
        except Exception as e:
            print(f"[{SUBJECT} Service] Groq Streaming failed: {e}")
            yield f"[{display_name}] I identified this as a {matched_topic} question, but the answer service is currently unavailable."

    return StreamingResponse(generate_tokens(), media_type="text/plain")
