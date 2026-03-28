"""
Intellifox AI — Organizational Memory Engine
Two products: KT Training + Knowledge Base
Multi-agent | Gemini Multimodal | Cloud Run + Vertex AI ready

GCP Vertex AI deployment (NO API KEY needed):
  - Set GOOGLE_GENAI_USE_VERTEXAI=true
  - Set GOOGLE_CLOUD_PROJECT=your-project-id
  - Set GOOGLE_CLOUD_LOCATION=us-central1
  - Cloud Run Service Account needs roles/aiplatform.user

Local dev: copy .env.example → .env
  gcloud auth application-default login
  python main.py
"""

import os, json, base64, io, wave, logging, asyncio, hashlib, time, re
from typing import Optional, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

# Project root — load .env before reading os.environ
_ROOT = os.path.dirname(os.path.abspath(__file__))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ROOT, ".env"))
except ImportError:
    pass

# ── LOGGING ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

RUN_ENV = os.environ.get("RUN_ENV", "local").strip().lower()


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


# ── BACKEND CONFIG ─────────────────────────────────────────────────────────────
GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY", "").strip()
USE_VERTEX_AI   = _env_truthy("GOOGLE_GENAI_USE_VERTEXAI") or _env_truthy("VERTEXAI")
GCP_PROJECT     = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
GCP_LOCATION    = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1").strip()

# ── VERTEX AI MODEL IDs (stable, available on Vertex) ─────────────────────────
# Text: gemini-2.0-flash-001  (fast, cheap, great quality)
# Image: imagen-3.0-generate-002  (Vertex native image generation)
# TTS: We use Gemini text + gTTS-style fallback; Vertex TTS via gemini-2.0-flash-001
#
# If running on Developer API (AI Studio), gemini-2.5-flash works for text.
# For Vertex: use the -001 suffixed stable aliases.

TEXT_MODEL  = os.environ.get("GEMINI_TEXT_MODEL",  "gemini-2.0-flash-001")
# Imagen 3 on Vertex for image generation (best quality, no text-in-image issues)
IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "imagen-3.0-generate-002")
# TTS: gemini-2.0-flash-001 with AUDIO modality works on Vertex
TTS_MODEL   = os.environ.get("GEMINI_TTS_MODEL",   "gemini-2.0-flash-001")


def _create_genai_client() -> Optional[genai.Client]:
    """
    Vertex AI (GCP) — no API key needed. Uses Application Default Credentials.
    On Cloud Run: Service Account with roles/aiplatform.user is used automatically.
    Locally: run  gcloud auth application-default login
    """
    if USE_VERTEX_AI or GCP_PROJECT:
        project = GCP_PROJECT
        if not project:
            logger.error(
                "GOOGLE_GENAI_USE_VERTEXAI=true but GOOGLE_CLOUD_PROJECT is not set. "
                "Set GOOGLE_CLOUD_PROJECT=your-project-id"
            )
            return None
        logger.info(
            "✅ Gemini via Vertex AI — project=%s  location=%s  text=%s  image=%s  tts=%s",
            project, GCP_LOCATION, TEXT_MODEL, IMAGE_MODEL, TTS_MODEL,
        )
        return genai.Client(vertexai=True, project=project, location=GCP_LOCATION)

    # Fallback: Developer API key (AI Studio) for local testing only
    if GEMINI_API_KEY:
        logger.info("Gemini via Developer API key (AI Studio)")
        return genai.Client(api_key=GEMINI_API_KEY)

    logger.warning(
        "⚠️  No Gemini client configured! "
        "Set GOOGLE_GENAI_USE_VERTEXAI=true + GOOGLE_CLOUD_PROJECT  OR  GEMINI_API_KEY"
    )
    return None


client = _create_genai_client()


def _gemini_backend_name() -> str:
    if client is None:
        return "none"
    return "vertex" if (USE_VERTEX_AI or GCP_PROJECT) else "ai_studio"


# ── RETRY LOGIC (handles 429 quota, transient errors) ─────────────────────────
def _retry_delay_from_error(e: Exception) -> Optional[float]:
    msg = str(e)
    if "NOT_FOUND" in msg and ("404" in msg or "not found" in msg.lower()):
        return None
    if "INVALID_ARGUMENT" in msg:
        return None
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        m = re.search(r"retry in ([\d.]+)s", msg, re.I)
        if m:
            return min(float(m.group(1)) + 2.0, 60.0)
        return 30.0
    if "503" in msg or "UNAVAILABLE" in msg:
        return 10.0
    return None


def generate_content_retrying(
    model: str,
    contents: Any,
    config: Optional[types.GenerateContentConfig] = None,
    *,
    max_attempts: int = 4,
) -> Any:
    """Wrapper with retry + backoff for Vertex AI quota limits."""
    if client is None:
        raise RuntimeError(
            "No Gemini client. Set GOOGLE_GENAI_USE_VERTEXAI=true and GOOGLE_CLOUD_PROJECT."
        )
    last: Optional[Exception] = None
    for attempt in range(max_attempts):
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except Exception as e:
            last = e
            wait = _retry_delay_from_error(e)
            if wait is None:
                raise
            logger.warning(
                "Gemini model=%s attempt %s/%s: %s — retrying in %.0fs",
                model, attempt + 1, max_attempts, type(e).__name__, wait,
            )
            time.sleep(wait)
    assert last is not None
    raise last


# ── IMAGEN 3 IMAGE GENERATION (Vertex native) ─────────────────────────────────
def generate_imagen(prompt: str) -> Optional[str]:
    """
    Vertex AI Imagen 3 → base64 PNG.
    Falls back to None gracefully if unavailable.
    """
    if client is None:
        return None
    try:
        response = client.models.generate_images(
            model=IMAGE_MODEL,
            prompt=prompt[:2000],
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="16:9",
                safety_filter_level="block_only_high",
            ),
        )
        if response.generated_images:
            img = response.generated_images[0]
            if hasattr(img, "image") and hasattr(img.image, "image_bytes"):
                return base64.b64encode(img.image.image_bytes).decode()
    except Exception as e:
        logger.warning(f"[Imagen3] failed ({type(e).__name__}): {e} — skipping image")
    return None


# ── TTS via Gemini (Vertex) ────────────────────────────────────────────────────
def pcm_to_wav(pcm_data: bytes, sample_rate: int = 24000) -> bytes:
    """Convert raw PCM L16 from Gemini TTS → valid WAV for browser."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return buf.getvalue()


def sync_tts_to_wav(script: str, voice_name: str = "Puck") -> Optional[str]:
    """Gemini TTS on Vertex → base64 WAV. Graceful fallback to None."""
    if not script or not str(script).strip() or client is None:
        return None
    text = str(script).strip()[:4000]
    try:
        audio_r = generate_content_retrying(
            TTS_MODEL,
            text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_name
                        )
                    )
                ),
            ),
        )
        parts = audio_r.candidates[0].content.parts
        for part in parts:
            if getattr(part, "inline_data", None) and part.inline_data.data:
                pcm = part.inline_data.data
                return base64.b64encode(pcm_to_wav(pcm)).decode()
    except Exception as e:
        logger.warning(f"[TTS] failed ({type(e).__name__}): {e} — skipping audio")
    return None


def sync_gen_image_b64(prompt: str) -> Optional[str]:
    """Image generation — uses Imagen 3 on Vertex."""
    if not prompt or not str(prompt).strip():
        return None
    return generate_imagen(str(prompt).strip())


def extract_json(text: str) -> dict:
    """Safely parse JSON from Gemini response, stripping markdown fences."""
    text = text.strip()
    # Remove markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        # Try to find JSON object in the text
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    return {}


# ── APP ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="Intellifox AI", version="2.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── BANKING KNOWLEDGE BASE ─────────────────────────────────────────────────────
_KB_PATH = os.environ.get(
    "BANKING_KNOWLEDGE_JSON", os.path.join(_ROOT, "banking_knowledge.json")
)


def _load_banking_data() -> dict:
    with open(_KB_PATH, encoding="utf-8") as f:
        return json.load(f)


try:
    BANKING_DATA = _load_banking_data()
    logger.info("✅ Banking knowledge loaded from %s", _KB_PATH)
except FileNotFoundError:
    logger.error("❌ Missing %s", _KB_PATH)
    BANKING_DATA = {
        "meta": {}, "systems": [], "teams": [],
        "processes": {}, "multimodal_training": {},
    }


def _seed_u32(s: str) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest()[:8], 16)


def multimodal_training_excerpt(*, role: str = "", topic: str = "", max_chars: int = 8000) -> str:
    """Bounded slice of multimodal_training for LLM prompts."""
    mm = BANKING_DATA.get("multimodal_training") or {}
    if not mm:
        return ""
    pack: dict = {
        "generation_style_guide": mm.get("generation_style_guide"),
        "glossary_sample": (mm.get("glossary") or [])[:12],
    }
    rm = mm.get("role_media_matrix") or {}
    rk = next(
        (k for k in rm if role and (role.lower() in k.lower() or k.lower() in role.lower())),
        None,
    )
    if rk:
        pack["role_media_matrix"] = {rk: rm[rk]}
    elif rm:
        first = list(rm.keys())[0]
        pack["role_media_matrix"] = {first: rm[first]}

    vc = mm.get("video_curriculum") or []
    if vc:
        pack["video_episode_sample"] = vc[_seed_u32(topic or role or "default") % len(vc)]

    img = mm.get("image_prompt_library") or []
    if img:
        h = _seed_u32((topic or role) + "|img")
        pack["image_prompt_samples"] = [img[(h + j * 11) % len(img)] for j in range(6)]

    aud = mm.get("audio_narration_library") or []
    if aud:
        h = _seed_u32((topic or role) + "|aud")
        pack["audio_narration_samples"] = [aud[(h + j * 7) % len(aud)] for j in range(4)]

    txt = mm.get("text_curriculum_modules") or []
    if txt:
        h = _seed_u32((topic or role) + "|txt")
        pack["text_curriculum_samples"] = [txt[(h + j * 3) % len(txt)] for j in range(3)]

    out = json.dumps(pack, indent=2, ensure_ascii=False)
    if len(out) > max_chars:
        return out[:max_chars - 50] + "\n/* …truncated… */"
    return out


def get_system(name: str) -> Optional[dict]:
    name_lower = name.lower()
    for s in BANKING_DATA.get("systems", []):
        if name_lower in s["name"].lower() or name_lower in s["id"].lower():
            return s
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT 1 — CONTEXT AGENT
# ═══════════════════════════════════════════════════════════════════════════════
def context_agent(query: str) -> dict:
    q = query.lower()
    matched_systems = []
    for s in BANKING_DATA.get("systems", []):
        score = 0
        if q in s.get("name", "").lower():            score += 10
        if q in s.get("id", "").lower():              score += 10
        if q in s.get("description", "").lower():     score += 5
        for d in s.get("dependencies", []):
            if q in d.lower():                        score += 3
        for t in s.get("tech_stack", []):
            if q in t.lower():                        score += 2
        if score > 0:
            matched_systems.append((score, s))

    matched_systems.sort(key=lambda x: -x[0])
    result_systems = [s for _, s in matched_systems[:6]] or BANKING_DATA.get("systems", [])

    matched_teams = [
        t for t in BANKING_DATA.get("teams", [])
        if q in t.get("name", "").lower()
        or any(q in s.lower() for s in t.get("owned_systems", []))
    ]

    return {
        "systems": result_systems,
        "teams": matched_teams or BANKING_DATA.get("teams", []),
        "processes": BANKING_DATA.get("processes", {}),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT 2 — KNOWLEDGE GRAPH AGENT
# ═══════════════════════════════════════════════════════════════════════════════
def knowledge_graph_agent() -> dict:
    risk_color = {
        "critical": "#ef4444", "high": "#f97316",
        "medium": "#eab308", "low": "#22c55e",
    }
    nodes, edges = [], []
    for s in BANKING_DATA.get("systems", []):
        nodes.append({
            "id": s["id"], "label": s["name"],
            "team": s.get("owning_team", ""),
            "risk": s.get("risk_level", "low"),
            "color": risk_color.get(s.get("risk_level", "low"), "#6366f1"),
            "tech": s.get("tech_stack", [])[:2],
        })
        for dep in s.get("dependencies", []):
            if any(sys["id"] == dep for sys in BANKING_DATA.get("systems", [])):
                edges.append({"source": s["id"], "target": dep, "risk": s.get("risk_level", "low")})
    return {"nodes": nodes, "edges": edges, "system_count": len(nodes)}


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT 3 — STORYTELLING AGENT (text + Imagen3 image + TTS audio)
# ═══════════════════════════════════════════════════════════════════════════════
async def storytelling_agent(topic: str) -> dict:
    context = context_agent(topic)
    primary = get_system(topic) or (context["systems"][0] if context["systems"] else {})
    ctx_json = json.dumps(
        {"primary_system": primary, "related": context["systems"][:3]}, indent=2
    )
    mm_excerpt = multimodal_training_excerpt(topic=topic, max_chars=6000)

    story_prompt = f"""You are Intellifox — a Creative Director AI for a major bank's engineering org.

Topic: "{topic}"
Knowledge base:
{ctx_json}

Multimodal style guide:
{mm_excerpt}

Return ONLY valid JSON (no markdown fences, no extra text) with this exact structure:
{{
  "headline": "One punchy headline (max 10 words)",
  "story": "3 immersive paragraphs about this system — who built it, what problem it solves, how it fits in the bank.",
  "visual_description": "Describe a technical architecture diagram for '{topic}' — boxes, arrows, colors, layout.",
  "audio_script": "A 40-second professional voiceover script. Warm, clear, authoritative.",
  "insights": ["Insight 1 about role/impact", "Insight 2 about dependencies", "Insight 3 about risk"],
  "risk_analysis": "What happens if this system goes down? Who is affected?",
  "followups": ["Follow-up question 1?", "Follow-up question 2?", "Follow-up question 3?"]
}}"""

    story_data: dict = {}
    try:
        r = generate_content_retrying(
            TEXT_MODEL,
            story_prompt,
            config=types.GenerateContentConfig(temperature=0.8, max_output_tokens=2000),
        )
        story_data = extract_json(r.text)
    except Exception as e:
        logger.error(f"[Storytelling] text failed: {e}")
        story_data = {
            "headline": f"{topic} — Architecture Deep Dive",
            "story": f"The {topic} is a critical component of our banking infrastructure. It handles core financial operations and serves thousands of daily transactions. Built by our platform engineering team, it underpins the reliability our customers depend on.",
            "visual_description": f"Architecture diagram for {topic} with upstream and downstream systems",
            "audio_script": f"Welcome to the {topic} overview. This system sits at the heart of our banking platform.",
            "insights": ["Core system in the banking stack", "High availability required 24/7", "Multiple team dependencies"],
            "risk_analysis": "Critical system — downstream impact on all consumers if unavailable.",
            "followups": ["What are the dependencies?", "Who owns this system?", "What is the SLA?"],
        }

    # Image via Imagen 3 (async thread)
    image_b64 = None
    try:
        img_prompt = (
            f"Professional technical architecture diagram for a banking system: '{topic}'. "
            f"{story_data.get('visual_description', '')} "
            "Style: dark navy background, glowing cyan/blue boxes, white labels, clean arrows, "
            "enterprise fintech aesthetic. No people, no text overlays, pure technical diagram."
        )
        image_b64 = await asyncio.to_thread(sync_gen_image_b64, img_prompt)
    except Exception as e:
        logger.error(f"[Storytelling] image failed: {e}")

    # Audio via Gemini TTS (async thread)
    audio_b64 = None
    try:
        audio_b64 = await asyncio.to_thread(
            sync_tts_to_wav,
            story_data.get("audio_script", f"Welcome to the {topic} overview."),
            "Kore",
        )
    except Exception as e:
        logger.error(f"[Storytelling] TTS failed: {e}")

    return {
        "headline": story_data.get("headline", topic),
        "story": story_data.get("story", ""),
        "image_b64": image_b64,
        "image_mime": "image/png",
        "audio_b64": audio_b64,
        "audio_script": story_data.get("audio_script", ""),
        "insights": story_data.get("insights", []),
        "risk_analysis": story_data.get("risk_analysis", ""),
        "followups": story_data.get("followups", []),
        "visual_description": story_data.get("visual_description", ""),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT 4 — KT TRAINING AGENT (4 weeks × 3 scenes: image + audio + text)
# ═══════════════════════════════════════════════════════════════════════════════
KT_SCENE_VOICES = ["Puck", "Kore", "Charon"]


def _normalize_week_video_scenes(week: dict) -> list:
    raw = week.get("video_scenes") or []
    out = []
    if isinstance(raw, list):
        for s in raw[:5]:
            if not isinstance(s, dict):
                continue
            title = s.get("title") or s.get("scene_title") or "Scene"
            narr = (s.get("narration_script") or s.get("narration") or "").strip()
            vis = (s.get("visual_prompt") or week.get("image_prompt") or "").strip()
            if narr and vis:
                out.append({
                    "title": str(title)[:120],
                    "narration_script": narr[:3000],
                    "visual_prompt": vis[:1500],
                })
    theme = week.get("theme") or f"Week {week.get('week', 1)}"
    story = (week.get("story") or "").strip()
    ip = (week.get("image_prompt") or "").strip() or f"Professional banking engineering illustration for {theme}"
    while len(out) < 3:
        i = len(out)
        if i == 0:
            out.append({
                "title": "Opening",
                "narration_script": f"Welcome to {theme}. {story[:600]}",
                "visual_prompt": ip,
            })
        elif i == 1:
            out.append({
                "title": "Deep Dive",
                "narration_script": f"In {theme}, connect what you build to customer trust and measurable SLOs. {story[:400]}",
                "visual_prompt": f"Technical architecture illustration, dark fintech style: {ip}",
            })
        else:
            out.append({
                "title": "Action",
                "narration_script": f"Ship small, document decisions, and ask early. This week: {theme}.",
                "visual_prompt": f"Engineering collaboration, modern bank tech: {theme}",
            })
    return out[:3]


async def _week_scene_media(week: dict, sem: asyncio.Semaphore) -> dict:
    scenes = _normalize_week_video_scenes(week)
    week["video_scenes"] = scenes

    async def one_scene(si: int, sc: dict) -> dict:
        async with sem:
            img = await asyncio.to_thread(sync_gen_image_b64, sc["visual_prompt"])
            aud = await asyncio.to_thread(
                sync_tts_to_wav,
                sc["narration_script"],
                KT_SCENE_VOICES[si % len(KT_SCENE_VOICES)],
            )
        return {
            "title": sc["title"],
            "narration_script": sc["narration_script"],
            "image_b64": img,
            "audio_b64": aud,
        }

    week["scene_media"] = list(
        await asyncio.gather(*[one_scene(i, s) for i, s in enumerate(scenes)])
    )
    if week["scene_media"] and week["scene_media"][0].get("image_b64"):
        week["image_b64"] = week["scene_media"][0]["image_b64"]
    return week


async def kt_training_agent(role: str, name: str) -> dict:
    all_systems = json.dumps(
        [{"name": s["name"], "tech": s.get("tech_stack", [])[:3], "team": s.get("owning_team", "")}
         for s in BANKING_DATA.get("systems", [])], indent=2
    )
    teams_json = json.dumps(
        [{"name": t["name"], "head": t.get("head", ""), "owns": t.get("owned_systems", [])}
         for t in BANKING_DATA.get("teams", [])], indent=2
    )
    process_json = json.dumps(BANKING_DATA.get("processes", {}).get("onboarding", {}), indent=2)
    mm_excerpt = multimodal_training_excerpt(role=role, max_chars=6000)

    kt_prompt = f"""You are a Senior Engineering Mentor at a top-tier bank.
Create an immersive 4-week KT onboarding plan for {name} joining as {role}.

Available Systems:
{all_systems}

Teams:
{teams_json}

Onboarding Process:
{process_json}

Style guide:
{mm_excerpt}

Return ONLY valid JSON (no markdown, no extra text):
{{
  "welcome_message": "Personal warm 2-sentence welcome for {name} as {role}.",
  "role_overview": "What this role does at the bank in 2 sentences.",
  "audio_script": "35-45 second motivational welcome voiceover for {name}. Warm, inspiring.",
  "weeks": [
    {{
      "week": 1,
      "theme": "Week theme title",
      "story": "2-3 sentence hook for the week",
      "story_extended": "Long-form reading (4-6 paragraphs): deeper narrative, concrete examples, how this connects to banking systems and the {role} role.",
      "image_prompt": "Hero illustration prompt — professional banking engineering, no text overlay",
      "video_scenes": [
        {{
          "title": "Scene 1 title",
          "narration_script": "60-80 words voiceover — set context, mention 1-2 real systems",
          "visual_prompt": "Image prompt for scene 1 — dark fintech visual, no text overlay, max 200 chars"
        }},
        {{
          "title": "Scene 2 title",
          "narration_script": "60-80 words — technical focus, habits, risks",
          "visual_prompt": "Image prompt for scene 2, max 200 chars"
        }},
        {{
          "title": "Scene 3 title",
          "narration_script": "60-80 words — actions, mentors, success signals",
          "visual_prompt": "Image prompt for scene 3, max 200 chars"
        }}
      ],
      "tasks": [
        {{"title": "Task", "description": "Action + why it matters", "type": "setup", "estimate": "1-2 hrs"}},
        {{"title": "Task", "description": "...", "type": "read", "estimate": "2 hrs"}},
        {{"title": "Task", "description": "...", "type": "meet", "estimate": "1 hr"}},
        {{"title": "Task", "description": "...", "type": "code", "estimate": "3 hrs"}},
        {{"title": "Task", "description": "...", "type": "explore", "estimate": "2 hrs"}}
      ],
      "systems_to_learn": ["System Name 1", "System Name 2"],
      "quiz": [
        {{"q": "Question?", "options": ["A","B","C","D"], "answer": 0, "why": "Explanation"}},
        {{"q": "Question?", "options": ["A","B","C","D"], "answer": 1, "why": "Explanation"}}
      ]
    }}
  ],
  "key_contacts": [
    {{"name": "Person Name", "role": "Their role", "for": "What to ask them"}}
  ],
  "success_metrics": ["Metric by end of week 1", "Metric by end of month 1"]
}}
Create ALL 4 weeks. Each week MUST have exactly 3 video_scenes. Use real system names."""

    kt_data: dict = {}
    try:
        r = generate_content_retrying(
            TEXT_MODEL,
            kt_prompt,
            config=types.GenerateContentConfig(temperature=0.7, max_output_tokens=8192),
        )
        kt_data = extract_json(r.text)
    except Exception as e:
        logger.error(f"[KT] text gen failed: {e}")
        kt_data = {"error": str(e), "weeks": []}

    welcome_script = kt_data.get("audio_script") or (
        f"Welcome to the team, {name}! You're joining as a {role}. "
        "Your structured onboarding journey starts now. We're excited to have you here."
    )
    welcome_audio_b64 = await asyncio.to_thread(sync_tts_to_wav, welcome_script, "Puck")

    welcome_prompt = (
        f"Welcoming onboarding illustration for a new {role} at a modern fintech bank. "
        "Futuristic open office, large screens showing code and dashboards, "
        "diverse engineering team welcoming a newcomer. Warm golden light, vibrant, professional. "
        "No text overlay."
    )
    welcome_image_b64 = await asyncio.to_thread(sync_gen_image_b64, welcome_prompt)

    # Limit parallelism to avoid quota exhaustion on Vertex
    sem = asyncio.Semaphore(2)
    weeks = kt_data.get("weeks") or []
    if weeks:
        kt_data["weeks"] = list(
            await asyncio.gather(
                *[_week_scene_media(w, sem) for w in weeks],
                return_exceptions=True,
            )
        )
        kt_data["weeks"] = [w for w in kt_data["weeks"] if isinstance(w, dict)]

    kt_data["welcome_image_b64"] = welcome_image_b64
    kt_data["welcome_audio_b64"] = welcome_audio_b64
    kt_data["role"] = role
    kt_data["name"] = name
    return kt_data


# ═══════════════════════════════════════════════════════════════════════════════
# KT COACH AGENT
# ═══════════════════════════════════════════════════════════════════════════════
async def kt_coach_agent(message: str, history: list, plan_digest: dict) -> str:
    digest = json.dumps(plan_digest or {}, indent=2, ensure_ascii=False)
    if len(digest) > 20000:
        digest = digest[:20000] + "\n…"

    system_instruction = (
        "You are a KT (knowledge transfer) onboarding coach for a bank engineering org. "
        "The learner has a personalized 4-week plan with welcome audio, weekly reading, "
        "interactive video scenes (image + audio), tasks, and quizzes. "
        "Answer ONLY from the PLAN DIGEST. If not listed, say so and point them to the relevant week. "
        "Be warm and concise (short paragraphs or bullets).\n\nPLAN DIGEST:\n" + digest
    )

    messages = []
    for h in (history or [])[-8:]:
        messages.append({"role": h.get("role", "user"), "parts": [{"text": h.get("content", "")}]})
    messages.append({"role": "user", "parts": [{"text": message}]})

    try:
        r = generate_content_retrying(
            TEXT_MODEL,
            messages,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.4,
                max_output_tokens=800,
            ),
        )
        return r.text or ""
    except Exception as e:
        logger.error(f"[KT Coach] failed: {e}")
        return "The coach could not respond right now. Please try again."


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT 5 — LIVE ASSISTANT (grounded Q&A, no hallucination)
# ═══════════════════════════════════════════════════════════════════════════════
async def live_assistant_agent(question: str, history: list) -> str:
    context = context_agent(question)
    ctx_str = json.dumps(
        {"systems": context["systems"][:4], "processes": context["processes"]}, indent=2
    )

    system_instruction = (
        "You are Intellifox, an AI assistant with deep knowledge of our banking engineering organization.\n\n"
        f"GROUNDED KNOWLEDGE BASE:\n{ctx_str}\n\n"
        "Rules:\n"
        "- Answer ONLY based on the knowledge base above. Never hallucinate.\n"
        "- Cite systems by name: e.g. 'The Core Banking System (owned by Platform Engineering)...'\n"
        "- Be concise but specific (3-5 sentences).\n"
        "- If you don't know, say 'This isn't in my knowledge base yet.'\n"
        "- For process questions, reference the actual deployment/incident process."
    )

    messages = []
    for h in (history or [])[-6:]:
        messages.append({"role": h.get("role", "user"), "parts": [{"text": h.get("content", "")}]})
    messages.append({"role": "user", "parts": [{"text": question}]})

    try:
        r = generate_content_retrying(
            TEXT_MODEL,
            messages,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.3,
                max_output_tokens=600,
            ),
        )
        return r.text or "I encountered an error. Please try again."
    except Exception as e:
        logger.error(f"[Assistant] failed: {e}")
        return "I encountered an error. Please try again."


# ── PYDANTIC MODELS ────────────────────────────────────────────────────────────
class StoryRequest(BaseModel):
    topic: str

class TrainingRequest(BaseModel):
    role: str = "Full Stack Developer"
    name: str = "New Joiner"

class ChatRequest(BaseModel):
    message: str
    history: list = []

class PlanCoachRequest(BaseModel):
    message: str
    history: list = Field(default_factory=list)
    plan_digest: dict = Field(default_factory=dict)


# ── ROUTES ─────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return FileResponse(os.path.join(_ROOT, "index.html"))

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "Intellifox AI v2.1",
        "run_env": RUN_ENV,
        "agents": ["context", "graph", "storytelling", "kt-training", "kt-coach", "live-assistant"],
        "gemini_backend": _gemini_backend_name(),
        "gemini_auth": (
            "vertex_adc" if (USE_VERTEX_AI or GCP_PROJECT) and client
            else ("api_key" if client and GEMINI_API_KEY else "none")
        ),
        "gcp_vertex": {
            "enabled": bool(USE_VERTEX_AI or GCP_PROJECT),
            "project": GCP_PROJECT or None,
            "location": GCP_LOCATION or None,
        },
        "models": {"text": TEXT_MODEL, "image": IMAGE_MODEL, "tts": TTS_MODEL},
        "paths": {"root": _ROOT, "knowledge_json": _KB_PATH},
        "knowledge_loaded": bool(BANKING_DATA.get("systems")),
    }

@app.get("/api/systems")
async def get_systems():
    return {
        "systems": [
            {
                "id": s["id"], "name": s["name"],
                "risk": s.get("risk_level", "low"),
                "team": s.get("owning_team", ""),
                "tech": s.get("tech_stack", [])[:3],
            }
            for s in BANKING_DATA.get("systems", [])
        ]
    }

@app.get("/api/graph")
async def get_graph():
    return knowledge_graph_agent()

@app.post("/api/story")
async def story(req: StoryRequest):
    if not req.topic.strip():
        raise HTTPException(400, "topic is required")
    return await storytelling_agent(req.topic)

@app.post("/api/onboarding/generate")
async def generate_onboarding(req: TrainingRequest):
    return await kt_training_agent(req.role, req.name)

@app.post("/api/onboarding/coach")
async def onboarding_coach(req: PlanCoachRequest):
    if not req.message.strip():
        raise HTTPException(400, "message is required")
    text = await kt_coach_agent(req.message, req.history, req.plan_digest)
    return {"response": text}

@app.post("/api/chat")
async def chat(req: ChatRequest):
    answer = await live_assistant_agent(req.message, req.history)
    return {"response": answer}

@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    answer = await live_assistant_agent(req.message, req.history)
    async def gen():
        words = answer.split()
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield f"data: {json.dumps({'text': chunk})}\n\n"
            await asyncio.sleep(0.03)
        yield "data: [DONE]\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")


# ── ENTRY POINT ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    host = os.environ.get("UVICORN_HOST", "127.0.0.1")
    reload = os.environ.get("UVICORN_RELOAD", "").strip().lower() in ("1", "true", "yes", "on")
    logger.info("🦊 Intellifox AI starting on http://%s:%s  reload=%s  backend=%s",
                host, port, reload, _gemini_backend_name())
    uvicorn.run("main:app", host=host, port=port, reload=reload)
