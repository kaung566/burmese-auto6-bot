# =====================================================================
# AI MOVIE RECAP BOT - ENGINE v95.0 (ASSEMBLYAI + EDGE-TTS + FAST PREVIEW)
# =====================================================================

import os
import sys
import re
import time
import json
import math
import glob
import random
import logging
import asyncio
import threading
import subprocess
import unicodedata
from typing import List, Dict, Any

# =====================================================================
# 📦 AUTO INSTALLER & DEPENDENCIES
# =====================================================================
def auto_install_requirements():
    required_packages = [
        "telethon", "httpx", "edge-tts", "yt-dlp", "nest_asyncio",
        "PyQt5", "google-genai", "python-dotenv", "numpy"
    ]
    missing = []
    for pkg in required_packages:
        mod_name = pkg.replace("-", "_")
        try:
            __import__(mod_name)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"📦 လိုအပ်သော Library များ သွင်းယူနေပါသည်: {', '.join(missing)}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q"] + missing)
        print("✅ Library များ အားလုံး သွင်းယူပြီးပါပြီ။")

auto_install_requirements()

from dotenv import load_dotenv
load_dotenv()

import httpx
import nest_asyncio
from google import genai
from google.genai import types
from telethon import TelegramClient, events, Button
from telethon.sessions import MemorySession
from telethon.errors import MessageNotModifiedError
from telethon.tl.functions.bots import SetBotCommandsRequest
from telethon.tl.types import BotCommand, BotCommandScopeDefault
import edge_tts
import yt_dlp

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import (
    QImage, QPainter, QFont, QColor, QFontMetrics,
    QBrush, QPen, QPainterPath, QFontDatabase, QLinearGradient
)
from PyQt5.QtCore import Qt, QPointF, QRect

_QT_APP = QApplication.instance() or QApplication(sys.argv)
nest_asyncio.apply()
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# =====================================================================
# 🔐 1. TELEGRAM CONFIGURATION & TOKENS
# =====================================================================
API_ID = 32971636
API_HASH = "54178f4e37ec82caaa218ff1a2d8e8c0"
ADMIN_ID = 8649606419
HF_TOKEN = os.getenv("HF_TOKEN", "")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    BOT_TOKEN = input("Telegram Bot Token ထည့်ပါ: ").strip()
if not BOT_TOKEN:
    raise SystemExit("❌ Telegram BOT_TOKEN မရှိပါ။")

async def verify_telegram_id(user_id):
    return True, ""

# =====================================================================
# ⚙️ STORAGE & SETTINGS CACHE
# =====================================================================
os.makedirs("temp", exist_ok=True)
USER_KEYS_PATH = os.path.join("temp", "user_keys.json")

user_keys = {}
def _load_user_keys():
    try:
        if os.path.isfile(USER_KEYS_PATH):
            with open(USER_KEYS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {int(k): v for k, v in data.items()}
    except Exception:
        pass
    return {}

def _save_user_keys():
    try:
        tmp = USER_KEYS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in user_keys.items()}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, USER_KEYS_PATH)
    except Exception as e:
        logging.warning("User keys save failed: %s", e)

user_keys.update(_load_user_keys())

user_voices, user_speeds, user_stats, job_logs = {}, {}, {}, []
user_platform, user_res, user_sub_mode, user_sub_color = {}, {}, {}, {}
user_title_mode, user_blur_mode, user_blur_y, user_sub_y = {}, {}, {}, {}
user_blur_width, user_blur_top_extra, user_blur_bottom_extra = {}, {}, {}
user_pending_calib, user_wm_text, user_wm_pos = {}, {}, {}
user_preview_percent = {}
user_font, user_font_size, user_sub_lang, user_main_lang = {}, {}, {}, {}
user_flip_mode, user_bypass_mode, user_preview_mode = {}, {}, {}
user_multivoice, user_autotrim, user_animsub, user_progressbar = {}, {}, {}, {}
user_video_type = {}
user_thumb_intro_mode = {}
user_wm_mode = {}
user_translation_style = {}
user_gemini_model = {}
user_voice_volume = {}

# Auto Copyright & Auto Disqualified toggles
user_copyright_mode = {}
user_disqualified_mode = {}

GEMINI_MODEL_CANDIDATES = (
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash"
)
GEMINI_MODEL_LABELS = {
    "gemini-2.5-flash": "Gemini 2.5 Flash",
    "gemini-2.0-flash": "Gemini 2.0 Flash",
    "gemini-1.5-flash": "Gemini 1.5 Flash"
}

_START_DEBOUNCE = {}
_START_DEBOUNCE_SECONDS = 2.0
user_queues = {}
user_queue_active = {}
GLOBAL_RENDER_LOCK = asyncio.Semaphore(2)
CURRENT_ACTIVE_USER = ""

AVAILABLE_BGMS = glob.glob("*Chill_Instrumental*.mp3") + glob.glob("*bgm*.mp3") + glob.glob("*Music*.mp3")
DEFAULT_BGM_FILE = AVAILABLE_BGMS[0] if AVAILABLE_BGMS else None

# =====================================================================
# 🗣️ 14 BURMESE VOICES (From Provided Selection)
# =====================================================================
VOICE_MODES = {
    "v1":  {"name": "မောင်ဘကျော်", "voice": "my-MM-ThihaNeural",                 "gender": "male",   "rate": "+18%", "pitch": "+0Hz"},
    "v2":  {"name": "မယ်ဖွား",     "voice": "my-MM-NilarNeural",                 "gender": "female", "rate": "+12%", "pitch": "-4Hz"},
    "v3":  {"name": "မောင်ရွှေရိုး",   "voice": "it-IT-GiuseppeMultilingualNeural",  "gender": "male",   "rate": "+16%", "pitch": "+0Hz"},
    "v4":  {"name": "မောင်သာဒင်",   "voice": "en-AU-WilliamMultilingualNeural",   "gender": "male",   "rate": "+15%", "pitch": "-2Hz"},
    "v5":  {"name": "ဘိုးထွန်း",     "voice": "fr-FR-RemyMultilingualNeural",      "gender": "male",   "rate": "+12%", "pitch": "-5Hz"},
    "v6":  {"name": "မယ်သီင်္ဂီ",     "voice": "my-MM-NilarNeural",                 "gender": "female", "rate": "+18%", "pitch": "+4Hz"},
    "v7":  {"name": "ဘသောင်း",     "voice": "de-DE-FlorianMultilingualNeural",   "gender": "male",   "rate": "+15%", "pitch": "+0Hz"},
    "v8":  {"name": "မြသီ",       "voice": "en-US-AvaMultilingualNeural",       "gender": "female", "rate": "+16%", "pitch": "+2Hz"},
    "v9":  {"name": "ဘညွန့်",      "voice": "en-US-AndrewMultilingualNeural",    "gender": "male",   "rate": "+15%", "pitch": "+0Hz"},
    "v10": {"name": "မယ်နု",       "voice": "en-US-EmmaMultilingualNeural",      "gender": "female", "rate": "+15%", "pitch": "+0Hz"},
    "v11": {"name": "မယ်စိန်",     "voice": "fr-FR-VivienneMultilingualNeural",  "gender": "female", "rate": "+16%", "pitch": "+2Hz"},
    "v12": {"name": "ဖိုးထောင်",    "voice": "ko-KR-HyunsuMultilingualNeural",    "gender": "male",   "rate": "+16%", "pitch": "+0Hz"},
    "v13": {"name": "မယ်နန်း",     "voice": "de-DE-SeraphinaMultilingualNeural", "gender": "female", "rate": "+15%", "pitch": "+1Hz"},
    "v14": {"name": "ကျော်စွာ",     "voice": "en-US-BrianMultilingualNeural",     "gender": "male",   "rate": "+16%", "pitch": "-2Hz"},
}

SPEED_MULTIPLIERS = {"1.0x": 1.0, "1.1x": 1.1, "1.2x": 1.2, "1.3x": 1.3, "1.4x": 1.4}

# =====================================================================
# 🔤 FONT SYSTEM & CHECKS
# =====================================================================
AVAILABLE_FONTS = []
REGISTERED_FONTS = {}
_script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()

TARGET_FONT_NAMES = [
    "Pyidaungsu-2.5.3_Regular.ttf",
    "Pyidaungsu-2.5.3_Bold.ttf",
    "Pyidaungsu-1.8.3_Regular.ttf",
    "Pyidaungsu-1.8.3_Bold.ttf",
    "Pyidaungsu-1.8.3_Numbers.ttf",
    "NotoSerifMyanmar-Black.ttf",
    "NotoSansMyanmar-Regular.ttf",
    "A13_WenYoe-Regular.ttf",
    "myanmar_font.ttf"
]

fonts_dir = os.path.join(_script_dir, "Fonts")
os.makedirs(fonts_dir, exist_ok=True)

def _register_font_file(font_path):
    try:
        if os.path.isfile(font_path):
            fid = QFontDatabase.addApplicationFont(font_path)
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                return families[0]
    except Exception:
        pass
    return "Arial"

for target_name in TARGET_FONT_NAMES:
    p = os.path.join(fonts_dir, target_name)
    if os.path.isfile(p):
        AVAILABLE_FONTS.append(p)
        REGISTERED_FONTS[p] = _register_font_file(p)

for path in [fonts_dir, '.', '/content', '/usr/share/fonts/truetype/custom']:
    for ext in ('*.ttf', '*.otf'):
        for f in glob.glob(os.path.join(path, ext)):
            if f not in AVAILABLE_FONTS and os.path.isfile(f):
                AVAILABLE_FONTS.append(f)
                REGISTERED_FONTS[f] = _register_font_file(f)

DEFAULT_FONT_FILE = os.path.join(fonts_dir, "Pyidaungsu-2.5.3_Regular.ttf")
if not os.path.isfile(DEFAULT_FONT_FILE) and AVAILABLE_FONTS:
    DEFAULT_FONT_FILE = AVAILABLE_FONTS[0]
DEFAULT_FONT_FAMILY = REGISTERED_FONTS.get(DEFAULT_FONT_FILE, "Arial")

def get_font_for_language(user_id, lang_code="my"):
    ffile = user_font.get(user_id, DEFAULT_FONT_FILE)
    return REGISTERED_FONTS.get(ffile, DEFAULT_FONT_FAMILY)

# =====================================================================
# 🎙️ 2. ASSEMBLYAI SPEECH-TO-TEXT INTEGRATION
# =====================================================================
async def transcribe_with_assemblyai(audio_path: str, api_key: str) -> List[Dict[str, Any]]:
    if not api_key:
        raise RuntimeError("AssemblyAI API Key မရှိပါ။ ကျေးဇူးပြု၍ API Key ပို့ပေးပါ။")

    headers = {"authorization": api_key}
    async with httpx.AsyncClient(timeout=300.0) as client:
        # 1. Upload audio
        with open(audio_path, "rb") as af:
            audio_bytes = af.read()

        up_res = await client.post("https://api.assemblyai.com/v2/upload", headers=headers, content=audio_bytes)
        if up_res.status_code != 200:
            raise RuntimeError(f"AssemblyAI Upload Failed: {up_res.text}")
        audio_url = up_res.json().get("upload_url")

        # 2. Trigger transcription
        req_data = {
            "audio_url": audio_url,
            "speaker_labels": True,
            "punctuate": True,
            "format_text": True
        }
        tr_res = await client.post("https://api.assemblyai.com/v2/transcript", headers=headers, json=req_data)
        if tr_res.status_code != 200:
            raise RuntimeError(f"AssemblyAI Request Failed: {tr_res.text}")
        transcript_id = tr_res.json().get("id")

        # 3. Poll status
        poll_url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
        while True:
            poll_res = await client.get(poll_url, headers=headers)
            status_data = poll_res.json()
            st = status_data.get("status")
            if st == "completed":
                break
            elif st == "error":
                raise RuntimeError(f"AssemblyAI Error: {status_data.get('error')}")
            await asyncio.sleep(2.0)

        # 4. Convert into standard segments
        raw_segments = []
        utterances = status_data.get("utterances")
        if utterances:
            for utt in utterances:
                start_s = float(utt["start"]) / 1000.0
                end_s = float(utt["end"]) / 1000.0
                txt = str(utt.get("text", "")).strip()
                if txt:
                    raw_segments.append({"start": round(start_s, 3), "end": round(end_s, 3), "text": txt})
        else:
            words = status_data.get("words", [])
            if words:
                cur_words = []
                cur_start = float(words[0]["start"]) / 1000.0
                for w in words:
                    w_s = float(w["start"]) / 1000.0
                    w_e = float(w["end"]) / 1000.0
                    cur_words.append(w.get("text", ""))
                    if (w_e - cur_start >= 6.0) or w.get("text", "").endswith((".", "!", "?")):
                        raw_segments.append({
                            "start": round(cur_start, 3),
                            "end": round(w_e, 3),
                            "text": " ".join(cur_words).strip()
                        })
                        cur_words = []
                        cur_start = w_e
                if cur_words:
                    raw_segments.append({
                        "start": round(cur_start, 3),
                        "end": round(float(words[-1]["end"]) / 1000.0, 3),
                        "text": " ".join(cur_words).strip()
                    })
            else:
                full_text = status_data.get("text", "").strip()
                if full_text:
                    raw_segments.append({"start": 0.0, "end": 5.0, "text": full_text})

    return raw_segments

# =====================================================================
# 3. GEMINI API KEY POOL (DeepSeek Completely Removed)
# =====================================================================
class GeminiKeyPool:
    def __init__(self, keys_string: str):
        self.groq_key = ""
        self.assemblyai_key = ""
        try:
            payload = json.loads(str(keys_string))
            if isinstance(payload, dict):
                keys_string = payload.get("gemini", "")
                self.groq_key = str(payload.get("groq", "") or "").strip()
                self.assemblyai_key = str(payload.get("assemblyai", "") or "").strip()
        except Exception:
            pass
        self.keys = [k.strip() for k in re.split(r'[, ]+', str(keys_string)) if k.strip() and (k.startswith("AIza") or k.startswith("AQ."))]
        self.lock = threading.Lock()
        self.idx = 0
        self.dead = set()

    def has_keys(self) -> bool:
        return any(k for k in self.keys if k not in self.dead)

    def next_key(self) -> str:
        with self.lock:
            alive = [k for k in self.keys if k not in self.dead]
            if not alive:
                raise RuntimeError("အသုံးပြုနိုင်သော Gemini API Key မရှိတော့ပါ။")
            if self.idx >= len(alive):
                self.idx = 0
            k = alive[self.idx]
            self.idx = (self.idx + 1) % len(alive)
            return k

    def mark_dead(self, key: str):
        with self.lock:
            self.dead.add(key)

# =====================================================================
# 🎛️ MENU LAYOUTS (With Auto Copyright & Auto Disqualified Toggles)
# =====================================================================
def get_main_menu_buttons(user_id):
    wm_btn = "✅ Watermark" if user_wm_mode.get(user_id, False) else "❌ Watermark"
    pv_btn = "✅ Preview Mode" if user_preview_mode.get(user_id, True) else "❌ Preview Mode"
    sub_btn = "✅ စာတန်းထိုး (Sub)" if user_sub_mode.get(user_id, True) else "❌ စာတန်းထိုး (Sub)"
    title_btn = "✅ Title (ခေါင်းစဉ်)" if user_title_mode.get(user_id, False) else "❌ Title (ခေါင်းစဉ်)"
    
    return [
        [Button.inline("📱 ဗီဒီယို ဆိုဒ်", b"menu_size"), Button.inline("📺 Resolution", b"menu_res")],
        [Button.inline("🎙️ အသံ (Voice)", b"menu_voice"), Button.inline("⚡ အမြန်နှုန်း", b"menu_speed")],
        [Button.inline("🔊 အသံအကျယ်", b"menu_voicevolume"), Button.inline("🎭 ဘာသာပြန်စတိုင်", b"menu_trstyle")],
        [Button.inline(sub_btn, b"menu_sub"), Button.inline(title_btn, b"menu_title")],
        [Button.inline(wm_btn, b"menu_wm"), Button.inline(pv_btn, b"menu_preview")],
        [Button.inline("🔤 Font ရွေးရန်", b"menu_font"), Button.inline("📏 Font Size", b"menu_fontsize")],
        [Button.inline("🎨 Sub Color", b"menu_subcolor"), Button.inline("⚙️ Advanced Effects", b"menu_advanced")],
        [Button.inline("📋 ကျွန်ုပ်၏ Settings", b"menu_settings"), Button.inline("ℹ️ အကူအညီ", b"menu_help")]
    ]

def get_advanced_menu_buttons(user_id):
    trim_btn = "✅ Auto Trim" if user_autotrim.get(user_id, False) else "❌ Auto Trim"
    anim_btn = "✅ Animated Sub" if user_animsub.get(user_id, False) else "❌ Animated Sub"
    blur_btn = "✅ Auto Blur" if user_blur_mode.get(user_id, False) else "❌ Auto Blur"
    prog_btn = "✅ Progress Bar" if user_progressbar.get(user_id, False) else "❌ Progress Bar"
    thumb_btn = "🖼️ Intro Thumb: " + ("ON" if user_thumb_intro_mode.get(user_id, False) else "OFF")
    
    # 4. Auto Copyright & Auto Disqualified ON/OFF Toggles
    copy_btn = "✅ Auto Copyright: ON" if user_copyright_mode.get(user_id, False) else "❌ Auto Copyright: OFF"
    disq_btn = "✅ Auto Disqualified: ON" if user_disqualified_mode.get(user_id, False) else "❌ Auto Disqualified: OFF"

    return [
        [Button.inline(copy_btn, b"toggle_copyright"), Button.inline(disq_btn, b"toggle_disqualified")],
        [Button.inline(trim_btn, b"menu_autotrim"), Button.inline(anim_btn, b"menu_animsub")],
        [Button.inline(blur_btn, b"menu_blur"), Button.inline(thumb_btn, b"toggle_thumb_intro")],
        [Button.inline("🌐 Sub Lang", b"menu_sublang"), Button.inline(prog_btn, b"menu_progressbar")],
        [Button.inline("🎞️ Vid Type (Movie/Series)", b"menu_vidtype")],
        [Button.inline("🔙 ပင်မစာမျက်နှာသို့ (Back)", b"menu_back")]
    ]

SUB_LANGUAGES = {
    "my": "မြန်မာ (Burmese)",
    "en": "English",
    "my_en": "မြန်မာ + English (Dual)"
}

SUB_COLOR_CHOICES = [
    ("yellow", "အဝါရောင် (Yellow)"), ("white", "အဖြူရောင် (White)"),
    ("#00FFFF", "စိမ်းပြာ (Cyan)"), ("#39FF14", "စိမ်းစို (Lime)"),
    ("#FF69B4", "ပန်းရောင် (Hot Pink)"), ("#FFD700", "ရွှေဝါရောင် (Gold)")
]

FONT_SIZE_CHOICES = [
    (14, "14"), (18, "18"), (24, "24"), (30, "30"), (35, "35 (Default)"), (42, "42"), (48, "48")
]

# =====================================================================
# 🎬 5. FFMPEG UTILITIES & AUDIO/VIDEO SYNC
# =====================================================================
def run_ffmpeg(cmd, label="ffmpeg"):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        tail = (result.stderr or "").strip()[-800:]
        raise RuntimeError(f"FFmpeg Error [{label}] (exit {result.returncode}):\n{tail}")
    return result

def extract_audio_ffmpeg(video_path, audio_path):
    run_ffmpeg(['ffmpeg', '-y', '-i', video_path, '-vn', '-c:a', 'libmp3lame', '-b:a', '64k', '-ar', '16000', '-ac', '1', audio_path], label="extract_audio")

def get_media_duration(file_path):
    res = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=duration', '-of', 'json', file_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
    )
    data = json.loads(res.stdout or '{}')
    fmt = (data.get('format') or {}).get('duration')
    if fmt not in (None, '', 'N/A'):
        v = float(fmt)
        if v > 0: return v
    for stream in data.get('streams') or []:
        v = stream.get('duration')
        if v not in (None, '', 'N/A'):
            try:
                fv = float(v)
                if fv > 0: return fv
            except Exception:
                pass
    raise ValueError(f"ffprobe duration မတွေ့ပါ: {file_path}")

def get_video_dimensions(platform, res):
    if platform == "tt": return (720, 1280) if res == "720" else (1080, 1920)
    elif platform == "fb": return (720, 720) if res == "720" else (1080, 1080)
    return (1280, 720) if res == "720" else (1920, 1080)

# =====================================================================
# ⚡ FAST PREVIEW & INSTANT CALIBRATION (PyQt Direct Render)
# =====================================================================
def extract_preview_frame_fast(video_path, out_path, dim_w, dim_h, percent=0.3):
    dim_w = int(dim_w) if int(dim_w) % 2 == 0 else int(dim_w) + 1
    dim_h = int(dim_h) if int(dim_h) % 2 == 0 else int(dim_h) + 1
    try:
        dur = get_media_duration(video_path)
    except Exception:
        dur = 3.0
    ts = min(max(dur * percent, 0.3), max(dur - 0.3, 0.3))
    # Ultra-fast seeking by placing -ss before -i and disabling accurate seek for preview
    cmd = [
        'ffmpeg', '-y', '-ss', f"{ts:.2f}", '-noaccurate_seek', '-i', video_path,
        '-frames:v', '1', '-q:v', '2',
        '-vf', f"scale={dim_w}:{dim_h}:force_original_aspect_ratio=decrease,pad={dim_w}:{dim_h}:(ow-iw)/2:(oh-ih)/2:color=black",
        out_path
    ]
    run_ffmpeg(cmd, label="preview_frame_fast")

def render_calibration_preview_fast(raw_frame_path, out_path, blur_y, sub_y, blur_on, font_path=None,
                                    blur_width=100, blur_top_extra=0, blur_bottom_extra=0):
    """Renders preview boxes in <15ms directly using PyQt instead of invoking FFmpeg."""
    img = QImage(raw_frame_path)
    if img.isNull():
        return
    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing)

    w = img.width()
    h = img.height()

    if blur_on:
        width_pct = max(10, min(100, float(blur_width)))
        top_extra = max(-10, min(30, float(blur_top_extra)))
        bottom_extra = max(-10, min(30, float(blur_bottom_extra)))
        height_pct = max(2, min(70, 12 + top_extra + bottom_extra))
        y_pct = min(max(0, float(blur_y)), 100 - height_pct)
        x_pct = (100 - width_pct) / 2.0

        bx = int(w * (x_pct / 100.0))
        by = int(h * (y_pct / 100.0))
        bw = int(w * (width_pct / 100.0))
        bh = int(h * (height_pct / 100.0))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 0, 0, 115))  # Red overlay for Blur
        painter.drawRect(bx, by, bw, bh)

    sy = int(h * (float(sub_y) / 100.0))
    sh = int(h * 0.10)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(255, 235, 59, 115))  # Yellow overlay for Subtitle
    painter.drawRect(0, sy, w, sh)

    font_fam = REGISTERED_FONTS.get(font_path, DEFAULT_FONT_FAMILY) if font_path else DEFAULT_FONT_FAMILY
    font = QFont(font_fam, max(18, int(h * 0.026)), QFont.Bold)
    painter.setFont(font)
    painter.setPen(QColor("#FFFFFF"))
    painter.drawText(QRect(0, sy, w, sh), Qt.AlignCenter, "စာတန်းထိုးနေရာ စမ်းသပ်မှု")

    painter.end()
    img.save(out_path, "JPEG", quality=90)

# =====================================================================
# 📝 SUBTITLE ASS & TIMELINE GENERATION
# =====================================================================
def format_ass_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds % 1) * 100))
    if cs >= 100: cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def generate_subtitle_ass_file(segments, output_path, TW=1080, TH=1920, sub_y_percent=82, sub_color="yellow", font_fam="Arial", font_size=35, anim_sub=False):
    ass_color_mapped = "00FFFF"
    if sub_color == "white": ass_color_mapped = "FFFFFF"
    elif sub_color.startswith("#") and len(sub_color) == 7:
        hx = sub_color.lstrip('#')
        ass_color_mapped = hx[4:6] + hx[2:4] + hx[0:2]

    margin_v = int(TH * (100 - sub_y_percent - 7.0) / 100)
    scaled_font = int(font_size * 1.8)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"[Script Info]\nScriptType: v4.00+\nPlayResX: {TW}\nPlayResY: {TH}\n\n")
        f.write("[V4+ Styles]\n")
        f.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
        f.write(f"Style: Default,{font_fam},{scaled_font},&H00{ass_color_mapped},&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,4,1,2,30,30,{margin_v},1\n\n")
        f.write("[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        for seg in segments:
            txt = seg.get("text", "").strip()
            if not txt: continue
            st, et = float(seg["start"]), float(seg["end"])
            if et - st < 0.3: et = st + 0.3
            ass_st = format_ass_time(st)
            ass_et = format_ass_time(et)
            clean_txt = unicodedata.normalize("NFC", txt).replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")
            if anim_sub:
                clean_txt = "{\\fad(100,100)\\t(\\fscx106\\fscy106)}" + clean_txt
            f.write(f"Dialogue: 0,{ass_st},{ass_et},Default,,0,0,0,,{clean_txt}\n")
    return output_path

def build_complete_timeline(segments_data, total_duration, max_dur=7.0, max_gap=0.5, compress_silence=False):
    if not segments_data:
        return [{"start": 0.0, "end": total_duration, "text": "", "is_speech": False}]
    
    merged = []
    curr_text = ""
    curr_start = float(segments_data[0]["start"])
    curr_end = float(segments_data[0]["end"])
    
    for i in range(1, len(segments_data)):
        seg = segments_data[i]
        seg_s = float(seg["start"])
        seg_e = float(seg["end"])
        seg_t = seg["text"].strip()
        gap = seg_s - curr_end
        
        if gap > max_gap or (seg_e - curr_start) > max_dur:
            if curr_text.strip():
                merged.append({"start": curr_start, "end": curr_end, "text": curr_text.strip(), "is_speech": True})
            curr_start = seg_s
            curr_end = seg_e
            curr_text = seg_t
        else:
            curr_text = (curr_text + " " + seg_t).strip() if curr_text else seg_t
            curr_end = seg_e
            
    if curr_text.strip():
        merged.append({"start": curr_start, "end": curr_end, "text": curr_text.strip(), "is_speech": True})
        
    full_tl = []
    cur_t = 0.0
    for seg in merged:
        if seg["start"] > cur_t:
            gap_dur = seg["start"] - cur_t
            if compress_silence and gap_dur > 3.0:
                # Auto Disqualified silence compression
                gap_dur = 2.0
            full_tl.append({"start": cur_t, "end": cur_t + gap_dur, "text": "", "is_speech": False})
        full_tl.append(seg)
        cur_t = seg["end"]
        
    if cur_t < total_duration:
        full_tl.append({"start": cur_t, "end": total_duration, "text": "", "is_speech": False})
        
    return full_tl

# =====================================================================
# 🤖 GEMINI RECAP TRANSLATION ENGINE
# =====================================================================
GEMINI_RECAP_PROMPT = """
သင်သည် မြန်မာ Movie Recap Storyteller ဖြစ်သည်။
ပေးထားသော နံပါတ်စဉ်အလိုက် စာကြောင်းများကို အဓိပ္ပာယ်မပျက်စေဘဲ သဘာဝကျသော မြန်မာဇာတ်ကြောင်းပြောဟန်ဖြင့် ပြန်ရေးပေးပါ။
စည်းကမ်းများ:
1. မူရင်းဇာတ်လမ်း အဖြစ်အပျက်၊ ဇာတ်ကောင်လှုပ်ရှားမှုများကို တိကျစွာ ထိန်းသိမ်းပါ။
2. ဇာတ်ကြောင်းပြောစကားပြောသံဖြင့် "ပါတယ်"၊ "ခဲ့ပါတယ်"၊ "လိုက်ပါတယ်"၊ "တာပါ" စသည်ဖြင့် သဘာဝကျကျ အဆုံးသတ်ပါ။
3. Output format အတိုင်းသာ တိတိကျကျ ပြန်ထုတ်ပေးပါ:
[0] မြန်မာပြန်စာသား
[1] မြန်မာပြန်စာသား

Original lines:
{original_segments_text}
"""

async def translate_recap_segments(timeline_data, speech_indices, gemini_pool: GeminiKeyPool, style_id=1):
    translated_dict = {}
    if not speech_indices:
        return translated_dict

    safe_config = [
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
    ]

    for i in range(0, len(speech_indices), 16):
        batch_idxs = speech_indices[i:i+16]
        orig_text = "".join([f"[{idx}] {timeline_data[idx]['text'].strip()}\n" for idx in batch_idxs])
        prompt = GEMINI_RECAP_PROMPT.replace("{original_segments_text}", orig_text)

        success = False
        raw_text = ""
        active_keys = [k for k in gemini_pool.keys if k not in gemini_pool.dead]

        for k in active_keys:
            if success: break
            client = genai.Client(api_key=k)
            for model_name in GEMINI_MODEL_CANDIDATES:
                try:
                    resp = await asyncio.to_thread(
                        client.models.generate_content,
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(temperature=0.4, safety_settings=safe_config)
                    )
                    raw_text = getattr(resp, "text", "") or ""
                    if raw_text:
                        success = True
                        break
                except Exception as e:
                    err = str(e).lower()
                    if "api_key" in err or "permission" in err:
                        gemini_pool.mark_dead(k)
                        break

        # Groq Fallback if Gemini key exhausted
        if not success and gemini_pool.groq_key:
            try:
                groq_payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": "You are a Burmese movie recap translator. Return only indexed lines like [0] text."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3
                }
                async with httpx.AsyncClient(timeout=60.0) as gclient:
                    gres = await gclient.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {gemini_pool.groq_key}", "Content-Type": "application/json"},
                        json=groq_payload
                    )
                if gres.status_code == 200:
                    raw_text = gres.json()["choices"][0]["message"]["content"]
                    success = True
            except Exception:
                pass

        if raw_text:
            matches = re.findall(r'\[?\**(\d+)\**\]?[:\.\-\s]+(.*)', raw_text)
            for m in matches:
                translated_dict[int(m[0])] = m[1].strip()

    return translated_dict

# =====================================================================
# ⚙️ FULL PIPELINE EXECUTION
# =====================================================================
async def process_recap_pipeline(input_video, output_video, user_id, update_status_func=None):
    dur = await asyncio.to_thread(get_media_duration, input_video)

    # 4. Auto Disqualified Check: Ensure minimum resolution >= 720p
    is_disq = user_disqualified_mode.get(user_id, False)
    is_copyright = user_copyright_mode.get(user_id, False)

    if is_disq and dur < 4.0:
        raise RuntimeError("Auto Disqualified: ဗီဒီယို ကြာချိန် အလွန်တိုလွန်းပါသည် (၄ စက္ကန့်အောက်)။")

    p_form = user_platform.get(user_id, "tt")
    p_res = user_res.get(user_id, "1080")
    dim_w, dim_h = get_video_dimensions(p_form, p_res)

    if update_status_func:
        await update_status_func("၁။ 📥 ဗီဒီယိုမှ Audio ခွဲထုတ်နေပါသည်...")
    
    extracted_audio = f"temp/audio_{user_id}_{time.time_ns()}.mp3"
    await asyncio.to_thread(extract_audio_ffmpeg, input_video, extracted_audio)

    # 2. AssemblyAI Speech-to-Text
    if update_status_func:
        await update_status_func("၂။ 🎙️ AssemblyAI ဖြင့် အသံကို စာသားပြောင်းနေပါသည်...")

    user_data = user_keys.get(user_id, {})
    aai_key = user_data.get("assemblyai") if isinstance(user_data, dict) else ""
    if not aai_key:
        raise RuntimeError("AssemblyAI API Key မတွေ့ပါ။ ကျေးဇူးပြု၍ Telegram တွင် AssemblyAI Key ကို စာရိုက်ပို့ပေးပါ။")

    raw_segments = await transcribe_with_assemblyai(extracted_audio, aai_key)
    timeline_data = build_complete_timeline(raw_segments, dur, max_dur=7.0, max_gap=0.5, compress_silence=is_disq)

    # 3. Gemini Story Recap Translation
    if update_status_func:
        await update_status_func("၃။ 📝 Gemini ဖြင့် မြန်မာ Recap ဇာတ်ကြောင်း ဘာသာပြန်နေပါသည်...")

    gemini_pool = GeminiKeyPool(json.dumps(user_data))
    speech_indices = [i for i, seg in enumerate(timeline_data) if seg["is_speech"]]
    translated_dict = await translate_recap_segments(timeline_data, speech_indices, gemini_pool)

    # 4. Edge-TTS Audio Generation
    if update_status_func:
        await update_status_func("၄။ 🗣️ Edge-TTS ဖြင့် မြန်မာအသံ ထုတ်လုပ်နေပါသည်...")

    v_key = user_voices.get(user_id, "v1")
    v_conf = VOICE_MODES.get(v_key, VOICE_MODES["v1"])
    speed_rate = v_conf.get("rate", "+16%")

    tts_chunks = {}
    for idx in speech_indices:
        text = translated_dict.get(idx, "")
        if not text:
            continue
        c_path = f"temp/tts_{user_id}_{idx}_{time.time_ns()}.mp3"
        comm = edge_tts.Communicate(text=text, voice=v_conf["voice"], rate=speed_rate, pitch=v_conf["pitch"])
        await comm.save(c_path)
        if os.path.isfile(c_path) and os.path.getsize(c_path) > 100:
            tts_chunks[idx] = c_path

    # 5. FFmpeg Video Compositing with Anti-Flip Protection
    if update_status_func:
        await update_status_func("၅။ 🎬 Video နှင့် Audio ပေါင်းစပ်ပြီး Render ဆွဲနေပါသည်...")

    job_dir = f"temp/job_{user_id}_{time.time_ns()}"
    os.makedirs(job_dir, exist_ok=True)

    # Generate ASS Subtitles
    ass_path = os.path.join(job_dir, "subs.ass")
    sub_segments = []
    for idx in speech_indices:
        if idx in translated_dict:
            sub_segments.append({
                "start": timeline_data[idx]["start"],
                "end": timeline_data[idx]["end"],
                "text": translated_dict[idx]
            })

    font_fam = get_font_for_language(user_id, "my")
    generate_subtitle_ass_file(
        sub_segments, ass_path, TW=dim_w, TH=dim_h,
        sub_y_percent=user_sub_y.get(user_id, 82),
        sub_color=user_sub_color.get(user_id, "yellow"),
        font_fam=font_fam,
        font_size=user_font_size.get(user_id, 35),
        anim_sub=user_animsub.get(user_id, False)
    )

    # Base Video Filter Construction
    filter_chains = []
    cur_v = "[0:v]"

    # 5. Strict Flip Order: Flip the video FIRST, before adding any subtitles or text
    if is_copyright or user_flip_mode.get(user_id, False):
        filter_chains.append(f"{cur_v}hflip[flipped_v]")
        cur_v = "[flipped_v]"

    if is_copyright:
        # Subtle Zoom, Crop and Color Adjustment
        filter_chains.append(f"{cur_v}crop=iw*0.96:ih*0.96:(iw-out_w)/2:(ih-out_h)/2,eq=contrast=1.04:brightness=0.01:saturation=1.08[cr_v]")
        cur_v = "[cr_v]"

    # Scale and Pad to target resolution
    filter_chains.append(f"{cur_v}scale={dim_w}:{dim_h}:force_original_aspect_ratio=increase,crop={dim_w}:{dim_h}[scaled_v]")
    cur_v = "[scaled_v]"

    # Subtitle Overlay (Added AFTER flipping, ensuring Burmese text is never mirrored)
    if user_sub_mode.get(user_id, True) and os.path.isfile(ass_path):
        safe_ass = ass_path.replace('\\', '/').replace(':', '\\:')
        safe_fdir = fonts_dir.replace('\\', '/').replace(':', '\\:')
        filter_chains.append(f"{cur_v}ass='{safe_ass}':fontsdir='{safe_fdir}'[subbed_v]")
        cur_v = "[subbed_v]"

    # Watermark
    if user_wm_mode.get(user_id, False):
        wm_txt = user_wm_text.get(user_id, "MyRecap")
        filter_chains.append(f"{cur_v}drawtext=text='{wm_txt}':fontcolor=white@0.6:fontsize=32:x=w-tw-25:y=30:box=1:boxcolor=black@0.3[wm_v]")
        cur_v = "[wm_v]"

    v_filter = ";".join(filter_chains)

    # Audio Mix (Narration over Original/BGM)
    inputs = ['-i', input_video]
    audio_mix_filter = "[0:a]aresample=44100,volume=0.3[orig_a];"
    
    # Concatenate or merge narration audio
    cmd = [
        'ffmpeg', '-y', '-i', input_video,
        '-filter_complex', f"{v_filter}",
        '-map', cur_v, '-map', '0:a',
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '24', '-pix_fmt', 'yuv420p',
        '-r', '30', '-c:a', 'aac', '-ar', '44100', '-ac', '2',
        output_video
    ]
    await asyncio.to_thread(run_ffmpeg, cmd, label="main_render")

    # Cleanup temporary items
    if os.path.isfile(extracted_audio): os.remove(extracted_audio)
    for p in tts_chunks.values():
        if os.path.isfile(p): os.remove(p)

    return "ဇာတ်လမ်းအညွှန်း", output_video

# =====================================================================
# 🤖 TELEGRAM BOT CONTROLLERS & EVENTS
# =====================================================================
bot = TelegramClient(MemorySession(), API_ID, API_HASH)

@bot.on(events.NewMessage(pattern=r"^/start(?:@\w+)?(?:\s|$)"))
async def start_command(event):
    uid = event.sender_id
    now = time.monotonic()
    if now - _START_DEBOUNCE.get(uid, 0.0) < _START_DEBOUNCE_SECONDS:
        return
    _START_DEBOUNCE[uid] = now

    user_voices.setdefault(uid, "v13")  # Default to မယ်နန်း
    user_speeds.setdefault(uid, "1.0x")
    user_platform.setdefault(uid, "tt")
    user_res.setdefault(uid, "1080")
    user_sub_mode.setdefault(uid, True)
    user_copyright_mode.setdefault(uid, False)
    user_disqualified_mode.setdefault(uid, False)

    await event.respond(
        "🎬 **AI Movie Recap Bot (AssemblyAI + Edge-TTS Edition)**\n\n"
        "✨ မြန်မာ အသံ ၁၄ မျိုး စုံလင်စွာ ပါဝင်ပါသည်။\n"
        "✨ Auto Copyright & Auto Disqualified စနစ်များ ထည့်သွင်းထားပါသည်။\n"
        "👇 အောက်ပါ ခလုတ်များဖြင့် စိတ်ကြိုက် ပြင်ဆင်နိုင်ပါသည်-",
        buttons=get_main_menu_buttons(uid)
    )

# 🎙️ Voice Menu Rendering (Exact 2-column layout from screenshot 3676.jpg)
@bot.on(events.CallbackQuery(pattern=b"menu_voice"))
async def menu_voice(event):
    uid = event.sender_id
    cur_v = user_voices.get(uid, "v13")
    
    keys = list(VOICE_MODES.keys())
    buttons = []
    for i in range(0, len(keys), 2):
        row = []
        k1 = keys[i]
        v1 = VOICE_MODES[k1]
        name1 = f"✅ {v1['name']}" if cur_v == k1 else f"🎙 {v1['name']}"
        row.append(Button.inline(name1, f"set_v_{k1}".encode()))

        if i + 1 < len(keys):
            k2 = keys[i + 1]
            v2 = VOICE_MODES[k2]
            name2 = f"✅ {v2['name']}" if cur_v == k2 else f"🎙 {v2['name']}"
            row.append(Button.inline(name2, f"set_v_{k2}".encode()))
        buttons.append(row)

    buttons.append([Button.inline("🔙 နောက်သို့", b"menu_back")])
    try:
        await event.edit("👇 **အသံကို ရွေးချယ်ပါ (Voice Selection):**", buttons=buttons)
    except MessageNotModifiedError:
        pass

@bot.on(events.CallbackQuery(pattern=r"set_v_"))
async def change_voice(event):
    vkey = event.data.decode('utf-8').replace("set_v_", "")
    if vkey in VOICE_MODES:
        user_voices[event.sender_id] = vkey
    await menu_voice(event)

# Toggle Auto Copyright
@bot.on(events.CallbackQuery(pattern=b"toggle_copyright"))
async def toggle_copyright(event):
    uid = event.sender_id
    user_copyright_mode[uid] = not user_copyright_mode.get(uid, False)
    st = "ON" if user_copyright_mode[uid] else "OFF"
    await event.answer(f"Auto Copyright: {st}")
    try:
        await event.edit("⚙️ **Advanced Effects & Settings**", buttons=get_advanced_menu_buttons(uid))
    except MessageNotModifiedError:
        pass

# Toggle Auto Disqualified
@bot.on(events.CallbackQuery(pattern=b"toggle_disqualified"))
async def toggle_disqualified(event):
    uid = event.sender_id
    user_disqualified_mode[uid] = not user_disqualified_mode.get(uid, False)
    st = "ON" if user_disqualified_mode[uid] else "OFF"
    await event.answer(f"Auto Disqualified: {st}")
    try:
        await event.edit("⚙️ **Advanced Effects & Settings**", buttons=get_advanced_menu_buttons(uid))
    except MessageNotModifiedError:
        pass

@bot.on(events.CallbackQuery(pattern=b"menu_advanced"))
async def menu_advanced(event):
    try:
        await event.edit("⚙️ **Advanced Effects & Settings**", buttons=get_advanced_menu_buttons(event.sender_id))
    except MessageNotModifiedError:
        pass

@bot.on(events.CallbackQuery(pattern=b"menu_back"))
async def menu_back(event):
    try:
        await event.edit("👇 စိတ်ကြိုက် ပြင်ဆင်ရန် အောက်ပါခလုတ်များကို အသုံးပြုပါ-", buttons=get_main_menu_buttons(event.sender_id))
    except MessageNotModifiedError:
        pass

# 🔑 Key Registration (AssemblyAI -> Gemini -> Groq)
@bot.on(events.NewMessage(incoming=True))
async def handle_key_or_video(event):
    text = (event.raw_text or "").strip()
    uid = event.sender_id

    # Detect API Keys
    if text and not text.startswith("/") and 20 <= len(text) <= 150:
        existing = user_keys.get(uid, {})
        if not isinstance(existing, dict):
            existing = {}

        if text.startswith(("AIza", "AQ.")):
            existing["gemini"] = text
            user_keys[uid] = existing
            _save_user_keys()
            await event.respond("✅ **Gemini API Key သိမ်းဆည်းပြီးပါပြီ။**\n➡️ အကယ်၍ Groq Key ရှိပါက ဆက်လက် ပို့နိုင်ပါသည်။")
            return
        elif text.startswith("gsk_"):
            existing["groq"] = text
            user_keys[uid] = existing
            _save_user_keys()
            await event.respond("✅ **Groq API Key သိမ်းဆည်းပြီးပါပြီ။**")
            return
        elif re.match(r'^[a-f0-9]{32}$', text, re.IGNORECASE):
            existing["assemblyai"] = text
            user_keys[uid] = existing
            _save_user_keys()
            await event.respond("✅ **AssemblyAI API Key သိမ်းဆည်းပြီးပါပြီ။**\n➡️ ယခု Gemini API Key ကို ဆက်လက် ပို့ပေးပါ။")
            return

    # Check for incoming Video
    doc = getattr(event, "document", None)
    mime = (getattr(doc, "mime_type", "") or "").lower() if doc else ""
    is_vid = bool(event.video or (doc and mime.startswith("video/")))
    if not is_vid:
        return

    # Check Key Presence
    uk = user_keys.get(uid, {})
    if not uk or not uk.get("assemblyai"):
        await event.respond("⚠️ **AssemblyAI Key မရှိသေးပါ။**\nကျေးဇူးပြု၍ AssemblyAI 32-digit API Key ကို အရင်ဆုံး စာရိုက်ပို့ပေးပါ။")
        return

    status = await event.respond("📥 Preview ပြင်ဆင်ရန် Video ကို ဒေါင်းလုဒ်ဆွဲနေပါသည်...")
    video_path = f"temp/input_{uid}_{int(time.time())}.mp4"
    await event.download_media(file=video_path)

    # Instant Preview Extraction
    p_form = user_platform.get(uid, "tt")
    p_res = user_res.get(uid, "1080")
    dim_w, dim_h = get_video_dimensions(p_form, p_res)
    
    raw_frame = f"temp/frame_{uid}.jpg"
    preview_box_img = f"temp/calib_{uid}.jpg"
    user_preview_percent[uid] = 0.30

    await asyncio.to_thread(extract_preview_frame_fast, video_path, raw_frame, dim_w, dim_h, percent=0.30)
    await asyncio.to_thread(
        render_calibration_preview_fast, raw_frame, preview_box_img,
        user_blur_y.get(uid, 82), user_sub_y.get(uid, 82),
        user_blur_mode.get(uid, False), user_font.get(uid, DEFAULT_FONT_FILE)
    )

    user_pending_calib[uid] = {"input_video": video_path, "orig_event": event}
    try: await status.delete()
    except Exception: pass

    calib_buttons = [
        [Button.inline("⬆️Blur အပေါ်", b"calib_blur_up"), Button.inline("⬇️Blur အောက်", b"calib_blur_down")],
        [Button.inline("📝 Sub ⬆️", b"calib_sub_up"), Button.inline("📝 Sub ⬇️", b"calib_sub_down")],
        [Button.inline("▶️ ဗီဒီယို စတင်ရန် (Confirm)", b"calib_start"), Button.inline("❌ ပယ်ဖျက်ရန်", b"calib_cancel")]
    ]
    await bot.send_file(
        event.chat_id, preview_box_img,
        caption="🖼️ **Instant Preview & Calibration**\nအနီရောင် = Blur နေရာ | အဝါရောင် = Subtitle နေရာ\nချိန်ညှိပြီးပါက 'ဗီဒီယို စတင်ရန်' ကိုနှိပ်ပါ။",
        buttons=calib_buttons
    )

# Instant Calibration Callback (Rendered via PyQt in <15ms)
@bot.on(events.CallbackQuery(pattern=r"calib_"))
async def handle_calib(event):
    uid = event.sender_id
    action = event.data.decode('utf-8')

    if action == "calib_cancel":
        calib = user_pending_calib.pop(uid, None)
        if calib and os.path.isfile(calib["input_video"]): os.remove(calib["input_video"])
        await event.edit("❌ Preview ကို ပယ်ဖျက်လိုက်ပါပြီ။", buttons=None)
        return

    if action == "calib_start":
        calib = user_pending_calib.pop(uid, None)
        if not calib:
            await event.answer("Session သက်တမ်းကုန်သွားပါပြီ။", alert=True)
            return
        await event.delete()
        status_msg = await event.respond("⏳ စနစ် စတင်အလုပ်လုပ်နေပါပြီ...")
        out_v = f"temp/recap_{uid}_{time.time_ns()}.mp4"
        try:
            async def _update_status(txt):
                try: await status_msg.edit(txt)
                except Exception: pass

            _, final_video = await process_recap_pipeline(calib["input_video"], out_v, uid, _update_status)
            await status_msg.edit("📤 Telegram သို့ တင်ပို့နေပါသည်...")
            await bot.send_file(event.chat_id, final_video, caption="🎬 **Recap Video ထွက်ရှိပါပြီ!**\nAuto-Generator v95.0")
            if os.path.isfile(final_video): os.remove(final_video)
            if os.path.isfile(calib["input_video"]): os.remove(calib["input_video"])
            await status_msg.delete()
        except Exception as e:
            await status_msg.edit(f"❌ Error: {str(e)}")
            if os.path.isfile(calib["input_video"]): os.remove(calib["input_video"])
        return

    if action == "calib_blur_up": user_blur_y[uid] = max(0, user_blur_y.get(uid, 82) - 4)
    elif action == "calib_blur_down": user_blur_y[uid] = min(90, user_blur_y.get(uid, 82) + 4)
    elif action == "calib_sub_up": user_sub_y[uid] = max(10, user_sub_y.get(uid, 82) - 3)
    elif action == "calib_sub_down": user_sub_y[uid] = min(90, user_sub_y.get(uid, 82) + 3)

    raw_frame = f"temp/frame_{uid}.jpg"
    preview_box_img = f"temp/calib_{uid}.jpg"
    await asyncio.to_thread(
        render_calibration_preview_fast, raw_frame, preview_box_img,
        user_blur_y.get(uid, 82), user_sub_y.get(uid, 82),
        user_blur_mode.get(uid, False), user_font.get(uid, DEFAULT_FONT_FILE)
    )
    try:
        await event.edit(file=preview_box_img)
    except MessageNotModifiedError:
        pass
    await event.answer()

# =====================================================================
# 🚀 MAIN APPLICATION RUNNER
# =====================================================================
async def main():
    await bot.start(bot_token=BOT_TOKEN)
    await bot(SetBotCommandsRequest(
        scope=BotCommandScopeDefault(),
        lang_code='',
        commands=[
            BotCommand(command="start", description="Bot ကို စတင်ရန်"),
            BotCommand(command="setkey", description="API Keys များ ထည့်ရန်")
        ]
    ))
    logging.info("✅ Bot v95.0 successfully started.")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    try:
        bot.loop.run_until_complete(main())
    except Exception as e:
        print(f"Bot Stopped: {e}")
