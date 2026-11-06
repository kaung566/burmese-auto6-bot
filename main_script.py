# =====================================================================
# AI MOVIE RECAP BOT - ENGINE v93.0 (GROQ WHISPER + ADVANCED MENU + PERFECT SYNC)
# =====================================================================

import os
import builtins
import re
import time
import json
import asyncio
import logging
import threading
import subprocess
import sys
import math
import base64
import glob
import urllib.request
import random
import wave
import numpy as np
from typing import List
from concurrent.futures import ThreadPoolExecutor
import itertools
import unicodedata

# =====================================================================
# 📦 AUTO INSTALLER & IMPORTS
# =====================================================================
def auto_install_requirements():
    try:
        import telethon
        import httpx
        import edge_tts
        import yt_dlp
        import nest_asyncio
        from PyQt5.QtWidgets import QApplication
        from google import genai
        import dotenv
    except ImportError:
        print("📦 Colab အတွက် လိုအပ်သော Library များ စတင်သွင်းယူနေပါသည် (ခေတ္တစောင့်ပါ)...")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-q",
            "telethon", "httpx", "edge-tts", "yt-dlp", "nest_asyncio", "PyQt5", "google-genai", "python-dotenv"
        ])
        print("✅ Library များ သွင်းယူပြီးပါပြီ။")

auto_install_requirements()

from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types

import httpx
import nest_asyncio
from telethon import TelegramClient, events, Button
from telethon.sessions import MemorySession
from telethon.errors import MessageNotModifiedError
from telethon.tl.functions.bots import SetBotCommandsRequest
from telethon.tl.types import BotCommand, BotCommandScopeDefault
import edge_tts
import yt_dlp

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QImage, QPainter, QFont, QColor, QFontMetrics, QBrush, QPen, QPainterPath, QFontDatabase, QLinearGradient, QPolygonF, QConicalGradient
from PyQt5.QtCore import Qt, QPointF

_QT_APP = QApplication.instance() or QApplication(sys.argv)
nest_asyncio.apply()
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# =====================================================================
# 🔐 TELEGRAM BOT CONFIGURATION (LICENSE CHECK REMOVED)
# =====================================================================
API_ID = 30921075
API_HASH = "be0dcb53c69af61e86e74938c9ace4a4"

# Set BOT_TOKEN in environment variables, or enter it when prompted.
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    BOT_TOKEN = input("Telegram Bot Token ထည့်ပါ: ").strip()
if not BOT_TOKEN:
    raise SystemExit("❌ Telegram BOT_TOKEN မရှိပါ။")

# License/paid-user verification has been removed; all users can access the bot.
async def verify_telegram_id(user_id):
    return True, ""

# =====================================================================
# ⚙️ VARIABLES & CACHES 
# =====================================================================
user_keys = {}
user_voices, user_speeds, user_stats, job_logs = {}, {}, {}, []
user_platform, user_res, user_sub_mode, user_sub_color = {}, {}, {}, {}
user_title_mode, user_blur_mode, user_blur_y, user_sub_y = {}, {}, {}, {}
# Per-user Blur mask controls: width percentage and extra top/bottom expansion (percentage points)
user_blur_width, user_blur_top_extra, user_blur_bottom_extra = {}, {}, {}
user_pending_calib, user_wm_text, user_wm_pos = {}, {}, {}
user_preview_percent = {}  # selected preview frame position (0.0-1.0)
user_font, user_font_size, user_sub_lang, user_main_lang = {}, {}, {}, {}
user_flip_mode, user_bypass_mode, user_preview_mode = {}, {}, {}
user_multivoice, user_autotrim, user_animsub, user_progressbar = {}, {}, {}, {}
user_video_type = {} 
user_wm_mode = {}
user_translation_style = {}
user_gemini_model = {}
user_gemini_available_models = {}

# Use only the three Gemini models that the user's Burmese GenerateContent
# test reported as successful. Do not probe/test model availability during /setkey.
GEMINI_MODEL_CANDIDATES = (
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
)
GEMINI_MODEL_LABELS = {
    "gemini-3.6-flash": "Gemini 3.6 Flash",
    "gemini-3.5-flash": "Gemini 3.5 Flash",
    "gemini-3.5-flash-lite": "Gemini 3.5 Flash-Lite",
}
user_voice_volume = {}

# Suppress duplicate /start updates received close together in the same running bot process.
_START_DEBOUNCE = {}
_START_DEBOUNCE_SECONDS = 2.0

user_queues = {}
user_queue_active = {}
# Accept many users into per-user queues, but run only a safe number of full
# video jobs at once. Override with MAX_CONCURRENT_JOBS=2 on a larger host.
try:
    MAX_CONCURRENT_JOBS = max(1, min(4, int(os.getenv("MAX_CONCURRENT_JOBS", "1"))))
except (TypeError, ValueError):
    MAX_CONCURRENT_JOBS = 1
GLOBAL_JOB_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
GLOBAL_RENDER_LOCK = asyncio.Semaphore(2)
CURRENT_ACTIVE_USER = ""
ADMIN_ID = API_ID

os.makedirs("temp", exist_ok=True)
AVAILABLE_BGMS = glob.glob("*Chill_Instrumental*.mp3") + glob.glob("*bgm*.mp3") + glob.glob("*Music*.mp3") + glob.glob("/content/bgm.mp3")
DEFAULT_BGM_FILE = AVAILABLE_BGMS[0] if AVAILABLE_BGMS else None

MMS_MODEL = None
MMS_TOKENIZER = None
# Per-user toggle for preserving original audio at the opening before recap narration.
user_original_intro_mode = {}

class GeminiKeyPool:
    def __init__(self, keys_string: str):
        self.groq_keys = []
        try:
            payload = json.loads(str(keys_string))
            if isinstance(payload, dict):
                self.groq_keys = [k.strip() for k in re.split(r"[,\s]+", str(payload.get("groq", "") or "")) if k.strip()]
                keys_string = payload.get("gemini", "")
        except Exception:
            pass
        self.keys = [k.strip() for k in re.split(r"[,\s]+", str(keys_string)) if k.strip()]
        self.groq_key = self.groq_keys[0] if self.groq_keys else ""
        if not self.keys:
            self.keys = load_gemini_keys()
        self.lock = threading.Lock()
        self.idx = 0
        self.dead = set()
        self.preferred_model = "auto"
        self.available_models = None

    def has_keys(self) -> bool:
        return any(k for k in self.keys if k not in self.dead)

    def next_key(self) -> str:
        with self.lock:
            alive = [k for k in self.keys if k not in self.dead]
            if not alive:
                raise RuntimeError("No valid Gemini API keys left.")
            if self.idx >= len(alive):
                self.idx = 0
            k = alive[self.idx]
            self.idx = (self.idx + 1) % len(alive)
            return k

    def mark_dead(self, key: str):
        with self.lock:
            self.dead.add(key)

# =====================================================================
# GEMINI TRANSLATION PROMPT TEMPLATES
# =====================================================================
ORIGINAL_GEMINI_PROMPT_TEMPLATE = """
[SYSTEM INSTRUCTION: You are an expert movie-recap storyteller and translation editor. Translate the supplied lines into {target_voice_lang}.]

STYLE: MOVIE RECAP STORYTELLING, NOT WORD-FOR-WORD TRANSLATION.
- Rewrite the meaning in natural, fluent spoken {target_voice_lang}, suitable for a human voiceover narrator. Keep the story engaging, vivid, emotionally appropriate, and smoothly paced.
- Preserve every important event, character action, cause-and-effect relationship, names, and factual detail. Never invent plot events, dialogue, thoughts, motives, or explanations that are not supported by the source.
- Connect each line naturally to the surrounding story when context supports it. Use transitions equivalent to “at that moment”, “before long”, “but then”, or “it turns out” only when appropriate; do not repeat transition phrases mechanically.
- Correct obvious auto-caption mistakes only when the surrounding story clearly establishes the intended meaning. Do not guess uncertain names or facts.
- Use conversational narration endings and phrasing in Burmese when the target language is Burmese (for example, natural forms such as “ပါတယ်”, “တာပါ”, “သွားခဲ့ပါတယ်”). Avoid stiff, literal, machine-like wording.
- Keep each numbered segment concise enough for its corresponding voiceover timing. Do not merge, omit, reorder, or renumber segments. Do not add headings, notes, explanations, English text, or commentary.
{gender_rule}

OUTPUT FORMAT: Return ONLY the numbered translated lines in this exact format, preserving every original index:
[0] Translated narration
[1] Translated narration

Original lines:
{original_segments_text}
"""

NEW_GEMINI_PROMPT_TEMPLATE = """
### ROLE & OBJECTIVE:
သင်သည် ကျွမ်းကျင်သော မြန်မာ Movie Recap Storyteller နှင့် ဘာသာပြန်တည်းဖြတ်သူဖြစ်သည်။
ပေးထားသော numbered lines များကို Word-for-Word တိုက်ရိုက်မပြန်ဘဲ ဇာတ်လမ်းအဓိပ္ပာယ်မပျက်စေဘဲ သဘာဝကျသော မြန်မာရုပ်ရှင်ဇာတ်ကြောင်းပြောဟန်ဖြင့် ပြန်ရေးပါ။
{gender_rule}

### STYLE RULES — ပါကျဲဘာသာပြန်ပုံစံ:
1. တိုက်ရိုက်စကားလုံးချင်း ဘာသာမပြန်ဘဲ ပရိသတ်ရင်ထဲထိစေမည့် သဘာဝကျသော မြန်မာ Movie Recap ဇာတ်ကြောင်းပြောဟန်ဖြင့် ရေးပါ။ မူရင်းအဓိပ္ပာယ်၊ အဖြစ်အပျက်အစီအစဉ်၊ ဇာတ်ကောင်လုပ်ဆောင်ချက်နှင့် အကြောင်းရင်း/အကျိုးဆက်ကို တိတိကျကျ ထိန်းသိမ်းပါ။
2. ဝါကျများကို အလွန်တိုတိုပြတ်ပြတ် မဖြတ်ပါနှင့်။ သက်ဆိုင်ရာအကြောင်းအရာအလိုက် “အဲဒီအချိန်မှာတော့”၊ “ဒါပေမဲ့”၊ “အဲဒါကြောင့်ပဲ”၊ “သိပ်မကြာခင်မှာပဲ” စသည်တို့ကို သဘာဝကျကျ ချိတ်ဆက်ပါ။ စကားလုံးတစ်မျိုးတည်းကို ထပ်ခါထပ်ခါ မသုံးပါနှင့်။
3. မြန်မာစကားပြောသံဖြင့် ဖတ်ရလွယ်ကူစေပြီး “ခဲ့ပါတယ်”၊ “လိုက်ပါတယ်”၊ “ဖြစ်ပါတယ်”၊ “တာပါ” စသည့် အဆုံးသတ်များကို အခြေအနေနှင့်လိုက်ဖက်အောင် သုံးပါ။ စာသားကို မူရင်းထက် အလွန်တိုအောင် မချုံ့ပါနှင့်။
4. ဇာတ်ရှိန်မြင့်သည့်နေရာတွင် အဓိပ္ပာယ်နှင့်ကိုက်ညီမှသာ “ဘယ်လောက်ပဲ ... ပါစေ၊ ဘယ်လောက်ပဲ ... နေပါစေ” သို့မဟုတ် “...တဲ့သူနဲ့ ...တဲ့သူ” ကဲ့သို့ အလေးပေးပုံစံများ သုံးနိုင်သည်။ အလှဆင်ရန်အတွက်သာ အတင်းမထည့်ပါနှင့်။
5. စွန့်လွှတ်မှု၊ သံယောဇဉ်၊ ဆုံးဖြတ်ချက်နှင့် ခံစားချက်များကို မူရင်းစာသားက ထောက်ခံသည့်အတိုင်းသာ ထင်ရှားစေပါ။ မူရင်းတွင်မပါသော အတွေး၊ ရည်ရွယ်ချက်၊ စကားပြောခန်း၊ ဇာတ်ကွက် သို့မဟုတ် အချက်အလက်ကို လုံးဝမတီထွင်ပါနှင့်။
6. စာကြောင်းနံပါတ်တစ်ခုချင်းစီကို တစ်ခုချင်းစီ ပြန်ဆိုပါ။ နံပါတ်မပေါင်း၊ မဖျက်၊ မပြောင်းပါနှင့်။ ဝါကျတစ်ခုသည် အသံဖတ်ရာတွင် အဓိပ္ပာယ်ပြည့်စုံသည့်နေရာ၌ အဆုံးသတ်စေပြီး နောက်စာကြောင်းကို မတော်တဆ အလယ်ကဖြတ်ဆက်မိသကဲ့သို့ မရေးပါနှင့်။
7. နောက်ဆုံး batch/နောက်ဆုံးစာကြောင်းဖြစ်ကြောင်း ညွှန်ပြထားမှသာ ဇာတ်လမ်းနှင့် အမှန်တကယ်ကိုက်ညီသော အနှစ်ချုပ်ဒဿနကို တိုတိုထည့်နိုင်သည်။ “စွန့်လွှတ်ရဲတဲ့ သတ္တိမျိုး ရှိရဲ့လား” ကဲ့သို့ မေးခွန်းကို ဇာတ်လမ်းက အမှန်တကယ် ထောက်ခံမှသာ သုံးပါ။ အချက်အလက်မတီထွင်ရန် အလှဆင်ဒဿနကို မဖြစ်မနေ မထည့်ပါနှင့်။

### OUTPUT FORMAT:
ဘာသာပြန်ထားသော စာကြောင်းများကိုသာ အောက်ပါပုံစံအတိုင်း ထုတ်ပေးပါ။ ခေါင်းစဉ်၊ ရှင်းလင်းချက်၊ အင်္ဂလိပ်စာ သို့မဟုတ် အခြားမှတ်ချက်များ မထည့်ပါနှင့်။
[0] မြန်မာဇာတ်ကြောင်းပြောစာသား
[1] မြန်မာဇာတ်ကြောင်းပြောစာသား

Original lines:
{original_segments_text}
"""

# =====================================================================
# 🔤 FONT SYSTEM
# =====================================================================
def download_required_fonts():
    fonts_to_dl = {
        "NotoSansJP-Bold.ttf": "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP-Bold.ttf",
        "NotoSansThai-Bold.ttf": "https://github.com/google/fonts/raw/main/ofl/notosansthai/NotoSansThai-Bold.ttf",
        "NotoSansKR-Bold.ttf": "https://github.com/google/fonts/raw/main/ofl/notosanskr/NotoSansKR-Bold.ttf",
        "NotoSansSC-Bold.ttf": "https://github.com/google/fonts/raw/main/ofl/notosanssc/NotoSansSC-Bold.ttf"
    }
    for fname, url in fonts_to_dl.items():
        if not os.path.exists(fname):
            try: urllib.request.urlretrieve(url, fname)
            except Exception: pass

download_required_fonts()

def _register_font(font_path):
    try:
        if os.path.exists(font_path):
            font_id = QFontDatabase.addApplicationFont(font_path)
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families: return families[0]
    except Exception: pass
    return "Arial"

AVAILABLE_FONTS = []
REGISTERED_FONTS = {}
_script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
search_paths = [
    '.', '/content', '/usr/share/fonts/truetype/custom',
    os.path.join(_script_dir, 'Fonts'),
    os.path.join(_script_dir, 'fonts'),
    '/tmp/system_core/Fonts',
]
for path in search_paths:
    for ext in ('*.ttf', '*.otf', '*.TTF', '*.OTF'):
        AVAILABLE_FONTS.extend(glob.glob(os.path.join(path, ext)))

if not AVAILABLE_FONTS:
    _script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else '/content'
    _LOCAL_FONT = os.path.join(_script_dir, "font.ttf")
    if os.path.exists(_LOCAL_FONT): AVAILABLE_FONTS.append(_LOCAL_FONT)
# Register bundled fonts from ZIP; keep all bundled font files available to the app.
for f in set(AVAILABLE_FONTS):
    fam = _register_font(f)
    REGISTERED_FONTS[f] = fam

# Fonts are registered directly from the bundled Fonts/ directory with Qt.
# Do not copy them into /usr/local/share/fonts: hosted containers may be read-only.
# FFmpeg/ASS uses the bundled font directory explicitly where supported.

DEFAULT_FONT_FILE = AVAILABLE_FONTS[0] if AVAILABLE_FONTS else "Arial"
DEFAULT_FONT_FAMILY = REGISTERED_FONTS.get(DEFAULT_FONT_FILE, "Arial")

def get_font_for_language(user_id, lang_code):
    ffile = user_font.get(user_id, DEFAULT_FONT_FILE)
    return REGISTERED_FONTS.get(ffile, DEFAULT_FONT_FAMILY)

# =====================================================================
# 🗣️ VOICE CONFIGURATION
# =====================================================================
VOICE_MODES = {
    "v1":  {"name": "🎙️ မောင်ဘကျော်",        "voice": "my-MM-ThihaNeural",                 "gender": "male",   "rate": "+18%", "pitch": "+0Hz"},
    "v2":  {"name": "🎙️ မယ်ဖွား",              "voice": "my-MM-NilarNeural",                 "gender": "female", "rate": "+18%", "pitch": "+0Hz"},
    "v3":  {"name": "🎙️ မောင်ရွှေရိုး",              "voice": "it-IT-GiuseppeMultilingualNeural",  "gender": "male",   "rate": "+15%", "pitch": "+0Hz"},
    "v4":  {"name": "🎙️ မောင်သာဒင်",         "voice": "en-AU-WilliamMultilingualNeural",   "gender": "male",   "rate": "+15%", "pitch": "+0Hz"},
    "v5":  {"name": "🎙️ ဘိုးထွန်း",           "voice": "en-US-AndrewMultilingualNeural",    "gender": "male",   "rate": "+15%", "pitch": "+0Hz"},
    "v6":  {"name": "🎙️ မယ်သိင်္ဂီ",         "voice": "en-US-AvaMultilingualNeural",       "gender": "female", "rate": "+15%", "pitch": "+0Hz"},
    "v7":  {"name": "🎙️ ဘသောင်း",              "voice": "en-US-BrianMultilingualNeural",     "gender": "male",   "rate": "+15%", "pitch": "+0Hz"},
    "v8":  {"name": "🎙️ မြသီ",          "voice": "en-US-EmmaMultilingualNeural",      "gender": "female", "rate": "+15%", "pitch": "+0Hz"},
    "v9":  {"name": "🎙️ ဘညွန့်",              "voice": "fr-FR-RemyMultilingualNeural",      "gender": "male",   "rate": "+15%", "pitch": "+0Hz"},
    "v10": {"name": "🎙️ မယ်နု",        "voice": "fr-FR-VivienneMultilingualNeural",  "gender": "female", "rate": "+15%", "pitch": "+0Hz"},
    "v11": {"name": "🎙️ မယ်စိန်",            "voice": "de-DE-SeraphinaMultilingualNeural", "gender": "female", "rate": "+15%", "pitch": "+0Hz"},
    "v12": {"name": "🎙️ ပိုးထောင်",             "voice": "de-DE-FlorianMultilingualNeural",   "gender": "male",   "rate": "+15%", "pitch": "+0Hz"},
    "v13": {"name": "🎙️ မယ်နန်း",         "voice": "pt-BR-ThalitaMultilingualNeural",   "gender": "female", "rate": "+15%", "pitch": "+0Hz"},
    "v14": {"name": "🎙️ ကျော်စွာ",          "voice": "ko-KR-HyunsuMultilingualNeural",    "gender": "male",   "rate": "+15%", "pitch": "+0Hz"},
}

SPEED_MULTIPLIERS = {"1.0x": 1.0, "1.1x": 1.1, "1.2x": 1.2, "1.3x": 1.3, "1.4x": 1.4}

# =====================================================================
# 🎛️ MENU LAYOUTS (Fully Dynamic On/Off Toggles)
# =====================================================================
def get_main_menu_buttons(user_id):
    wm_btn = "✅ Watermark" if user_wm_mode.get(user_id, True) else "❌ Watermark"
    pv_btn = "✅ Preview Mode" if user_preview_mode.get(user_id, True) else "❌ Preview Mode"
    sub_btn = "✅ စာတန်းထိုး (Sub)" if user_sub_mode.get(user_id, True) else "❌ စာတန်းထိုး (Sub)"
    title_btn = "✅ Title (ခေါင်းစဉ်)" if user_title_mode.get(user_id, True) else "❌ Title (ခေါင်းစဉ်)"
    
    return [
        [Button.inline("📱 ဗီဒီယို ဆိုဒ်", b"menu_size"), Button.inline("📺 Resolution", b"menu_res")],
        [Button.inline("🎙️ အသံ (Voice)", b"menu_voice"), Button.inline("⚡ အမြန်နှုန်း (Speed)", b"menu_speed")],
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
    flip_btn = "✅ Video Flip" if user_flip_mode.get(user_id, False) else "❌ Video Flip"
    bypass_btn = "✅ Auto Bypass" if user_bypass_mode.get(user_id, False) else "❌ Auto Bypass"
    multi_btn = "✅ Multi-Voice" if user_multivoice.get(user_id, False) else "❌ Multi-Voice"
    prog_btn = "✅ Progress Bar" if user_progressbar.get(user_id, False) else "❌ Progress Bar"

    return [
        [Button.inline(trim_btn, b"menu_autotrim"), Button.inline(anim_btn, b"menu_animsub")],
        [Button.inline(blur_btn, b"menu_blur"), Button.inline(flip_btn, b"menu_flip")],
        [Button.inline(bypass_btn, b"menu_bypass"), Button.inline("🌐 Sub Lang", b"menu_sublang")],
        [Button.inline("🌍 Int'l Mode", b"menu_intl"), Button.inline(multi_btn, b"menu_multivoice")],
        [Button.inline(prog_btn, b"menu_progressbar"), Button.inline("🎞️ Vid Type (Movie/Series)", b"menu_vidtype")],
        [Button.inline("🔙 ပင်မစာမျက်နှာသို့ (Back)", b"menu_back")]
    ]

SUB_LANGUAGES = {
    "my": "မြန်မာ (Burmese)", 
    "en": "English", 
    "my_en": "မြန်မာ + English (Dual)",
    "th": "ไทย (Thai)",
    "zh": "中文 (Chinese)", 
    "ja": "日本語 (Japanese)", 
    "ko": "한국어 (Korean)", 
    "id": "Bahasa Indonesia",
}

SUB_COLOR_CHOICES = [
    ("yellow", "အဝါရောင် (Yellow)"), ("white", "အဖြူရောင် (White)"), ("#00FFFF", "စိမ်းပြာ (Cyan)"), 
    ("#39FF14", "စိမ်းစို (Lime)"), ("#FF69B4", "ပန်းရောင် (Hot Pink)"), ("#FFA500", "လိမ္မော်ရောင် (Orange)"),
    ("#FF0000", "အနီရောင် (Red)"), ("#ADD8E6", "ကောင်းကင်ပြာ (Light Blue)"), ("#FFD700", "ရွှေဝါရောင် (Gold)"),
    ("#FF00FF", "ခရမ်းရောင် (Magenta)")
]

FONT_SIZE_CHOICES = [
    (12, "12"), (14, "14"), (16, "16"), (18, "18"), (20, "20"),
    (24, "24"), (28, "28"), (32, "32"), (35, "35 (Default)"), (40, "40"),
    (45, "45"), (50, "50"),
]

# =====================================================================
# 🎬 FFmpeg UTILS
# =====================================================================
def get_best_video_encoder():
    try:
        test_cmd = ['ffmpeg', '-y', '-hide_banner', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=640x480:r=30:d=1', '-frames:v', '1', '-c:v', 'h264_nvenc', '-preset', 'p4', '-pix_fmt', 'yuv420p', '-f', 'null', '-']
        result = subprocess.run(test_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            return 'h264_nvenc'
    except Exception: pass
    return 'libx264'

FFMPEG_ENCODER = get_best_video_encoder()

def video_encoder_args(preset="medium", quality=28):
    """Use NVIDIA NVENC when available; otherwise use a compatible CPU encoder."""
    if FFMPEG_ENCODER == "h264_nvenc":
        # NVENC uses p1-p7 presets and CQ rather than x264 CRF.
        nv_preset = {"ultrafast": "p1", "fast": "p3", "medium": "p4", "slow": "p5"}.get(preset, "p4")
        return ["-c:v", "h264_nvenc", "-preset", nv_preset, "-rc", "vbr", "-cq", str(quality), "-b:v", "0"]
    return ["-c:v", "libx264", "-preset", preset, "-crf", str(quality)]

def run_health_check_server():
    from http.server import BaseHTTPRequestHandler, HTTPServer
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK - Telegram bot is running.")
        def log_message(self, format, *args): return
    port = int(os.environ.get("PORT", 7860))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        server.serve_forever()
    except OSError as e:
        if e.errno == 98: pass
        else: raise e

def run_ffmpeg(cmd, label="ffmpeg"):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        tail = (result.stderr or "").strip()
        tail = tail[-800:] if len(tail) > 800 else tail
        raise RuntimeError(f"FFmpeg Error [{label}] (exit {result.returncode}):\n{tail}")
    return result

def extract_audio_ffmpeg(video_path, audio_path):
    run_ffmpeg(['ffmpeg', '-y', '-i', video_path, '-vn', '-c:a', 'libmp3lame', '-b:a', '32k', '-ar', '16000', '-ac', '1', audio_path], label="extract_audio")

def is_youtube_link(url): return bool(re.search(r'(youtube\.com|youtu\.be)', url, re.IGNORECASE))

def download_youtube_video(url, output_path):
    """Fetch a small, low-resolution opening segment for calibration preview only."""
    ydl_opts = {
        'format': 'best[height<=480][ext=mp4]/best[height<=480]/best[ext=mp4]/best',
        'outtmpl': output_path,
        'quiet': True, 'no_warnings': True,
        'download_sections': {'*': '0-35'},
        'force_keyframes_at_cuts': True,
        'merge_output_format': 'mp4',
        'retries': 3, 'fragment_retries': 3,
        'socket_timeout': 20,
        'concurrent_fragment_downloads': 4,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

def get_media_duration(file_path):
    """Read duration robustly from format or streams (TS chunks may omit format.duration)."""
    res = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=duration', '-of', 'json', file_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
    )
    data = json.loads(res.stdout or '{}')
    fmt = (data.get('format') or {}).get('duration')
    if fmt not in (None, '', 'N/A'):
        value = float(fmt)
        if value > 0: return value
    stream_values = []
    for stream in data.get('streams') or []:
        value = stream.get('duration')
        if value not in (None, '', 'N/A'):
            try:
                value = float(value)
                if value > 0: stream_values.append(value)
            except (TypeError, ValueError):
                pass
        # Some MPEG-TS/fragmented outputs omit stream.duration but expose duration_ts/time_base.
        try:
            ticks = stream.get('duration_ts')
            time_base = stream.get('time_base')
            if ticks not in (None, '', 'N/A') and time_base:
                num, den = str(time_base).split('/', 1)
                derived = float(ticks) * float(num) / float(den)
                if derived > 0: stream_values.append(derived)
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    if stream_values:
        return max(stream_values)
    # Last-resort container probe; handles files whose stream metadata is incomplete.
    fallback = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    try:
        value = float((fallback.stdout or '').strip())
        if value > 0: return value
    except (TypeError, ValueError):
        pass
    raise ValueError(f"ffprobe duration မတွေ့ပါ: {file_path}")

def create_silent_audio(duration, output_path):
    run_ffmpeg(['ffmpeg', '-y', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo', '-t', str(max(duration, 0.1)), '-c:a', 'libmp3lame', '-b:a', '128k', output_path], label="silent_audio")

def get_video_dimensions(platform, res):
    if platform == "tt": return (720, 1280) if res == "720" else (1080, 1920)
    elif platform == "fb": return (720, 720) if res == "720" else (1080, 1080)
    return (1280, 720) if res == "720" else (1920, 1080)

def detect_content_crop(video_path, sample_seconds=8):
    try: dur = get_media_duration(video_path)
    except Exception: dur = sample_seconds + 1.0
    ss = max(0.0, dur * 0.15)
    t = min(sample_seconds, max(dur - ss - 0.2, 1.0))
    cmd = ['ffmpeg', '-ss', f"{ss:.2f}", '-t', f"{t:.2f}", '-i', video_path, '-vf', 'cropdetect=24:16:0', '-f', 'null', '-']
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    crops = re.findall(r'crop=(\d+):(\d+):(\d+):(\d+)', result.stderr or "")
    if not crops: return None
    w, h, x, y = (int(v) for v in crops[-1])
    if w <= 0 or h <= 0: return None
    return w, h, x, y

def apply_content_crop_if_needed(video_path, job_tag):
    try:
        crop = detect_content_crop(video_path)
        if not crop: return video_path
        cw, ch, cx, cy = crop
        probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'json', video_path], stdout=subprocess.PIPE, text=True)
        dims = json.loads(probe.stdout)['streams'][0]
        src_w, src_h = dims['width'], dims['height']
        if cw >= src_w * 0.97 and ch >= src_h * 0.97: return video_path
        cropped_path = f"temp/crop_{job_tag}_{int(time.time())}.mp4"
        cmd = ['ffmpeg', '-y', '-i', video_path, '-vf', f'crop={cw}:{ch}:{cx}:{cy}', '-map_metadata', '-1', '-c:a', 'copy', cropped_path]
        run_ffmpeg(cmd, label="content_crop")
        return cropped_path
    except Exception: return video_path

def get_blur_mask_filter(current_video_label="[0:v]", y_position_percent=82, border_thick=0,
                         width_percent=100, top_extra=0, bottom_extra=0):
    # Blur rectangle is horizontally centered; the top/bottom buttons expand the mask
    # in the selected direction. Keep all values bounded to avoid out-of-frame crops.
    y_position_percent = max(0, min(88, float(y_position_percent)))
    width_percent = max(10, min(100, float(width_percent)))
    top_extra = max(-10, min(30, float(top_extra)))
    bottom_extra = max(-10, min(30, float(bottom_extra)))
    height_percent = max(2, min(70, 12 + top_extra + bottom_extra))
    y_position_percent = min(y_position_percent, 100 - height_percent)
    x_percent = (100 - width_percent) / 2.0
    crop_x = f"iw*({x_percent}/100.0)"
    crop_y = f"ih*({y_position_percent}/100.0)"
    crop_w = f"iw*({width_percent}/100.0)"
    crop_h = f"ih*({height_percent}/100.0)"
    overlay_x = f"W*({x_percent}/100.0)"
    overlay_y = f"H*({y_position_percent}/100.0)"
    filter_string = f"{current_video_label}split=2[orig_for_blur][blur_crop];"
    filter_string += f"[blur_crop]crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale=iw/4:ih/4,boxblur=5:2,scale=iw*4:ih*4:flags=fast_bilinear[blurred_bot];"
    filter_string += f"[orig_for_blur][blurred_bot]overlay={overlay_x}:{overlay_y}[vid_sub_blurred]"
    return filter_string, "[vid_sub_blurred]"

def extract_preview_frame(video_path, out_path, dim_w, dim_h, percent=0.3):
    dim_w = int(dim_w); dim_w = dim_w if dim_w % 2 == 0 else dim_w + 1
    dim_h = int(dim_h); dim_h = dim_h if dim_h % 2 == 0 else dim_h + 1
    try: dur = get_media_duration(video_path)
    except Exception: dur = 3.0
    ts = min(max(dur * percent, 0.3), max(dur - 0.3, 0.3))
    run_ffmpeg(['ffmpeg', '-y', '-ss', f"{ts:.2f}", '-i', video_path, '-frames:v', '1', '-vf', f"scale={dim_w}:{dim_h}:force_original_aspect_ratio=decrease,pad={dim_w}:{dim_h}:-1:-1:color=black", out_path], label="preview_frame")

def render_calibration_preview(frame_path, out_path, blur_y, sub_y, blur_on, font_path=None,
                               blur_width=100, blur_top_extra=0, blur_bottom_extra=0):
    parts = []
    if blur_on:
        width_pct = max(10, min(100, float(blur_width)))
        top_extra = max(-10, min(30, float(blur_top_extra)))
        bottom_extra = max(-10, min(30, float(blur_bottom_extra)))
        height_pct = max(2, min(70, 12 + top_extra + bottom_extra))
        y_pct = min(max(0, float(blur_y)), 100 - height_pct)
        x_pct = (100 - width_pct) / 2.0
        parts.append(f"drawbox=x=iw*({x_pct}/100.0):y=ih*({y_pct}/100.0):w=iw*({width_pct}/100.0):h=ih*({height_pct}/100.0):color=red@0.45:t=fill")
    parts.append(f"drawbox=x=0:y=ih*({sub_y}/100.0):w=iw:h=ih*0.10:color=yellow@0.45:t=fill")
    
    if font_path and os.path.exists(font_path):
        safe_font = os.path.abspath(font_path).replace('\\', '/').replace(':', '\\:')
        text_y = f"h*({sub_y}/100.0)+(h*0.10-th)/2"
        parts.append(f"drawtext=fontfile='{safe_font}':text='စာတန်းထိုးချိန်ရန်':fontcolor=white:fontsize=40:x=(w-tw)/2:y={text_y}")
        
    run_ffmpeg(['ffmpeg', '-y', '-i', frame_path, '-vf', ",".join(parts), out_path], label="calibration_preview")

_MY_COMBINING = set("\u102B\u102C\u102D\u102E\u102F\u1030\u1031\u1032\u1033\u1034\u1035\u1036\u1037\u1038\u1039\u103A\u103B\u103C\u103D\u103E\u103F\u1060\u1061\u1062\u1063\u1064\u1065\u1066\u1067\u1068\u1069")
_MY_ASAT = '\u103A'; _MY_VIRAMA = '\u1039'; _MY_BREAK_CHARS = set(' \t\n\u200b၊။!?.,;:()[]{}"\'')

def _burmese_syllable_clusters(text):
    clusters = []; cur = ""; n = len(text); i = 0
    while i < n:
        ch = text[i]
        if not cur: cur = ch; i += 1; continue
        if ch in _MY_COMBINING or cur[-1] == _MY_VIRAMA: cur += ch; i += 1; continue
        if (i + 1 < n and text[i + 1] == _MY_ASAT and cur[-1] not in _MY_BREAK_CHARS): cur += ch; i += 1; continue
        clusters.append(cur); cur = ch; i += 1
    if cur: clusters.append(cur)
    return clusters

def _fit_title_font_size(painter, font_fam, text, box_w, box_h, max_pt=75, min_pt=35):
    for pt in range(max_pt, min_pt - 1, -2):
        font = QFont(font_fam, pt, QFont.Black); font.setStyleHint(QFont.SansSerif)
        fm = QFontMetrics(font)
        if fm.horizontalAdvance(text) <= box_w and fm.height() <= box_h: 
            return pt
    return min_pt

def _draw_hook_title(painter, font_fam, text, box_x, box_y, box_w, box_h, max_pt=75, min_pt=35):
    clean_title = text.strip().replace("\n", " ")
    if len(clean_title) > 15:
        clean_title = clean_title[:15]
        
    fit_pt = _fit_title_font_size(painter, font_fam, clean_title, box_w, box_h, max_pt=max_pt, min_pt=min_pt)
    font = QFont(font_fam, fit_pt, QFont.Black); font.setStyleHint(QFont.SansSerif)
    fm = QFontMetrics(font)
    
    line_w = fm.horizontalAdvance(clean_title)
    line_x = box_x + int((box_w - line_w) / 2)
    cur_y = box_y + max(0, (box_h - fm.height()) // 2) + fm.ascent()
    
    path = QPainterPath()
    path.addText(float(line_x), float(cur_y), font, clean_title)
    path.setFillRule(Qt.WindingFill)
    
    # Thumbnail title: bright yellow fill with a clear black outline.
    grad = QLinearGradient(line_x, box_y, line_x, box_y + fm.height())
    grad.setColorAt(0.0, QColor("#FFF36A"))
    grad.setColorAt(1.0, QColor("#FFD700"))
    
    outline_w = max(5, int(fit_pt * 0.12))
    painter.setPen(QPen(QColor(0, 0, 0, 255), outline_w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(path)
    
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(grad))
    painter.drawPath(path)

    underline_h = max(6, int(fit_pt * 0.08))
    underline_y = box_y + fm.height() + int(fm.height() * 0.15)
    painter.setPen(QPen(QColor(0, 0, 0, 255), outline_w // 2, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin))
    painter.setBrush(QBrush(QColor("#FFD700")))
    painter.drawRect(line_x, underline_y, line_w, underline_h)

def extract_best_frame(video_path, out_path, dim_w=None, dim_h=None, crop_square=False, search_seconds=25, center_time=None):
    dim_w = int(dim_w) if dim_w else None
    dim_h = int(dim_h) if dim_h else None
    if dim_w is not None: dim_w = dim_w if dim_w % 2 == 0 else dim_w + 1
    if dim_h is not None: dim_h = dim_h if dim_h % 2 == 0 else dim_h + 1
    try: dur = get_media_duration(video_path)
    except Exception: dur = 10.0
    if center_time is not None:
        half = search_seconds / 2.0; window_start = max(min(center_time - half, dur - 1.0), 0.0); window_len = min(search_seconds, max(dur - window_start - 0.2, 1.0))
    else:
        window_start = max(dur * 0.15, 0.5); window_len = min(search_seconds, max(dur - window_start - 0.5, 1.0))

    vf_parts = [f"thumbnail={max(int(window_len * 24), 25)}"]
    if crop_square:
        vf_parts.append("crop='min(iw,ih)':'min(iw,ih)'")
        if dim_w and dim_h: vf_parts.append(f"scale={dim_w}:{dim_h}")
    else:
        if dim_w and dim_h:
            vf_parts = [f"thumbnail={max(int(window_len * 24), 25)}", f"split=2[__bg][__fg]"]
            filter_complex = f"{','.join(vf_parts)};[__bg]scale={dim_w}:{dim_h}:force_original_aspect_ratio=increase,crop={dim_w}:{dim_h},boxblur=18:4,eq=brightness=-0.05[__bgblur];[__fg]scale={dim_w}:{dim_h}:force_original_aspect_ratio=decrease[__fgs];[__bgblur][__fgs]overlay=(W-w)/2:(H-h)/2"
            try: run_ffmpeg(['ffmpeg', '-y', '-ss', f"{window_start:.2f}", '-t', f"{window_len:.2f}", '-i', video_path, '-filter_complex', filter_complex, '-frames:v', '1', out_path], label="best_frame"); return
            except Exception: pass
    try: run_ffmpeg(['ffmpeg', '-y', '-ss', f"{window_start:.2f}", '-t', f"{window_len:.2f}", '-i', video_path, '-vf', ",".join(vf_parts), '-frames:v', '1', out_path], label="best_frame")
    except Exception:
        ts = center_time if center_time is not None else dur * 0.3
        cmd2 = ['ffmpeg', '-y', '-ss', f"{ts:.2f}", '-i', video_path, '-frames:v', '1']
        run_ffmpeg(cmd2 + [out_path], label="best_frame_fallback")

def draw_custom_arrow(painter, start_point, end_point, color="#FFFFFF", thickness=35, head_size=80):
    painter.setPen(QPen(QColor(0, 0, 0, 150), thickness + 8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    path = QPainterPath(start_point)
    dx = end_point.x() - start_point.x(); dy = end_point.y() - start_point.y()
    cx = start_point.x() + dx / 2 - dy * 0.25; cy = start_point.y() + dy / 2 + dx * 0.25
    path.quadTo(QPointF(cx, cy), end_point)
    painter.drawPath(path)
    
    painter.setPen(QPen(QColor(color), thickness, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.drawPath(path)

    angle = math.atan2(end_point.y() - cy, end_point.x() - cx)
    p1 = QPointF(end_point.x() - head_size * math.cos(angle - math.pi / 7), end_point.y() - head_size * math.sin(angle - math.pi / 7))
    p2 = QPointF(end_point.x() - head_size * math.cos(angle + math.pi / 7), end_point.y() - head_size * math.sin(angle + math.pi / 7))
    
    painter.setBrush(QColor(0, 0, 0, 150))
    painter.setPen(Qt.NoPen)
    painter.drawPolygon(QPolygonF([QPointF(end_point.x()+4, end_point.y()+4), QPointF(p1.x()+4, p1.y()+4), QPointF(p2.x()+4, p2.y()+4)]))
    
    painter.setBrush(QColor(color))
    painter.drawPolygon(QPolygonF([end_point, p1, p2]))

def _try_generate_ai_poster(video_path, out_path, api_keys):
    """Generate the poster ONLY with the image model, using two frames from the uploaded video.
    No local-frame/design fallback is allowed: return False if AI generation fails.
    """
    temp_paths = []
    try:
        raw_keys = str(api_keys or "").strip()
        try:
            payload = json.loads(raw_keys)
            if isinstance(payload, dict):
                raw_keys = str(payload.get("gemini", "") or "")
        except Exception:
            pass
        keys = [k.strip() for k in re.split(r"[,;\s]+", raw_keys) if k.strip().startswith(("AIza", "AQ."))]
        if not keys:
            logging.error("AI thumbnail generation stopped: no Gemini image-generation key is configured.")
            return False

        try:
            duration = float(get_media_duration(video_path))
        except Exception:
            duration = 60.0
        # Pick two separated moments so the model can compose a coherent two-scene poster.
        t1 = max(0.5, min(duration * 0.22, max(0.5, duration - 1.0)))
        t2 = max(0.5, min(duration * 0.72, max(0.5, duration - 0.5)))
        frame1 = "temp/ai_poster_scene_1.jpg"
        frame2 = "temp/ai_poster_scene_2.jpg"
        temp_paths.extend([frame1, frame2])
        extract_best_frame(video_path, frame1, dim_w=768, dim_h=1365, crop_square=False, center_time=t1, search_seconds=8)
        extract_best_frame(video_path, frame2, dim_w=768, dim_h=1365, crop_square=False, center_time=t2, search_seconds=8)
        if any(not os.path.isfile(p) or os.path.getsize(p) < 1000 for p in temp_paths):
            logging.error("AI thumbnail generation stopped: could not extract both reference scenes.")
            return False
        with open(frame1, "rb") as f:
            frame1_bytes = f.read()
        with open(frame2, "rb") as f:
            frame2_bytes = f.read()

        prompt = (
            "Generate ONE finished cinematic 9:16 vertical movie poster image, using BOTH supplied images as the only visual references. "
            "Image 1 is the upper-scene reference: create a powerful close-up/hero moment based on its actual characters. "
            "Image 2 is the lower-scene reference: create a second dramatic action, reaction, or confrontation moment from the same video. "
            "Blend both scenes into a single cohesive premium movie-poster composition, not a plain two-panel split and not a small inset. "
            "Separate the scenes with a dramatic torn-paper/ripped jagged edge, cinematic sparks and directional light streaks. "
            "Keep the people, faces, clothing, vehicles, setting and story consistent with the reference images; do not substitute unrelated people or invent an unrelated scene. "
            "Use realistic cinematic photography, strong visual hierarchy, warm gold with restrained red highlights, dark readable central/lower negative space for a Burmese title to be added later, and a thin muted-gold border. "
            "Do not render any text, letters, logos, watermarks, captions, title, or typography. Output the poster image only."
        )
        for key in keys:
            try:
                client = genai.Client(api_key=key)
                response = client.models.generate_content(
                    model="gemini-2.5-flash-image",
                    contents=[prompt,
                              types.Part.from_bytes(data=frame1_bytes, mime_type="image/jpeg"),
                              types.Part.from_bytes(data=frame2_bytes, mime_type="image/jpeg")],
                    config=types.GenerateContentConfig(temperature=0.4)
                )
                for candidate in (getattr(response, "candidates", None) or []):
                    content = getattr(candidate, "content", None)
                    for part in (getattr(content, "parts", None) or []):
                        inline = getattr(part, "inline_data", None)
                        data = getattr(inline, "data", None) if inline else None
                        if data:
                            with open(out_path, "wb") as f:
                                f.write(data)
                            if os.path.isfile(out_path) and os.path.getsize(out_path) > 10000:
                                return True
                logging.warning("AI thumbnail model returned no image for one Gemini key; trying next key.")
            except Exception as e:
                logging.warning("AI thumbnail key attempt failed: %s", str(e)[:220])
        return False
    except Exception as e:
        logging.warning("AI-only poster generation failed: %s", str(e)[:220])
        return False
    finally:
        for p in temp_paths:
            try:
                if os.path.exists(p): os.remove(p)
            except Exception:
                pass


def create_thumbnail(video_path, title_text, out_path, font_fam, w=960, h=1706, platform="yt", highlight_time=None, gemini_keys=""):
    """AI-assisted cinematic vertical poster: dominant hero on right, story scene on left, Burmese title panel bottom-left."""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    bg_path = f"temp/tb_bg_{int(time.time()*1000)}.jpg"
    # AI-ONLY mode: the poster background must be generated by Gemini from two
    # separate reference scenes. Never silently substitute a plain video frame.
    if not _try_generate_ai_poster(video_path, bg_path, gemini_keys):
        raise RuntimeError(
            "AI Thumbnail မထုတ်နိုင်ပါ။ Gemini Image model quota/API key/model access ကိုစစ်ပါ။ "
            "AI ပုံမရလျှင် video frame ကို အစားထိုးမသုံးပါ။"
        )

    img = QImage(w, h, QImage.Format_ARGB32)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)

    if os.path.exists(bg_path):
        background = QImage(bg_path)
        if not background.isNull():
            painter.drawImage(0, 0, background.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        else:
            img.fill(QColor("#171717"))
    else:
        img.fill(QColor("#171717"))

    # Darken the center/lower area for bold, readable Burmese title text.
    painter.fillRect(0, int(h*0.42), w, int(h*0.58), QColor(0, 0, 0, 82))

    # Wide angular center title plate, inspired by the requested cinematic poster reference.
    panel_x, panel_y = int(w*0.045), int(h*0.52)
    panel_w, panel_h = int(w*0.91), int(h*0.30)
    cut = int(w*0.12)
    panel_path = QPainterPath()
    panel_path.moveTo(panel_x, panel_y)
    panel_path.lineTo(panel_x + panel_w - cut, panel_y)
    panel_path.lineTo(panel_x + panel_w, panel_y + int(panel_h*0.16))
    panel_path.lineTo(panel_x + panel_w, panel_y + panel_h)
    panel_path.lineTo(panel_x, panel_y + panel_h)
    panel_path.closeSubpath()
    painter.setPen(QPen(QColor("#C7A77A"), max(3, int(w*0.005))))
    painter.setBrush(QColor(15, 12, 10, 224))
    painter.drawPath(panel_path)

    title_margin = int(w*0.045)
    title_text = (title_text or "Movie Recap").strip()
    _draw_hook_title(
        painter, font_fam, title_text,
        panel_x + title_margin, panel_y + int(panel_h*0.07),
        panel_w - title_margin*2, int(panel_h*0.84),
        max_pt=max(42, int(w*0.075)), min_pt=max(25, int(w*0.04))
    )

    # Thin warm-gold frame; deliberately no "MOVIE RECAP" badge.
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QColor("#D8C5A5"), max(2, int(w*0.004))))
    painter.drawRect(int(w*0.018), int(h*0.012), int(w*0.964), int(h*0.976))
    painter.end()
    img.save(out_path, "JPEG", quality=95)
    try:
        if os.path.exists(bg_path):
            os.remove(bg_path)
    except Exception:
        pass

def build_audio_routing_plan(timeline_data, recap_dict=None, hybrid_mode=True):
    """Route Whisper speech intervals to recap VO and all non-speech intervals
    to the untouched original soundtrack. In hybrid mode, speech is always
    replaced by recap narration; silence/non-speech is never narrated.
    """
    recap_dict = recap_dict or {}
    plan = []
    for idx, seg in enumerate(timeline_data):
        is_speech = bool(seg.get("is_speech"))
        text = recap_dict.get(idx, "") if hybrid_mode and is_speech else ""
        source = "recap" if hybrid_mode and is_speech and isinstance(text, str) and text.strip() else "original"
        plan.append({"index": idx, "start": float(seg.get("start", 0.0)),
                     "end": float(seg.get("end", 0.0)), "source": source,
                     "recap_text": text.strip() if source == "recap" else ""})
    return plan

def gemini_model_order(preferred="auto", available=None):
    """Preferred model first, then other models verified for this user's key."""
    allowed = list(GEMINI_MODEL_CANDIDATES) if available is None else list(available)
    allowed = [m for m in allowed if m in GEMINI_MODEL_CANDIDATES]
    if preferred and preferred != "auto" and preferred in allowed:
        return [preferred] + [m for m in allowed if m != preferred]
    return allowed


def _new_gemini_client(api_key):
    """Create a Gemini client with a finite HTTP timeout where supported."""
    try:
        return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=20000))
    except Exception:
        return genai.Client(api_key=api_key)


async def _gemini_request_with_retry(client, model_name, prompt, config, attempts=4):
    """Retry transient Gemini failures (503/network/timeout) at 2/4/8 seconds.

    Invalid-model/404 and quota/429 errors are surfaced immediately so the
    caller can move to its configured fallback model or key.
    """
    delays = (2, 4, 8)
    last_error = None
    for attempt in range(min(max(int(attempts), 1), 4)):
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(client.models.generate_content,
                                  model=model_name, contents=prompt, config=config),
                timeout=25.0
            )
        except Exception as exc:
            last_error = exc
            low = "timeout" if isinstance(exc, asyncio.TimeoutError) else str(exc).lower()
            if any(token in low for token in ("404", "not found", "invalid_argument", "model not found")):
                raise
            if any(token in low for token in ("429", "quota", "resource_exhausted")):
                raise
            transient = any(token in low for token in ("503", "unavailable", "timeout", "timed out", "connection", "network", "temporarily"))
            if not transient or attempt >= min(max(int(attempts), 1), 4) - 1:
                raise
            await asyncio.sleep(delays[attempt])
    raise last_error

def build_complete_timeline(segments_data, total_duration, max_dur=20.0, max_gap=5.0):
    if not segments_data: return [{"start": 0.0, "end": total_duration, "text": "", "is_speech": False}]
    
    merged_speech = []
    curr_text = ""
    curr_start = float(segments_data[0]["start"])
    curr_end = float(segments_data[0]["end"])
    
    for i in range(1, len(segments_data)):
        seg = segments_data[i]
        seg_start = float(seg["start"])
        seg_end = float(seg["end"])
        seg_text = seg["text"].strip()
        gap = seg_start - curr_end
        
        if gap > max_gap or (seg_end - curr_start) > max_dur:
            if curr_text.strip(): 
                merged_speech.append({"start": curr_start, "end": curr_end, "text": curr_text.strip(), "is_speech": True})
            curr_start = seg_start
            curr_end = seg_end
            curr_text = seg_text
        else:
            curr_text = (curr_text + " " + seg_text).strip() if curr_text else seg_text
            curr_end = seg_end
            
    if curr_text.strip(): 
        merged_speech.append({"start": curr_start, "end": curr_end, "text": curr_text.strip(), "is_speech": True})
    
    full_timeline = []
    current_time = 0.0
    for seg in merged_speech:
        if seg["start"] > current_time:
            full_timeline.append({"start": current_time, "end": seg["start"], "text": "", "is_speech": False})
        full_timeline.append(seg)
        current_time = seg["end"]
    
    if current_time < total_duration:
        full_timeline.append({"start": current_time, "end": total_duration, "text": "", "is_speech": False})
        
    return full_timeline

def format_ass_time(seconds):
    h = int(seconds // 3600); m = int((seconds % 3600) // 60); s = int(seconds % 60); cs = int(round((seconds % 1) * 100))
    if cs >= 100: cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def _format_srt_time(seconds):
    """Format non-negative seconds as a valid SRT timestamp."""
    ms = max(0, int(round(float(seconds) * 1000)))
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def generate_subtitle_srt_file(segments, output_path):
    """Write the same unified, final-render timeline used by ASS subtitles."""
    ordered = sorted((x for x in segments if str(x.get("text", "")).strip()),
                     key=lambda x: (float(x.get("start", 0)), float(x.get("end", 0))))
    with open(output_path, "w", encoding="utf-8") as f:
        cue = 0
        previous_end = 0.0
        for seg in ordered:
            start = max(float(seg.get("start", 0)), previous_end)
            end = max(float(seg.get("end", 0)), start + 0.05)
            if end <= start:
                continue
            cue += 1
            text = unicodedata.normalize("NFC", str(seg.get("text", "")))
            text = text.replace("\\N", "\n").replace("\r", "")
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r" *\n *", "\n", text).strip()
            f.write(f"{cue}\n{_format_srt_time(start)} --> {_format_srt_time(end)}\n{text}\n\n")
            previous_end = end
    return output_path

def generate_subtitle_ass_file(json_path, job_dir, TW=1080, TH=1920, sub_y_percent=82, sub_color="yellow", font_fam="Arial", font_size=35, sub_lang="my", anim_sub=False):
    with open(json_path, "r", encoding="utf-8") as f: segments = json.load(f)

    ass_color_mapped = "00FFFF"
    if sub_color == "yellow": ass_color_mapped = "00FFFF"
    elif sub_color == "white": ass_color_mapped = "FFFFFF"
    elif sub_color.startswith("#") and len(sub_color) == 7:
        hx = sub_color.lstrip('#')
        ass_color_mapped = hx[4:6] + hx[2:4] + hx[0:2]

    margin_v = int(TH * (100 - sub_y_percent - 7.0) / 100) 
    scaled_font = int(font_size * 1.8) 
    
    ass_path = os.path.join(job_dir, "subs.ass")
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(f"[Script Info]\nScriptType: v4.00+\nPlayResX: {TW}\nPlayResY: {TH}\n\n")
        f.write("[V4+ Styles]\n")
        f.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
        f.write(f"Style: Default,{font_fam},{scaled_font},&H00{ass_color_mapped},&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,4,1,2,30,30,{margin_v},1\n\n")
        f.write("[Events]\n")
        f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        for seg in segments:
            txt = seg.get("text", "").strip()
            if not txt: continue
            start_t = float(seg["start"]); end_t = float(seg["end"])
            if end_t - start_t < 0.5: end_t = start_t + 0.5
            ass_start = format_ass_time(start_t); ass_end = format_ass_time(end_t)
            clean_txt = txt.replace("$$", "\\N").replace("\n", "\\N")
            if anim_sub:
                clean_txt = "{\\fad(150,150)\\t(\\fscx108\\fscy108)}" + clean_txt
            f.write(f"Dialogue: 0,{ass_start},{ass_end},Default,,0,0,0,,{clean_txt}\n")
    return ass_path

def split_burmese_text_chronologically(text, start_t, end_t, max_chars=14):
    if not text.strip(): return [{"start": start_t, "end": end_t, "text": text}]
    words = [w for w in text.split(' ') if w != ""]
    SENTENCE_END = ('။', '၊', '!', '?', '.', ',')
    def visible_len(s): return len(_burmese_syllable_clusters(s))
    chunks = []; current_words = []; current_len = 0
    for word in words:
        w_len = visible_len(word)
        projected_len = current_len + w_len + (1 if current_words else 0)
        if current_words and projected_len > max_chars:
            chunks.append(" ".join(current_words)); current_words = [word]; current_len = w_len
        else:
            current_words.append(word); current_len = projected_len if len(current_words) > 1 else w_len
        if word.strip() and word.strip()[-1] in SENTENCE_END:
            chunks.append(" ".join(current_words)); current_words = []; current_len = 0
    if current_words: chunks.append(" ".join(current_words))
    if not chunks: chunks = [text]

    duration = end_t - start_t
    if duration < 0.5: duration = 0.5
    chunk_lens = [max(visible_len(c), 1) for c in chunks]
    total_len = sum(chunk_lens)
    result = []; cursor = start_t
    for i, chunk in enumerate(chunks):
        is_last = (i == len(chunks) - 1)
        share = chunk_lens[i] / total_len
        c_dur = duration * share
        c_start = cursor
        c_end = end_t if is_last else min(cursor + c_dur, end_t)
        if c_end - c_start < 0.5: c_end = min(c_start + 0.5, end_t) if not is_last else end_t
        result.append({"start": c_start, "end": c_end, "text": chunk})
        cursor = c_end
    return result

def split_subtitle_text_chronologically(text, start_t, end_t, max_chars=14, space_delimited=True):
    if space_delimited: return split_burmese_text_chronologically(text, start_t, end_t, max_chars=max_chars)
    if not text.strip(): return [{"start": start_t, "end": end_t, "text": text}]
    SENTENCE_END = ('。', '!', '?', '，', '、', '.', '!', '?', ',')
    chunks = []; current = ""
    for ch in text:
        current += ch
        if len(current.strip()) >= max_chars or ch in SENTENCE_END:
            if current.strip(): chunks.append(current.strip()); current = ""
    if current.strip(): chunks.append(current.strip())
    if not chunks: chunks = [text]

    duration = max(end_t - start_t, 0.5)
    chunk_lens = [max(len(c), 1) for c in chunks]
    total_len = sum(chunk_lens)
    result = []; cursor = start_t
    for i, chunk in enumerate(chunks):
        is_last = (i == len(chunks) - 1)
        share = chunk_lens[i] / total_len
        c_dur = duration * share
        c_start = cursor
        c_end = end_t if is_last else min(cursor + c_dur, end_t)
        if c_end - c_start < 0.5: c_end = min(c_start + 0.5, end_t) if not is_last else end_t
        result.append({"start": c_start, "end": c_end, "text": chunk})
        cursor = c_end
    return result

def sync_call_groq_whisper(audio_path, groq_key):
    """Groq-hosted Whisper STT with 10-minute chunks and key failover."""
    groq_keys = [k.strip() for k in re.split(r"[,\s]+", str(groq_key or "")) if k.strip()]
    if not groq_keys:
        raise RuntimeError("Groq API Key မရှိပါ။ /setkey groq GROQ_KEY1,GROQ_KEY2 ဖြင့် ထည့်ပါ။")
    if not os.path.isfile(audio_path):
        raise RuntimeError("Transcription audio file မတွေ့ပါ။")
    import httpx
    import tempfile
    work_dir = tempfile.mkdtemp(prefix="groq_whisper_")
    pattern = os.path.join(work_dir, "part_%03d.mp3")
    split = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", audio_path,
         "-f", "segment", "-segment_time", "600", "-reset_timestamps", "1",
         "-c:a", "libmp3lame", "-b:a", "48k", "-ar", "16000", "-ac", "1", pattern],
        capture_output=True, text=True
    )
    if split.returncode != 0:
        raise RuntimeError("Groq Whisper အတွက် audio ခွဲမရပါ: " + split.stderr[-400:])
    parts = sorted(glob.glob(os.path.join(work_dir, "part_*.mp3")))
    if not parts:
        raise RuntimeError("Groq Whisper audio အပိုင်း မတွေ့ပါ။")
    all_segments, all_text, offset = [], [], 0.0
    try:
        with httpx.Client(timeout=240.0) as client:
            for part_no, part_path in enumerate(parts, 1):
                if os.path.getsize(part_path) > 24 * 1024 * 1024:
                    raise RuntimeError(f"Groq Whisper အပိုင်း {part_no} သည် 24MB ထက်ကြီးနေပါသည်။")
                print(f"🎙️ Groq Whisper transcription {part_no}/{len(parts)}...", flush=True)
                response = None
                last_error = "No Groq keys available"
                for key_index, candidate_key in enumerate(groq_keys, 1):
                    with open(part_path, "rb") as audio_file:
                        response = client.post(
                            "https://api.groq.com/openai/v1/audio/transcriptions",
                            headers={"Authorization": f"Bearer {candidate_key}"},
                            files={"file": (os.path.basename(part_path), audio_file, "audio/mpeg")},
                            data={"model": "whisper-large-v3-turbo", "response_format": "verbose_json",
                                  "timestamp_granularities[]": "segment"},
                        )
                    if response.status_code == 200:
                        break
                    last_error = f"HTTP {response.status_code}: {response.text[:250]}"
                    # Auth/permission/quota failures move to the next supplied key.
                    if response.status_code not in (401, 403, 429, 500, 502, 503, 504):
                        break
                    print(f"⚠️ Groq key {key_index}/{len(groq_keys)} failed; trying next key...", flush=True)
                if response is None or response.status_code != 200:
                    raise RuntimeError(f"Groq Whisper failed with all available keys. Last error: {last_error}")
                payload = response.json()
                for seg in payload.get("segments", []) or []:
                    txt = str(seg.get("text", "")).strip()
                    if txt:
                        all_segments.append({"start": offset + float(seg.get("start", 0)),
                                             "end": offset + float(seg.get("end", 0)), "text": txt})
                txt_all = str(payload.get("text", "")).strip()
                if txt_all: all_text.append(txt_all)
                offset += awaitless_media_duration(part_path)
    finally:
        import shutil as _shutil
        _shutil.rmtree(work_dir, ignore_errors=True)
    print(f"✅ Groq Whisper completed: {len(all_segments)} segments", flush=True)
    return {"segments": all_segments, "text": " ".join(all_text), "duration": offset}

def awaitless_media_duration(path):
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                                capture_output=True, text=True, check=True)
        return max(0.0, float(result.stdout.strip()))
    except Exception:
        return 600.0

CHUNK_FRAME_RATE = 30
def _compute_frame_synced_durations(raw_durations, frame_rate=CHUNK_FRAME_RATE):
    target = []; carry = 0.0
    for d in raw_durations:
        ideal = d + carry; frames = max(1, round(ideal * frame_rate)); actual = frames / frame_rate; carry = ideal - actual; target.append(actual)
    return target

# =====================================================================
# 🔄 FIXED CHUNK PROCESSING - Sync Fix + Clean Try/Except block
# =====================================================================
def process_single_chunk(args):
    idx, start_time, end_time, input_video, chunk_audio_path, target_dur, p_form, p_res, do_flip, do_bypass, narration_gain, job_token, is_original_audio = args

    # Unique per-job output path prevents simultaneous users overwriting same-index chunks.
    chunk_video_path = f"temp/chunk_vid_{job_token}_{idx}.ts"
    try:
        audio_dur = max(target_dur, 0.1)
        vid_dur = max(end_time - start_time, 0.1)
        # setpts multiplies timestamps, so output duration = source duration * scale.
        # Therefore scale = target audio duration / source video duration.
        # Clamp extreme retiming to avoid pathological playback-speed changes.
        video_pts_scale = max(0.2, min(audio_dur / vid_dur, 6.0))
        dim_w, dim_h = get_video_dimensions(p_form, p_res)
        
        flip_filter = "hflip," if do_flip else ""
        if do_bypass:
            float_dir = "sin(t)" if idx % 2 == 0 else "cos(t)"
            dynamic_zoom = f"crop=iw*0.96:ih*0.96:(iw-out_w)/2+((iw-out_w)/2)*{float_dir}:(ih-out_h)/2+((ih-out_h)/2)*{float_dir},"
        else: 
            dynamic_zoom = "crop=iw*0.96:ih*0.96:iw*0.02:ih*0.02," if idx % 2 != 0 else ""
            
        color_edit = "eq=contrast=1.04:brightness=0.01:saturation=1.12,"
        video_out_dur = vid_dur * video_pts_scale
        pad_needed = max(0.0, audio_dur - video_out_dur)
        tpad_filter = f"tpad=stop_mode=clone:stop_duration={pad_needed:.3f}," if pad_needed > 0.03 else ""

        v_branch = f"[0:v]trim=start={start_time}:end={end_time},setpts=PTS-STARTPTS,setpts={video_pts_scale:.6f}*PTS,{flip_filter}{dynamic_zoom}{color_edit}split=2[vb_bg][vb_fg];[vb_bg]scale={dim_w}:{dim_h}:force_original_aspect_ratio=increase,crop={dim_w}:{dim_h},boxblur=16:4,eq=brightness=-0.05[vb_bgblur];[vb_fg]scale={dim_w}:{dim_h}:force_original_aspect_ratio=decrease[vb_fgs];[vb_bgblur][vb_fgs]overlay=(W-w)/2:(H-h)/2,{tpad_filter}trim=0:{audio_dur:.3f},setpts=PTS-STARTPTS[v_out];"
        
        if is_original_audio:
            # Preserve source soundtrack level and dynamics; never apply narrator gain/limiting.
            a_branch = f"[1:a]aresample=44100,apad,atrim=0:{audio_dur:.3f},asetpts=PTS-STARTPTS[a_out]"
        else:
            # User voice-volume control and peak protection apply only to generated narration.
            a_branch = f"[1:a]aresample=44100,dynaudnorm=f=150:g=15:p=0.90:m=5:r=0.12,volume={narration_gain:.3f},alimiter=limit=0.95,apad,atrim=0:{audio_dur:.3f},asetpts=PTS-STARTPTS[a_out]"

        # Fixed: Using safe -r 30 compatible with all FFmpeg versions while maintaining sync
        last_chunk_error = None
        for chunk_attempt in range(1, 3):
            try:
                if os.path.exists(chunk_video_path): os.remove(chunk_video_path)
                run_ffmpeg([
                    'ffmpeg', '-y', '-i', input_video, '-i', chunk_audio_path,
                    '-filter_complex', v_branch + a_branch,
                    '-map', '[v_out]', '-map', '[a_out]',
                    *video_encoder_args(preset='ultrafast', quality=28), '-pix_fmt', 'yuv420p',
                    '-r', '30',
                    '-c:a', 'aac', '-ar', '44100', '-ac', '2', chunk_video_path
                ], label=f"chunk_{idx}_attempt_{chunk_attempt}")
                if not os.path.isfile(chunk_video_path) or os.path.getsize(chunk_video_path) < 2048:
                    raise RuntimeError('Chunk output ဖိုင်မပြည့်စုံပါ။')
                measured_duration = get_media_duration(chunk_video_path)
                if measured_duration <= 0:
                    raise RuntimeError('Chunk duration သုည ဖြစ်နေပါသည်။')
                return (idx, chunk_video_path, measured_duration)
            except Exception as chunk_error:
                last_chunk_error = chunk_error
                logging.exception('Chunk %s attempt %s failed', idx, chunk_attempt)
                if os.path.exists(chunk_video_path):
                    try: os.remove(chunk_video_path)
                    except Exception: pass
        raise RuntimeError(f"Chunk {idx} retry 2 ကြိမ်လုံး မအောင်မြင်ပါ: {last_chunk_error}")
    except Exception as e:
        logging.exception("Chunk Error at %s", idx)
        print(f"Chunk Error at {idx}: {type(e).__name__}: {str(e)}")
        if os.path.exists(chunk_video_path): os.remove(chunk_video_path)
        return (idx, None, 0.0)

async def run_all_chunks(args_list, progress_callback=None):
    sem = asyncio.Semaphore(2)
    async def _one(args):
        async with sem:
            return await asyncio.to_thread(process_single_chunk, args)
    tasks = [asyncio.create_task(_one(args)) for args in args_list]
    results = []
    total = max(1, len(tasks))
    done = 0
    for task in asyncio.as_completed(tasks):
        results.append(await task)
        done += 1
        if progress_callback:
            await progress_callback(done, total)
    return sorted(results, key=lambda x: x[0])

async def generate_title_hook_hashtags(story_text, gemini_pool, target_lang="Burmese", vid_type="movie"):
    context_str = "This is a full standalone movie recap." if vid_type == "movie" else "This is a part/episode of an ongoing series. Make sure the title and hook reflect that it is a continuing story (e.g. adding Part numbers if necessary)."
    prompt = f"""[SYSTEM INSTRUCTION: You are a fast, viral Content Creator. {context_str}] Based on this video summary, generate an engaging Title, a Hook, and exactly 3 relevant hashtags. Language for all outputs: {target_lang}
    Story Summary: {story_text[:2500]}
    Output EXACTLY in this JSON format without any extra markdown or text:
    {{
        "title": "Engaging Title in {target_lang} (STRICTLY 10 to 15 characters total, absolutely NO MORE than 15 chars, ONE line)",
        "hook": "Engaging Hook in {target_lang} (1 short sentence)",
        "hashtags": "#Recap #Story #Viral"
    }}"""
    
    safe_config = [
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
    ]

    for current_key in [k for k in gemini_pool.keys if k not in gemini_pool.dead]:
        client = _new_gemini_client(current_key)
        try:
            response = await _gemini_request_with_retry(
                client,
                (gemini_model_order(getattr(gemini_pool, "preferred_model", "auto"), getattr(gemini_pool, "available_models", None)) or list(GEMINI_MODEL_CANDIDATES))[0],
                prompt,
                types.GenerateContentConfig(temperature=0.7, safety_settings=safe_config, response_mime_type="application/json"),
                attempts=2
            )
            raw = response.text if (response and hasattr(response, 'text')) else ""
            if raw:
                data = json.loads(re.sub(r'```json|```', '', raw).strip())
                return data.get("title", "🎬 Recap"), data.get("hook", "Engaging Story!"), data.get("hashtags", "#Recap")
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "quota" in err_str or "invalid" in err_str:
                gemini_pool.mark_dead(current_key)
            else:
                await asyncio.sleep(2)
    return "🎬 Recap", "Engaging Story!", "#Recap #Viral #Story"

async def translate_segments_to_language(timeline_data, speech_indices, gemini_pool, lang_name, batch_size=16):
    translated = {}
    translation_models = tuple(gemini_model_order(
        getattr(gemini_pool, "preferred_model", "auto"),
        getattr(gemini_pool, "available_models", None)
    )) or tuple(GEMINI_MODEL_CANDIDATES)
    for i in range(0, len(speech_indices), batch_size):
        chunk_indices = speech_indices[i:i + batch_size]
        original_segments_text = "".join([f"[{idx}] {timeline_data[idx]['text'].strip()}\n" for idx in chunk_indices])
        prompt = f"""[SYSTEM INSTRUCTION: You are a professional subtitle translator.] Translate the following numbered lines into natural, concise {lang_name}, written for on-screen subtitles (short, readable at a glance).
"{original_segments_text}"
Rules:
1. Translate EVERY line.
2. Keep each translation short and natural.
3. You MUST format the output exactly as: [index] Translated Text
4. Do NOT output anything else."""
        safe_config = [
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        ]
        success = False
        # Each key/model pair is attempted at most once per batch: no endless loop
        # when every configured model is quota-limited or unavailable.
        active_keys = [k for k in gemini_pool.keys if k not in gemini_pool.dead]
        for current_key in active_keys:
            if success:
                break
            client = _new_gemini_client(current_key)
            for model_name in translation_models:
                try:
                    response = await _gemini_request_with_retry(
                        client, model_name, prompt,
                        types.GenerateContentConfig(temperature=0.45, max_output_tokens=8192, safety_settings=safe_config)
                    )
                    raw = response.text if (response and hasattr(response, 'text')) else ""
                    if raw:
                        matches = re.findall(r'\[?\**(\d+)\**\]?[:\.\-\s]+(.*)', raw)
                        for match in matches:
                            if match[1].strip():
                                translated[int(match[0])] = match[1].strip()
                        success = bool(matches)
                        if success:
                            break
                except Exception as exc:
                    err_str = str(exc).lower()
                    logging.warning("Subtitle translation %s failed: %s", model_name, str(exc)[:180])
                    if any(x in err_str for x in ("api_key_invalid", "invalid api key", "api key not valid", "permission_denied")):
                        gemini_pool.mark_dead(current_key)
                        break
                    continue
        if not success:
            logging.error("Subtitle translation batch %s-%s failed on all verified Gemini models/keys", i, i + len(chunk_indices))
    return translated

async def generate_gap_recap_narration(timeline_data, speech_indices, translated_dict, gemini_pool, target_lang="Burmese", style_id=1, preferred_model="auto", available_models=None, progress_callback=None):
    """Create short recap narration only for timeline gaps with no detected original dialogue.
    Uses adjacent transcript context, never invents unsupported plot facts. Original-dialogue
    intervals are deliberately excluded and retain their source audio.
    """
    gap_indices = [i for i, seg in enumerate(timeline_data)
                   if not seg.get("is_speech") and float(seg.get("end", 0))-float(seg.get("start", 0)) >= 0.90]
    if not gap_indices:
        return {}
    style_names = {
        1: "သဘာဝကျသော ရုပ်ရှင်ဇာတ်ကြောင်းပြောဟန်",
        2: "တင်းမာပြီး အရှိန်ရှိသော Thriller ဟန်",
        3: "ပေါ့ပါးသွက်လက်သော လူငယ်စကားပြောဟန်",
        4: "မူရင်းအခြေအနေက ထောက်ခံသည့်နေရာတွင်သာ ဟာသပါသောဟန်",
        5: "ခံစားချက်ပါသော်လည်း မပိုမလျှံသော Drama ဟန်",
        6: "လုပ်ဆောင်ချက်အစီအစဉ်ရှင်းလင်းသော Action ဟန်",
        7: "ရုပ်ရှင်ဆန်ပြီး အခြေအနေလိုက် အရှိန်ပြောင်းသောဟန်",
        8: "သဘာဝကျသော SANMA Signature မြန်မာ Recap ဟန်",
    }
    jobs=[]
    for idx in gap_indices:
        prev_txt = ""
        next_txt = ""
        for j in range(idx-1, -1, -1):
            if timeline_data[j].get("is_speech") and timeline_data[j].get("text", "").strip():
                prev_txt = timeline_data[j]["text"].strip(); break
        for j in range(idx+1, len(timeline_data)):
            if timeline_data[j].get("is_speech") and timeline_data[j].get("text", "").strip():
                next_txt = timeline_data[j]["text"].strip(); break
        # Do not narrate a gap if there is no dialogue context to ground it.
        if prev_txt and next_txt:
            jobs.append({"index": idx, "seconds": round(float(timeline_data[idx]["end"])-float(timeline_data[idx]["start"]),2),
                         "before": prev_txt[:350], "after": next_txt[:350]})
    if not jobs:
        return {}
    prompt = f"""သင်သည် မြန်မာ Movie Recap ဇာတ်ညွှန်းရေးသူဖြစ်သည်။ အောက်ပါအချက်အလက်များသည် မူရင်းလူပြောသံ မတွေ့ရှိသော အချိန်ကွက်များဖြစ်သည်။
ရည်ရွယ်ချက်မှာ ထိုအချိန်ကွက်များတွင်သာ Recap narrator စာကြောင်းတို ထည့်ရန်ဖြစ်သည်။
ဘာသာစကား: {target_lang}
ဟန်: {style_names.get(style_id, style_names[1])}
စည်းကမ်းများ:
- အနီးကပ်ရှေ့/နောက် Dialogue မှ အတည်ပြုနိုင်သော အကြောင်းအရာကိုသာ ဆက်စပ်ပြောပါ။ မမြင်ရသော လှုပ်ရှားမှု၊ ဇာတ်ကောင်၊ အကြောင်းရင်း သို့မဟုတ် ဖြစ်ရပ်ကို မတီထွင်ပါနှင့်။
- ရှေ့/နောက် Dialogue နှစ်ဖက်လုံးမှ အတည်ပြုနိုင်သော ဖြစ်ရပ်/လုပ်ဆောင်ချက် မရှိလျှင် EMPTY ဟုသာ ပြန်ပါ။
- အသံတိတ်နေခြင်းတစ်ခုတည်းကို ဇာတ်လမ်းဖြစ်ရပ်ဟု မယူဆပါနှင့်။ အထွေထွေ filler စာကြောင်း မရေးပါနှင့်။
- အချိန်ကွက်ကြာချိန်နှင့် ကိုက်ညီအောင် တိုတိုရေးပါ။ Hook မထည့်ပါနှင့်။
- Output သည် [index] စာကြောင်း ပုံစံသာ ဖြစ်ရမည်။
အချိန်ကွက်များ:
""" + "\n".join(f"[{x['index']}] duration={x['seconds']}s | before={x['before']} | after={x['after']}" for x in jobs)
    model_order = gemini_model_order(preferred_model, available_models)
    for _ in range(max(1, len(gemini_pool.keys))):
        if not gemini_pool.has_keys(): break
        key=gemini_pool.next_key(); client=genai.Client(api_key=key)
        for model_name in model_order:
            try:
                if progress_callback:
                    await progress_callback(f"Gemini: {GEMINI_MODEL_LABELS.get(model_name, model_name)} ကို စမ်းသပ်နေသည်...")
                response=await _gemini_request_with_retry(client, model_name, prompt,
                    types.GenerateContentConfig(temperature=0.35, max_output_tokens=2048))
                raw=response.text if response and hasattr(response,"text") else ""
                out={}
                for m in re.findall(r'^\s*\[?(\d+)\]?\s*[:.\-]?\s*(.*?)\s*$', raw, re.M):
                    val=m[1].strip()
                    if val and val.upper() != "EMPTY": out[int(m[0])]=val
                if out:
                    return out
                logging.warning("Gap recap model %s returned no valid indexed lines", model_name)
                continue
            except Exception as e:
                low=str(e).lower()
                if "429" in low or "quota" in low or "resource_exhausted" in low:
                    reason = "429 Quota / Rate Limit"
                elif "404" in low or "not found" in low:
                    reason = "404 Model Not Found"
                elif "timeout" in low or "timed out" in low:
                    reason = "Timeout"
                elif "connection" in low or "network" in low:
                    reason = "Network Error"
                elif "503" in low or "unavailable" in low:
                    reason = "503 UNAVAILABLE"
                else:
                    reason = "API Error"
                logging.warning("Gap recap model %s failed (%s): %s", model_name, reason, str(e)[:180])
                if progress_callback:
                    await progress_callback(
                        f"Gemini {GEMINI_MODEL_LABELS.get(model_name, model_name)}: {reason}; နောက် Model သို့ Fallback လုပ်နေသည်..."
                    )
                continue
    return {}

async def advanced_sync_pipeline(audio_path, gemini_keys_str, input_video, output_video_path, voice_config, user_speed_val, user_id, update_status_func=None):
    gemini_pool = GeminiKeyPool(gemini_keys_str)
    gemini_pool.preferred_model = user_gemini_model.get(user_id, "auto")
    gemini_pool.available_models = user_gemini_available_models.get(user_id) or None
    
    total_video_duration = await asyncio.to_thread(get_media_duration, input_video)

    if user_id not in user_sub_mode: user_sub_mode[user_id] = True
    if user_id not in user_voice_volume: user_voice_volume[user_id] = 400
    if user_id not in user_translation_style: user_translation_style[user_id] = 2
    sub_enabled = user_sub_mode.get(user_id, True)

    p_form = user_platform.get(user_id, "tt")
    p_res = user_res.get(user_id, "1080")
    selected_font_size = user_font_size.get(user_id, 45)
    do_flip = user_flip_mode.get(user_id, False)
    do_bypass = user_bypass_mode.get(user_id, False)
    
    is_multi_voice = user_multivoice.get(user_id, False)
    is_auto_trim = user_autotrim.get(user_id, False)
    is_anim_sub = user_animsub.get(user_id, False)
    is_prog_bar = user_progressbar.get(user_id, False)
    v_type = user_video_type.get(user_id, "movie")

    if update_status_func: 
        await update_status_func("၂။ 🎙️ AI မှ အသံကို စာသားပြောင်းနေပါသည် (Groq Whisper STT)...")

    try:
        response_json = await asyncio.to_thread(sync_call_groq_whisper, audio_path, ",".join(gemini_pool.groq_keys))
            
        if "segments" not in response_json or not response_json["segments"]:
            words = response_json.get("text", "").split()
            if words:
                word_dur = response_json.get("duration", total_video_duration) / len(words)
                raw_segments = [{"start": i * word_dur, "end": (i + 1) * word_dur, "text": word} for i, word in enumerate(words)]
            else: raw_segments = []
        else: raw_segments = response_json.get("segments", [])
    except Exception as e: raise Exception(f"Groq Whisper STT Error: {str(e)}")

    # Hybrid mode must still render a video when Whisper finds no dialogue:
    # in that case there is no recap narration to insert, so preserve source audio.
    hybrid_mode_requested = user_original_intro_mode.get(user_id, True)
    if not raw_segments and not hybrid_mode_requested:
        raise Exception("❌ STT Error: မူရင်းဗီဒီယိုတွင် စကားပြောသံများ မပါဝင်ပါ (သို့) AI မှ ခွဲခြားသိမြင်နိုင်ခြင်း မရှိပါ။")
    if not raw_segments:
        raw_segments = []

    if update_status_func:
        await update_status_func("PROGRESS|AI Script|10|Whisper စာသားဖော်ထုတ်ပြီး၊ Recap အသံစာသား ပြင်ဆင်နေသည်...")
    # Group Whisper speech into longer timeline blocks to reduce the number of
    # narration near 15 chunks without dropping any recognized text or gaps.
    timeline_data = build_complete_timeline(raw_segments, total_video_duration, max_dur=20.0, max_gap=0.5)

    if is_auto_trim and not hybrid_mode_requested:
        timeline_data = [seg for seg in timeline_data if seg["is_speech"]]

    target_voice_lang = user_main_lang.get(user_id, "Burmese")
    gender_rule = "Use a female narrator tone." if voice_config.get("gender") == "female" else "Use a male narrator tone."
    if target_voice_lang == "Burmese":
        gender_rule = "မိန်းကလေး narrator အသံ ဖြင့် ဖတ်မည်ဖြစ်ပါသည်။" if voice_config.get("gender") == "female" else "ယောက်ျားလေး narrator အသံ ဖြင့် ဖတ်မည်ဖြစ်ပါသည်။"

    speech_indices = [idx for idx, seg in enumerate(timeline_data) if seg["is_speech"]]
    if not speech_indices and not user_original_intro_mode.get(user_id, True):
        raise Exception("❌ STT Error: ဗီဒီယိုတွင် အသံပါသော်လည်း စကားပြောသံ (Speech) များကို ရှာမတွေ့ပါ။")

    if update_status_func: 
        await update_status_func("၃။ 📝 စာသားများကို ဘာသာပြန်ဆိုနေပါသည် (Gemini → Groq Fallback)...")

    translated_dict = {}
    full_translated_text = ""
    story_title = "🎬 Recap"
    story_hook = "Engaging Story!"

    chosen_prompt_mode = "new" 

    for i in range(0, len(speech_indices), 16):
        chunk_indices = speech_indices[i:i+16]
        original_segments_text = "".join([f"[{idx}] {timeline_data[idx]['text'].strip()}\n" for idx in chunk_indices])
        
        if chosen_prompt_mode == "new":
            prompt = NEW_GEMINI_PROMPT_TEMPLATE.replace("{gender_rule}", gender_rule).replace("{original_segments_text}", original_segments_text)
            is_final_batch = (i + 16 >= len(speech_indices))
            prompt += "\n\nBATCH CONTEXT: " + ("ဤသည် ဇာတ်ကြောင်း၏ နောက်ဆုံး batch ဖြစ်သည်။ နောက်ဆုံးစာကြောင်းတွင်သာ ဇာတ်လမ်းနှင့်အမှန်တကယ်ကိုက်ညီလျှင် အနှစ်ချုပ်ဒဿန/မေးခွန်းကို သဘာဝကျကျ ထည့်နိုင်သည်။" if is_final_batch else "ဤသည် အလယ်ပိုင်း batch ဖြစ်သည်။ နိဂုံးချုပ်ဒဿန၊ နောက်ဆုံးမေးခွန်း သို့မဟုတ် ဇာတ်လမ်းအဆုံးသတ်သလို စာသား မထည့်ပါနှင့်။")
        else:
            prompt = ORIGINAL_GEMINI_PROMPT_TEMPLATE.replace("{target_voice_lang}", target_voice_lang).replace("{gender_rule}", gender_rule).replace("{original_segments_text}", original_segments_text)

        style_id = user_translation_style.get(user_id, 1)
        style_instructions = {
            1: "STYLE 1 — CLASSIC STORYTELLER: ရုပ်ရှင်ကို ဘေးမှကြည့်ပြီး ပရိသတ်ကို အဖြစ်အပျက်တစ်ခုပြီးတစ်ခု ချောမွေ့စွာ ပြောပြသည့် သဘာဝကျသော recap ဟန်။ စကားဆက်များကို မျှတစွာသုံးပြီး အလွန်အကျွံ အော်ဟစ်သလို မရေးပါနှင့်။",
            2: "STYLE 2 — INTENSE THRILLER: အန္တရာယ်၊ အချိန်ဖိအား၊ လိုက်လံမှုနှင့် မမျှော်လင့်သောလှည့်ကွက်များကို ဝါကျဖွဲ့စည်းပုံနှင့် စကားလုံးရွေးချယ်မှုဖြင့် တင်းမာစေပါ။ ဝါကျတို/ရှည်ကို အလှည့်ကျသုံးပါ။ ဖြစ်ရပ်မတီထွင်ပါနှင့်။",
            3: "STYLE 3 — YOUTHFUL CASUAL: သူငယ်ချင်းကို ပြန်ပြောသလို ပေါ့ပါး၊ သွက်လက်ပြီး ခေတ်မီသော မြန်မာစကားပြေကို သုံးပါ။ Slang ကို အနည်းငယ်သာသုံးပြီး အတင်းအကျပ် ဟာသမထည့်ပါနှင့်။",
            4: "STYLE 4 — COMEDY: မူရင်းဇာတ်ကွက်ထဲက ရယ်စရာအခြေအနေ၊ အချိန်ကိုက်မှုနှင့် ဇာတ်ကောင်တုံ့ပြန်မှုကို ထင်ရှားစေပါ။ ဇာတ်ကွက်ကို မပြောင်းဘဲ punchline ကို မူရင်းက ထောက်ခံသည့်နေရာတွင်သာ ထိန်းပါ။",
            5: "STYLE 5 — EMOTIONAL DRAMA: ဆုံးရှုံးမှု၊ သံယောဇဉ်၊ ကြောက်ရွံ့မှုနှင့် ဆုံးဖြတ်ချက်တို့ကို တည်ငြိမ်ပြီး ခံစားချက်ပါသော အသံနေအသံထားဖြင့် ရေးပါ။ အလွန်အကျွံ ဝမ်းနည်းစကား မဖြည့်ပါနှင့်။",
            6: "STYLE 6 — WAR & ACTION: တိုက်ပွဲ၊ လှုပ်ရှားမှု၊ နည်းဗျူဟာ၊ အန္တရာယ်နှင့် အကျိုးဆက်ကို ရှင်းလင်းတိကျစွာ ဖော်ပြပါ။ လုပ်ဆောင်ချက်အစီအစဉ် မပျက်စေရ။",
            7: "STYLE 7 — CINEMATIC HYBRID: အရေးကြီးသည့်နေရာတွင် ရုပ်ရှင်ဆန်သော မြင်ကွင်းဖော်ပြမှု၊ တင်းမာမှုနှင့် ခံစားချက်ကို ပေါင်းစပ်ပါ။ အေးဆေးသည့်အခန်းတွင် အေးဆေး၊ အရှိန်မြင့်သည့်အခန်းတွင် သွက်လက်စေပါ။",
            8: "STYLE 8 — SANMA SIGNATURE: တတိယပုဂ္ဂိုလ်ဖြင့် မြန်မာ Movie Recap ဇာတ်ကြောင်းပြောပါ။ 'ပါတယ်၊ ဖြစ်လာပါတယ်၊ လိုက်ပါတယ်၊ နေရပါတယ်၊ တာပါ' အဆုံးသတ်များကို အခြေအနေလိုက် အမျိုးမျိုးသုံးပါ။ အချိန်ပြောင်းလဲမှုကို ရှင်းလင်းစွာချိတ်ဆက်ပြီး ဒဿနကို အလွန်အကျွံမထည့်ပါနှင့်။",
        }
        prompt += "\n\nUSER SELECTED NARRATION STYLE:\n" + style_instructions.get(style_id, style_instructions[1])
        prompt += """
မြန်မာ Movie Recap အတွက် မဖြစ်မနေလိုက်နာရန်:
- ပထမ batch ဖြစ်မှသာ ပထမစာကြောင်းကို မူရင်းဇာတ်ကွက်ထဲမှ စိတ်ဝင်စားဖွယ် Hook ဖြင့် စပါ။ နောက် batch များတွင် ဇာတ်လမ်းဆက်ကြောင်းကို တိုက်ရိုက်ဆက်ပါ၊ Hook အသစ်မစပါနှင့်။
- စာကြောင်းတိုင်းကို သဘာဝကျသော မြန်မာစကားပြောဇာတ်ကြောင်းဖြင့် ပြန်ရေးပါ။ စက်ရုပ်ဆန်သော တိုက်ရိုက်ဘာသာပြန်ခြင်းကို ရှောင်ပါ။
- ဇာတ်ကောင်အမည်၊ လိင်၊ ဆက်နွယ်မှု၊ နေရာ၊ အချိန်၊ အကြောင်းရင်းနှင့် ဖြစ်ရပ်အစီအစဉ်ကို မူရင်းအတိုင်း ထိန်းပါ။ အချက်အလက်မတီထွင်ပါနှင့်။
- အရေးကြီးသော ဇာတ်ကွက်များ မချန်ပါနှင့်။ [index] နံပါတ်နှင့် အစီအစဉ်ကို အတိအကျထိန်းပါ။
- ရွေးထားသော STYLE ကို တိတိကျကျလိုက်နာပါ။ အခြား Style များ၏ အသံနေအသံထားကို မရောပါနှင့်။
- ဇာတ်ဝင်ခန်းနှင့် ကိုက်ညီသည့် ချိတ်ဆက်စကားများနှင့် ဝါကျအဆုံးများကို မျိုးစုံသုံးပါ။ တစ်မျိုးတည်း ထပ်ခါထပ်ခါ မသုံးပါနှင့်။
- မြန်မာစာ စာလုံးပေါင်း၊ သတ်ပုံ၊ ဝါကျဖွဲ့စည်းပုံ မှန်ကန်စေရန် စစ်ဆေးပြီးမှ ပြန်ပေးပါ။ အသံဖတ်မည့်စာသားနှင့် SRT စာတန်းထိုးစာသား တစ်ထပ်တည်းဖြစ်ရမည်။
- မူရင်းထက် အလွန်တိုအောင် မချုံ့ပါနှင့်။ အသံဖတ်ရန် သဘာဝကျပြီး ချောမွေ့စေပါ။
"""

        safe_config = [
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        ]
        
        raw = ""
        success = False
        last_gemini_error = "No response"
        models_to_try = gemini_model_order(
            user_gemini_model.get(user_id, "auto"),
            user_gemini_available_models.get(user_id) or None
        ) or list(GEMINI_MODEL_CANDIDATES)
        active_keys = [k for k in gemini_pool.keys if k not in gemini_pool.dead]
        _batch_total = max(1, (len(speech_indices) + 15) // 16)
        _batch_number = (i // 16) + 1
        _base_pct = 10 + int((_batch_number - 1) * 70 / _batch_total)
        for model_index, m in enumerate(models_to_try):
            if success:
                break
            model_unavailable = False
            for key_index, current_gemini_key in enumerate(active_keys):
                if success or model_unavailable:
                    break
                client = _new_gemini_client(current_gemini_key)
                if update_status_func:
                    _model_label = GEMINI_MODEL_LABELS.get(m, m)
                    await update_status_func(
                        f"PROGRESS|AI Script|{_base_pct}|Batch {_batch_number}/{_batch_total} — {_model_label} ကို စမ်းသပ်နေသည် (Key {key_index + 1}/{len(active_keys)}, Model {model_index + 1}/{len(models_to_try)})..."
                    )
                try:
                    response = await _gemini_request_with_retry(
                        client, m, prompt,
                        types.GenerateContentConfig(temperature=0.45, max_output_tokens=8192, safety_settings=safe_config)
                    )
                    raw = response.text if (response and hasattr(response, 'text')) else ""
                    if raw:
                        success = True
                        break
                    last_gemini_error = f"{m}: empty response"
                    model_unavailable = True
                except Exception as e:
                    last_gemini_error = f"{m}: {str(e)[:220]}"
                    err_str = str(e).lower()
                    if any(x in err_str for x in ("api_key_invalid", "invalid api key", "api key not valid", "permission_denied")):
                        gemini_pool.mark_dead(current_gemini_key)
                        continue
                    if "429" in err_str or "quota" in err_str or "resource_exhausted" in err_str:
                        # Quota is key-specific; try this model with the next key.
                        continue
                    # 404/503/timeout/network errors are treated as model/service
                    # failures for this batch; move to the next verified model.
                    model_unavailable = True
        if (not success or not raw) and gemini_pool.groq_key:
            try:
                groq_payload = {
                    "model": "openai/gpt-oss-120b",
                    "messages": [
                        {"role": "system", "content": "You are a professional Burmese movie-recap storyteller. Preserve every source event and index, write natural spoken Burmese narration, do not invent facts, and return only the numbered translated lines in the requested format."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.4,
                    "max_tokens": 8192
                }
                async with httpx.AsyncClient(timeout=90.0) as groq_client:
                    groq_res = await groq_client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {gemini_pool.groq_key}", "Content-Type": "application/json"},
                        json=groq_payload
                    )
                    if groq_res.status_code == 200:
                        groq_data = groq_res.json()
                        raw = (((groq_data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
                        success = bool(raw)
                        if not success: last_gemini_error += "; Groq empty response"
                    else:
                        last_gemini_error += f"; Groq HTTP {groq_res.status_code}: {groq_res.text[:180]}"
            except Exception as groq_err:
                last_gemini_error += f"; Groq: {str(groq_err)[:180]}"

        if not success or not raw:
            raise Exception("❌ ဘာသာပြန်ခြင်း မအောင်မြင်ပါ။ စမ်းသပ်အောင်မြင်ထားသော Gemini Model များနှင့် Groq အားလုံး မအောင်မြင်ပါ။ API error: " + last_gemini_error +
                            "\n💡 Key, Model availability နှင့် Quota/RPM ကို စစ်ဆေးပါ။")

        script_part = raw
        if "SCRIPT:" in raw:
            parts = raw.split("SCRIPT:")
            script_part = parts[-1].strip()
            front = parts[0]
            
            if i == 0:
                title_match = re.search(r'TITLE:\s*(.*)', front, re.IGNORECASE)
                if title_match and title_match.group(1).strip():
                    story_title = title_match.group(1).strip()
                    
                hook_match = re.search(r'HOOK:\s*(.*)', front, re.IGNORECASE)
                if hook_match and hook_match.group(1).strip():
                    story_hook = hook_match.group(1).strip()
        
        lines = script_part.split('\n')
        for line in lines:
            m_line = re.search(r'\[?\**(\d+)\**\]?[:\.\-\s]+(.*)', line.strip())
            if m_line and m_line.group(2).strip(): 
                translated_dict[int(m_line.group(1))] = m_line.group(2).strip()

        full_translated_text += script_part + "\n\n"
        _batch_total = max(1, (len(speech_indices) + 15) // 16)
        _batch_done = min(_batch_total, (i // 16) + 1)
        if update_status_func:
            _pct = 10 + int(_batch_done * 70 / _batch_total)
            await update_status_func(f"PROGRESS|AI Script|{_pct}|ဘာသာပြန် Batch {_batch_done}/{_batch_total} ပြီးပါပြီ")

    if speech_indices and not translated_dict:
        raise Exception("❌ Recap အသံစာသား မရရှိပါ။ Gemini/Groq မှ စာသားမပြန်ပေးပါ။")
    if speech_indices:
        missing_recap = [idx for idx in speech_indices if not translated_dict.get(idx, "").strip()]
        if missing_recap:
            raise Exception("❌ Whisper တွေ့ရှိသော စကားပြောအပိုင်းအချို့အတွက် Recap စာသား မရရှိပါ။ Missing segment: " + ", ".join(map(str, missing_recap[:12])))

    # Do not invent an AI opening hook/title. Keep a neutral title; the movie itself starts immediately.
    story_title = "🎬 Movie Recap"
    story_hook = ""
    story_hashtags = "#MovieRecap #BurmeseRecap #SANMA"

    sub_lang = user_sub_lang.get(user_id, "my")
    translated_dict_secondary = {}
    hybrid_original_dialogue = user_original_intro_mode.get(user_id, True)
    # Subtitle translation is intentionally skipped. If subtitles are enabled,
    # show the original Whisper transcript only; do not make extra Gemini calls.
    original_dialogue_subtitles = {
        idx: str(timeline_data[idx].get("text", "")).strip()
        for idx in speech_indices if str(timeline_data[idx].get("text", "")).strip()
    } if hybrid_original_dialogue else {}
    original_dialogue_subtitles_en = {}
    gap_recap_dict = {}
    gap_recap_subtitles = {}
    gap_recap_subtitles_my = {}
    if update_status_func:
        await update_status_func("PROGRESS|AI Script|90|Whisper စကားပြောအပိုင်းများအတွက် Recap အသံစာသား ပြီးပါပြီ။ Subtitle ဘာသာပြန်ခြင်း မလုပ်ပါ။")

    if update_status_func: 
        await update_status_func("၄။ 🗣️ နောက်ခံအသံများ ထုတ်လုပ်နေပါသည် (TTS Engine)...")

    audio_files_map = {}; tts_semaphore = asyncio.Semaphore(8); selected_rate = voice_config.get("rate", "+15%")
    audio_routing_plan = build_audio_routing_plan(timeline_data, translated_dict, hybrid_original_dialogue)

    async def _extract_original_audio_chunk(idx, seg, path):
        """Preserve the source soundtrack/dialogue whenever no recap VO is scheduled."""
        path = os.path.splitext(path)[0] + ".wav"
        start = max(0.0, float(seg.get("start", 0.0)))
        duration = max(0.1, float(seg.get("end", start)) - start)
        await asyncio.to_thread(
            run_ffmpeg,
            ['ffmpeg', '-y', '-ss', f"{start:.3f}", '-i', input_video,
             '-t', f"{duration:.3f}", '-vn', '-ac', '2', '-ar', '44100',
             '-c:a', 'pcm_s16le', path],
            label=f"original_audio_{idx}"
        )
        if not os.path.isfile(path) or os.path.getsize(path) < 100:
            raise RuntimeError(f"Original audio chunk {idx} ကို ထုတ်ယူမရပါ။ အသံတိတ်ဖိုင်နဲ့ အစားမထိုးပါ။")
        audio_files_map[idx] = path

    async def generate_audio_chunk(idx, seg):
        path = f"temp/chunk_audio_{user_id}_{idx}_{time.time_ns()}.mp3"
        expected_duration = max(0.1, float(seg.get("end", 0)) - float(seg.get("start", 0)))
        route = audio_routing_plan[idx]["source"] if idx < len(audio_routing_plan) else "original"
        if hybrid_original_dialogue:
            # The route plan is authoritative: recap = VO only; original = full source soundtrack.
            if route != "recap":
                await _extract_original_audio_chunk(idx, seg, path)
                return
            source_narration = audio_routing_plan[idx]["recap_text"]
        else:
            source_narration = translated_dict.get(idx, "")
            if not source_narration or not source_narration.strip():
                await asyncio.to_thread(create_silent_audio, expected_duration, path)
                audio_files_map[idx] = path
                return
        clean_text = re.sub(r'[\[\]{}()<>~*#_]', '', source_narration).strip()
        if len(clean_text) < 2:
            if hybrid_original_dialogue:
                await _extract_original_audio_chunk(idx, seg, path)
            else:
                await asyncio.to_thread(create_silent_audio, expected_duration, path); audio_files_map[idx] = path
            return
        
        c_voice = voice_config["voice"]; c_pitch = voice_config["pitch"]
        if is_multi_voice:
            if idx % 2 != 0:
                if voice_config["gender"] == "male": c_voice = "my-MM-NilarNeural"; c_pitch = "+5Hz"
                else: c_voice = "my-MM-ThihaNeural"; c_pitch = "-5Hz"
        
        async with tts_semaphore:
            rendered = False
            for attempt in range(3):
                try:
                    await edge_tts.Communicate(text=clean_text, voice=c_voice, rate=selected_rate, pitch=c_pitch).save(path)
                    if os.path.exists(path) and os.path.getsize(path) > 500:
                        rendered = True
                        break
                except Exception:
                    await asyncio.sleep(1.0)
            if not rendered:
                raise RuntimeError(f"Edge TTS chunk {idx} မအောင်မြင်ပါ။ အသံအလွတ်ဖြင့် အစားမထိုးဘဲ ရပ်လိုက်ပါသည်။")
            await asyncio.to_thread(add_natural_sentence_pause, path, 0.16)
            audio_files_map[idx] = path

    _audio_total = max(1, len(timeline_data))
    _audio_completed = 0
    async def _tracked_audio_chunk(idx, seg):
        nonlocal _audio_completed
        await generate_audio_chunk(idx, seg)
        audio_path = audio_files_map.get(idx)
        if not audio_path or not os.path.isfile(audio_path) or os.path.getsize(audio_path) < 100:
            raise RuntimeError(f"Audio chunk {idx} ထုတ်လုပ်မှု မအောင်မြင်ပါ။")
        duration = await asyncio.to_thread(get_media_duration, audio_path)
        if duration <= 0.05:
            raise RuntimeError(f"Audio chunk {idx} ကြာချိန် မမှန်ပါ။")
        _audio_completed += 1
        if update_status_func:
            pct = int(_audio_completed * 100 / _audio_total)
            await update_status_func(f"PROGRESS|Audio|{pct}|အသံအပိုင်း {_audio_completed}/{_audio_total} ပြီးပါပြီ")

    await asyncio.gather(*[_tracked_audio_chunk(idx, seg) for idx, seg in enumerate(timeline_data)])

    if update_status_func: 
        await update_status_func("၅။ 🎬 ဗီဒီယိုနှင့် အသံကို ပေါင်းစပ်နေပါသည် (FFmpeg Synchronization & Rendering)...")
        await update_status_func("PROGRESS|Render|0|Video/Audio အပိုင်းများ ပြင်ဆင်နေသည်...")

    ordered_idxs = [idx for idx in range(len(timeline_data)) if idx in audio_files_map]
    target_durs = _compute_frame_synced_durations([get_media_duration(audio_files_map[idx]) for idx in ordered_idxs], CHUNK_FRAME_RATE)
    target_dur_map = dict(zip(ordered_idxs, target_durs))

    # Keep the existing 100–700% control responsive without overdriving every
    # chunk; square-root scaling gives a smoother perceived-volume range.
    narration_gain = math.sqrt(max(1.0, min(7.0, float(user_voice_volume.get(user_id, 300)) / 100.0)))
    _render_job_token = f"{user_id}_{time.time_ns()}"
    ffmpeg_args = [(idx, float(timeline_data[idx]["start"]), float(timeline_data[idx]["end"]), input_video,
                    audio_files_map[idx], target_dur_map[idx], p_form, p_res, do_flip, do_bypass,
                    narration_gain, _render_job_token,
                    (audio_routing_plan[idx]["source"] == "original" if idx < len(audio_routing_plan) else True))
                   for idx in ordered_idxs]

    async def _render_chunk_progress(done, total):
        if update_status_func:
            _pct = int(done * 80 / max(total, 1))
            await update_status_func(f"PROGRESS|Render|{_pct}|Render အပိုင်း {done}/{total} ပြီးပါပြီ")

    chunk_results = await run_all_chunks(ffmpeg_args, _render_chunk_progress)
    ffmpeg_inputs = [res[1] for res in chunk_results if res[1] is not None]
    if len(ffmpeg_inputs) != len(ordered_idxs):
        raise Exception(f"Video/Audio Render အပိုင်း {len(ffmpeg_inputs)}/{len(ordered_idxs)} သာအောင်မြင်ပါသည်။ Sync ပျက်နိုင်သဖြင့် အပိုင်းပျောက်ပြီး ဆက်မပေါင်းတော့ပါ။")
    if not ffmpeg_inputs:
        raise Exception("ဗီဒီယို Timeline ချိန်ညှိမှု မအောင်မြင်ပါ။")

    concat_list_path = f"temp/list_{user_id}_{time.time_ns()}.txt"
    with open(concat_list_path, "w", encoding="utf-8") as f_list:
        for vid in ffmpeg_inputs: f_list.write(f"file '{os.path.abspath(vid)}'\n")

    # Sync Fix: Ensure concat output remains as .ts format briefly for perfectly contiguous audio bounds
    merge_temp = f"temp/merge_temp_{user_id}_{time.time_ns()}.ts"
    meta_flags = ['-map_metadata', '-1', '-map_chapters', '-1'] if do_bypass else []
    await asyncio.to_thread(run_ffmpeg, ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_list_path] + meta_flags + ['-c', 'copy', '-fflags', '+genpts', '-avoid_negative_ts', 'make_zero', merge_temp], label="concat_merge")
    if update_status_func:
        await update_status_func("PROGRESS|Render|80|Final Video/Audio mux နှင့် encode လုပ်နေသည်... (Final encode stage)")

    dim_w, dim_h = get_video_dimensions(p_form, p_res); sub_segments = []; cursor = 0.0
    for idx, seg in enumerate(timeline_data):
        if idx not in target_dur_map:
            continue
        # Use the same frame-synced timeline as the rendered audio.
        dur = target_dur_map[idx]
        if sub_enabled:
            if hybrid_original_dialogue:
                # Only the recap voice gets Burmese captions. Original-audio intervals
                # are intentionally subtitle-free, even if Whisper detected speech.
                route = audio_routing_plan[idx]["source"] if idx < len(audio_routing_plan) else "original"
                seg_text = translated_dict.get(idx, "").strip() if route == "recap" else ""
                if seg_text:
                    sub_segments.extend(
                        split_subtitle_text_chronologically(
                            unicodedata.normalize("NFC", seg_text), cursor, cursor + dur,
                            max_chars=14, space_delimited=True
                        )
                    )
            elif seg.get("is_speech"):
                source_dict = translated_dict_secondary if translated_dict_secondary else translated_dict
                seg_text = source_dict.get(idx, "").strip()
                if seg_text:
                    space_delim = sub_lang not in ["zh", "ja", "ko"]
                    sub_segments.extend(
                        split_subtitle_text_chronologically(
                            unicodedata.normalize("NFC", seg_text), cursor, cursor + dur,
                            max_chars=14, space_delimited=space_delim
                        )
                    )
        cursor += dur

    sub_y_percent = user_sub_y.get(user_id, 82)
    sub_color = user_sub_color.get(user_id, "#FFD700")
    job_dir = f"temp/subjob_{user_id}_{time.time_ns()}"; os.makedirs(job_dir, exist_ok=True)
    
    sub_font_fam = get_font_for_language(user_id, sub_lang)
    title_font_fam = get_font_for_language(user_id, target_voice_lang)

    subs_ass_path = None
    if sub_segments:
        subs_json_path = os.path.join(job_dir, "subs.json")
        with open(subs_json_path, "w", encoding="utf-8") as f: json.dump(sub_segments, f, ensure_ascii=False)
        generate_subtitle_srt_file(sub_segments, os.path.join(job_dir, "subs.srt"))
        subs_ass_path = generate_subtitle_ass_file(subs_json_path, job_dir, TW=dim_w, TH=dim_h, sub_y_percent=sub_y_percent, sub_color=sub_color, font_fam=sub_font_fam, font_size=selected_font_size, sub_lang=sub_lang, anim_sub=is_anim_sub)

    title_path = None
    if user_title_mode.get(user_id, True) and story_title and story_title.strip():
        title_path = os.path.join(job_dir, f"title_{user_id}.png")
        title_img = QImage(dim_w, dim_h, QImage.Format_ARGB32); title_img.fill(Qt.transparent); _t_painter = QPainter(title_img)
        try:
            _t_painter.setRenderHint(QPainter.Antialiasing); _t_painter.setRenderHint(QPainter.TextAntialiasing)
            _title_side_margin = int(dim_w * 0.10); _box_w = dim_w - (_title_side_margin * 2); _box_y = int(dim_h * 0.02); _box_h = int(dim_h * 0.16)
            _draw_hook_title(_t_painter, title_font_fam, story_title.strip(), _title_side_margin, _box_y, _box_w, _box_h, max_pt=60, min_pt=30)
        finally: _t_painter.end()
        title_img.save(title_path, "PNG")

    speech_segs = [s for s in timeline_data if s.get("is_speech") and s.get("text", "").strip()]
    highlight_time = (max(speech_segs, key=lambda s: s["end"] - s["start"])["start"] + max(speech_segs, key=lambda s: s["end"] - s["start"])["end"]) / 2.0 if speech_segs else None

    # Thumbnail generation disabled by request: MP4 output must not depend on image API/quota.
    tb_img_path = None

    blur_y_percent = user_blur_y.get(user_id, 82); blur_filter_str = ""; cur_label = "[0:v]"
    if user_blur_mode.get(user_id, False):
        blur_filter_str, cur_label = get_blur_mask_filter(
            "[0:v]", y_position_percent=blur_y_percent,
            width_percent=user_blur_width.get(user_id, 100),
            top_extra=user_blur_top_extra.get(user_id, 0),
            bottom_extra=user_blur_bottom_extra.get(user_id, 0))

    wm_text = user_wm_text.get(user_id, "MyRecap"); wm_pos = user_wm_pos.get(user_id, "bounce")
    if wm_pos == "topleft": wm_filter = f"drawtext=text='{wm_text}':fontcolor=white@0.8:fontsize=36:x=20:y=20:box=1:boxcolor=black@0.4:boxborderw=5"
    elif wm_pos == "topright": wm_filter = f"drawtext=text='{wm_text}':fontcolor=white@0.8:fontsize=36:x=w-tw-20:y=20:box=1:boxcolor=black@0.4:boxborderw=5"
    elif wm_pos == "bottom": wm_filter = f"drawtext=text='{wm_text}':fontcolor=white@0.8:fontsize=36:x=(w-tw)/2:y=h-th-20:box=1:boxcolor=black@0.4:boxborderw=5"
    else: wm_filter = f"drawtext=text='{wm_text}':fontcolor=white@0.4:fontsize=36:x='20+(w-tw-40)*(0.5+0.5*sin(t/2.5))':y='20+(h-th-40)*(0.5+0.5*cos(t/3.5))':box=1:boxcolor=black@0.15:boxborderw=5"

    watermarked_temp = f"temp/watermarked_{user_id}_{time.time_ns()}.mp4"
    user_logo_path = f"temp/logo_{user_id}.png"; user_bgm_path = f"temp/bgm_{user_id}.mp3"
    inputs = ['-i', merge_temp]; next_input_idx = 1
    
    logo_input_idx = None
    if os.path.exists(user_logo_path): inputs += ['-i', user_logo_path]; logo_input_idx = next_input_idx; next_input_idx += 1
        
    title_input_idx = None
    if title_path and os.path.exists(title_path): inputs += ['-loop', '1', '-i', title_path]; title_input_idx = next_input_idx; next_input_idx += 1

    bgm_input_idx = None; actual_bgm_path = user_bgm_path if os.path.exists(user_bgm_path) else DEFAULT_BGM_FILE
    has_bgm = actual_bgm_path is not None and os.path.exists(actual_bgm_path)
    if has_bgm: inputs += ['-stream_loop', '-1', '-i', actual_bgm_path]; bgm_input_idx = next_input_idx; next_input_idx += 1

    filter_parts = []
    if blur_filter_str: filter_parts.append(blur_filter_str)

    if subs_ass_path and os.path.exists(subs_ass_path):
        safe_ass_path = subs_ass_path.replace('\\', '/').replace(':', '\\:'); safe_font_dir = os.getcwd().replace('\\', '/').replace(':', '\\:')
        filter_parts.append(f"{cur_label}ass='{safe_ass_path}':fontsdir='{safe_font_dir}'[vid_with_subs]"); cur_label = "[vid_with_subs]"

    if title_input_idx is not None: filter_parts.append(f"{cur_label}[{title_input_idx}:v]overlay=0:0[vid_with_title]"); cur_label = "[vid_with_title]"
    
    if user_wm_mode.get(user_id, True):
        filter_parts.append(f"{cur_label}{wm_filter}[vid_wm]")
        cur_label = "[vid_wm]"
        
    if logo_input_idx is not None: filter_parts.append(f"[{logo_input_idx}:v]scale=-1:80[logo]"); filter_parts.append(f"{cur_label}[logo]overlay=W-w-20:20[vid_wm_logo]"); cur_label = "[vid_wm_logo]"

    if is_prog_bar:
        total_d = max(0.1, sum(target_dur_map.values()))
        prog_str = f"{cur_label}drawbox=x=0:y=ih-12:w='iw*(t/{total_d:.2f})':h=12:color=#FF0000@0.9:t=fill[vid_prog]"
        filter_parts.append(prog_str)
        cur_label = "[vid_prog]"

    audio_map_out = "[a_clean]"

    try:
        merged_dur = await asyncio.to_thread(get_media_duration, merge_temp)
    except:
        merged_dur = total_video_duration

    # Reset audio timestamps and enforce exact mux duration to prevent cut-off/drift.
    filter_parts.append(f"[0:a]aresample=44100:async=1:first_pts=0,apad,atrim=0:{merged_dur:.3f},asetpts=PTS-STARTPTS[a_clean]")
    if has_bgm:
        filter_parts.append(f"[a_clean]volume=1.5[a_main];[{bgm_input_idx}:a]aresample=44100,volume=0.15,asetpts=PTS-STARTPTS[a_bgm];[a_main][a_bgm]amix=inputs=2:duration=first:dropout_transition=2,alimiter=limit=0.95[a_mixed]")
        audio_map_out = "[a_mixed]"

    # If no video filter was applied, map the input stream directly. Bracketed
    # labels such as [0:v] are valid only for outputs created inside filter_complex.
    video_map_out = cur_label if cur_label != "[0:v]" else "0:v:0"
    # Do not use -shortest; audio is already padded/trimmed to the measured video duration.
    await asyncio.to_thread(run_ffmpeg, ['ffmpeg', '-y'] + inputs + ['-t', f"{merged_dur:.3f}", '-filter_complex', ";".join(filter_parts), '-map', video_map_out, '-map', audio_map_out] + meta_flags + ['-fflags', '+bitexact'] + video_encoder_args(preset='medium', quality=28) + ['-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '96k', watermarked_temp], label="final_render")

    speed_multiplier = SPEED_MULTIPLIERS.get(user_speed_val, 1.0)
    if abs(speed_multiplier - 1.0) > 0.001:
        await asyncio.to_thread(run_ffmpeg, ['ffmpeg', '-y', '-i', watermarked_temp, '-filter_complex', f"[0:v]setpts={1.0 / speed_multiplier:.4f}*PTS[v];[0:a]atempo={speed_multiplier:.3f}[a]", '-map', '[v]', '-map', '[a]'] + meta_flags + ['-fflags', '+bitexact'] + video_encoder_args(preset='medium', quality=28) + ['-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '96k', '-ar', '44100', '-ac', '2', output_video_path], label="final_speed_adjust")
        if os.path.exists(watermarked_temp): os.remove(watermarked_temp)
    else: os.replace(watermarked_temp, output_video_path)

    # Validate the delivered MP4 has both streams and no large A/V duration mismatch.
    probe = await asyncio.to_thread(
        subprocess.run,
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_type,duration', '-of', 'json', output_video_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if probe.returncode != 0:
        raise RuntimeError("Final MP4 ကို ffprobe ဖြင့် စစ်ဆေးမရပါ။")
    probe_data = json.loads(probe.stdout or "{}")
    stream_types = {st.get("codec_type") for st in probe_data.get("streams", [])}
    if not {"video", "audio"}.issubset(stream_types):
        raise RuntimeError("Final MP4 တွင် Video သို့မဟုတ် Audio Stream ပျောက်နေပါသည်။")
    fmt_dur = float((probe_data.get("format") or {}).get("duration") or 0)
    stream_durs = [float(st.get("duration")) for st in probe_data.get("streams", []) if st.get("duration")]
    if fmt_dur <= 0 or (stream_durs and max(stream_durs) - min(stream_durs) > 1.5):
        raise RuntimeError("Final MP4 ရဲ့ Video/Audio ကြာချိန် မညီပါ။ Sync စစ်ဆေးမှု မအောင်မြင်ပါ။")

    for f in list(audio_files_map.values()) + ffmpeg_inputs + [merge_temp]:
        if os.path.exists(f): os.remove(f)
    if os.path.exists(concat_list_path): os.remove(concat_list_path)
    if os.path.isdir(job_dir): import shutil; shutil.rmtree(job_dir, ignore_errors=True)

    return story_title, story_hook, story_hashtags, None, cursor

bot = TelegramClient(MemorySession(), API_ID, API_HASH)

@bot.on(events.NewMessage(pattern=r"^/start(?:@\w+)?(?:\s|$)"))
async def start(event):
    if not _claim_incoming_event(event): return
    user_id = event.sender_id

    # Telegram /start may be handled twice if the script/handler is started twice.
    # Ignore repeated start messages from the same user within a short window.
    now = time.monotonic()
    last_start = _START_DEBOUNCE.get(user_id, 0.0)
    if now - last_start < _START_DEBOUNCE_SECONDS:
        logging.warning("Ignored duplicate /start from user %s", user_id)
        return
    _START_DEBOUNCE[user_id] = now
    # Periodically prune old entries so this cache stays small.
    if len(_START_DEBOUNCE) > 1000:
        _START_DEBOUNCE.clear()
        _START_DEBOUNCE[user_id] = now
    
    is_valid, error_msg = await verify_telegram_id(user_id)
    if not is_valid:
        await event.respond(error_msg)
        return

    sender = await event.get_sender()
    sender_name = getattr(sender, 'first_name', '') or getattr(sender, 'username', '') or f"User_{user_id}"

    if user_id not in user_stats: user_stats[user_id] = {"name": sender_name, "count": 0, "last_active": time.strftime("%Y-%m-%d %H:%M:%S")}
    # Screenshot-matched defaults for new users.
    if user_id not in user_voices: user_voices[user_id] = "v1"
    if user_id not in user_speeds: user_speeds[user_id] = "1.1x"
    if user_id not in user_platform: user_platform[user_id] = "tt"
    if user_id not in user_res: user_res[user_id] = "1080"
    if user_id not in user_font: user_font[user_id] = DEFAULT_FONT_FILE
    if user_id not in user_font_size: user_font_size[user_id] = 45
    if user_id not in user_sub_lang: user_sub_lang[user_id] = "my"
    if user_id not in user_main_lang: user_main_lang[user_id] = "Burmese" 
    if user_id not in user_flip_mode: user_flip_mode[user_id] = False
    if user_id not in user_bypass_mode: user_bypass_mode[user_id] = False
    if user_id not in user_preview_mode: user_preview_mode[user_id] = True
    if user_id not in user_sub_color: user_sub_color[user_id] = "#FFD700"
    if user_id not in user_multivoice: user_multivoice[user_id] = False
    if user_id not in user_autotrim: user_autotrim[user_id] = False
    if user_id not in user_animsub: user_animsub[user_id] = False
    if user_id not in user_progressbar: user_progressbar[user_id] = False
    if user_id not in user_video_type: user_video_type[user_id] = "movie"
    if user_id not in user_wm_mode: user_wm_mode[user_id] = False
    if user_id not in user_title_mode: user_title_mode[user_id] = False
    if user_id not in user_sub_mode: user_sub_mode[user_id] = True
    if user_id not in user_voice_volume: user_voice_volume[user_id] = 400
    if user_id not in user_translation_style: user_translation_style[user_id] = 2
    if user_id not in user_original_intro_mode: user_original_intro_mode[user_id] = True

    await event.respond(
        "🎬 **AI Video Narration Bot (v93.0)**\n\n"
        "✨ **🌍 Dual Subtitle:** မြန်မာ+အင်္ဂလိပ် စာတန်းထိုး တွဲပေါ်စနစ် ပါဝင်ပါပြီ။\n"
        "✨ **✂️ Movie/Series Mode:** ဇာတ်လမ်းပုံစံ ရွေးချယ်နိုင်ပါပြီ။\n"
        "👇 အောက်ပါ Menu များမှတဆင့် စိတ်ကြိုက် ပြင်ဆင်နိုင်ပါသည်-",
        buttons=get_main_menu_buttons(user_id)
    )

@bot.on(events.CallbackQuery(pattern=b"menu_wm"))
async def toggle_wm(event):
    uid = event.sender_id
    user_wm_mode[uid] = not user_wm_mode.get(uid, False)
    status = "✅ ဖွင့်ထားသည်" if user_wm_mode[uid] else "❌ ပိတ်ထားသည်"
    try: await event.edit(f"💧 **Watermark:** {status}\n(သင့်ရဲ့ Watermark ကို Video ပေါ်တွင် ဖော်ပြပေးမည်/ဖျောက်ထားမည် ဖြစ်သည်။)", buttons=get_main_menu_buttons(uid))
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_advanced"))
async def menu_advanced(event):
    try: await event.edit("⚙️ **Advanced Effects & Settings**\n\nအောက်ပါ အထူးပြုလုပ်ချက်များကို စိတ်ကြိုက် ဖွင့်/ပိတ် နိုင်ပါသည်-", buttons=get_advanced_menu_buttons(event.sender_id))
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_settings"))
async def show_settings(event):
    uid = event.sender_id
    msg = "📋 **ကျွန်ုပ်၏ Settings များ**\n━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"📱 Size: {user_platform.get(uid, 'tt').upper()} | Resolution: {user_res.get(uid, '1080')}p\n"
    msg += f"🎙️ Voice: {user_voices.get(uid, 'v1')} | Speed: {user_speeds.get(uid, '1.1x')} | Volume: {user_voice_volume.get(uid, 400)}%\n"
    msg += f"🎭 Recap Style: {user_translation_style.get(uid, 2)}\n"
    msg += f"📝 Sub Lang: {user_sub_lang.get(uid, 'my')} | Color: {user_sub_color.get(uid, '#FFD700')} | Font Size: {user_font_size.get(uid, 45)}\n"
    msg += f"🏷️ Title Overlay: {'ON' if user_title_mode.get(uid, False) else 'OFF'}\n"
    msg += f"💧 Watermark: {'ON' if user_wm_mode.get(uid, False) else 'OFF'}\n"
    msg += f"👁️ Preview: {'ON' if user_preview_mode.get(uid, True) else 'OFF'}\n"
    intro_on = user_original_intro_mode.get(uid, True)
    msg += f"🎬 Original Dialogue: {'ON (Original Audio + Translated Subs / No-Dialogue = Recap VO)' if intro_on else 'OFF'}\n"
    msg += f"🤖 Gemini Model: {user_gemini_model.get(uid, 'auto')}\\n"
    msg += "━━━━━━━━━━━━━━━━━━━━\n"
    buttons = [
        [Button.inline("🎬 Original Dialogue: " + ("✅ ON" if intro_on else "❌ OFF"), b"toggle_original_intro")],
        [Button.inline("🤖 Gemini Model ရွေးရန်", b"menu_gemini_model")],
        [Button.inline("🔙 ပင်မစာမျက်နှာသို့ (Back)", b"menu_back")]
    ]
    try: await event.edit(msg, buttons=buttons)
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_gemini_model"))
async def show_gemini_model_menu(event):
    uid = event.sender_id
    available = list(GEMINI_MODEL_CANDIDATES)
    current = user_gemini_model.get(uid, "auto")
    buttons = [[Button.inline(("✅ " if current == "auto" else "") + "Auto Mode", b"gemmodel:auto")]]
    for model_id in available:
        label = GEMINI_MODEL_LABELS[model_id]
        buttons.append([Button.inline(("✅ " if current == model_id else "") + label, ("gemmodel:" + model_id).encode())])
    buttons.append([Button.inline("🔙 Settings သို့", b"menu_settings")])
    await event.edit(
        "🤖 **Gemini Model ရွေးချယ်မှု**\n"
        "အောင်မြင်ခဲ့သော Model ၃ ခုကိုသာ အသုံးပြုပါမည်။\n"
        "Auto Mode တွင် အစဉ်လိုက် အလိုအလျောက် ပြောင်းသုံးပါမည်။",
        buttons=buttons
    )

@bot.on(events.CallbackQuery(pattern=b"gemmodel:"))
async def set_gemini_model(event):
    uid = event.sender_id
    selected = event.data.decode("utf-8", "ignore").split(":", 1)[1]
    allowed = GEMINI_MODEL_CANDIDATES
    if selected != "auto" and selected not in allowed:
        await event.answer("မရရှိနိုင်သော Gemini Model ဖြစ်ပါသည်။", alert=True)
        return
    user_gemini_model[uid] = selected
    await event.answer("Gemini Model ပြောင်းပြီးပါပြီ။", alert=False)
    await show_gemini_model_menu(event)


@bot.on(events.CallbackQuery(pattern=b"toggle_original_intro"))
async def toggle_original_intro(event):
    uid = event.sender_id
    user_original_intro_mode[uid] = not user_original_intro_mode.get(uid, True)
    await event.answer("Setting updated", alert=False)
    await show_settings(event)

@bot.on(events.CallbackQuery(pattern=b"menu_vidtype"))
async def menu_vidtype(event):
    buttons = [
        [Button.inline("🎬 တပိုင်းတည်းအပြီး (Full Movie)", b"set_vidtype_movie")],
        [Button.inline("🎞️ ဇာတ်လမ်းအပိုင်း (Series / Part)", b"set_vidtype_series")],
        [Button.inline("🔙 နောက်သို့", b"menu_advanced")]
    ]
    try: await event.edit("👇 ဗီဒီယိုပုံစံကို ရွေးချယ်ပါ-", buttons=buttons)
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=r"set_vidtype_"))
async def set_vidtype(event):
    vtype = event.data.decode('utf-8').split("_")[2]
    user_video_type[event.sender_id] = vtype
    msg = "🎬 တပိုင်းတည်းအပြီး (Full Movie)" if vtype == "movie" else "🎞️ ဇာတ်လမ်းအပိုင်း (Series / Part)"
    try: await event.edit(f"✅ ဗီဒီယိုပုံစံကို **{msg}** သို့ ပြောင်းလဲလိုက်ပါပြီ။", buttons=get_advanced_menu_buttons(event.sender_id))
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_intl"))
async def menu_intl(event):
    buttons = [
        [Button.inline("🇬🇧 English Mode", b"set_intl_en")],
        [Button.inline("🇯🇵 Japanese Mode", b"set_intl_ja")],
        [Button.inline("🇹🇭 Thai Mode", b"set_intl_th")],
        [Button.inline("🇲🇲 Myanmar Mode (Default)", b"set_intl_my")],
        [Button.inline("🔙 နောက်သို့", b"menu_advanced")]
    ]
    try: await event.edit("🌍 **International Mode (Strict Sync)**\n\nဘာသာစကား တစ်ခုရွေးလိုက်ပါက အသံ၊ စာတန်းထိုး နှင့် Title အားလုံးကို ထိုဘာသာစကားဖြင့်သာ တင်းကျပ်စွာ အလိုအလျောက် ချိန်ညှိပြောင်းလဲပေးပါမည်။", buttons=buttons)
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=r"set_intl_"))
async def set_intl(event):
    lang = event.data.decode('utf-8').split("_")[2]
    uid = event.sender_id
    if lang == "en": user_voices[uid] = "v4"; user_sub_lang[uid] = "en"; user_main_lang[uid] = "English"
    elif lang == "ja": user_voices[uid] = "v14"; user_sub_lang[uid] = "ja"; user_main_lang[uid] = "Japanese"
    elif lang == "th": user_voices[uid] = "v2"; user_sub_lang[uid] = "th"; user_main_lang[uid] = "Thai"
    else: user_voices[uid] = "v1"; user_sub_lang[uid] = "my"; user_main_lang[uid] = "Burmese"
    try: await event.edit(f"✅ Strict Mode ကို **{lang.upper()}** သို့ ပြောင်းလဲလိုက်ပါပြီ။", buttons=get_advanced_menu_buttons(uid))
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_preview"))
async def toggle_preview(event):
    uid = event.sender_id; user_preview_mode[uid] = not user_preview_mode.get(uid, True)
    status = "✅ ဖွင့်ထားသည်" if user_preview_mode[uid] else "❌ ပိတ်ထားသည်"
    try: await event.edit(f"👁️ **Auto-Preview Mode:** {status}\n(ပိတ်ထားပါက Video တင်လိုက်သည်နှင့် Blur/Sub နေရာချိန်စရာမလိုဘဲ Auto-Queue သို့ တန်းဝင်သွားမည်ဖြစ်သည်။)", buttons=get_main_menu_buttons(uid))
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_size"))
async def menu_size(event):
    buttons = [[Button.inline("📱 TT/Reels (9:16)", b"set_size_tt")], [Button.inline("🖥️ YouTube (16:9)", b"set_size_yt")], [Button.inline("🔲 Facebook (1:1)", b"set_size_fb")], [Button.inline("🔙 နောက်သို့", b"menu_back")]]
    try: await event.edit("📱 ဗီဒီယိုထွက်ရှိမည့် Format Size ကို ရွေးချယ်ပါ-", buttons=buttons)
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=r"set_size_"))
async def set_size(event):
    user_platform[event.sender_id] = event.data.decode('utf-8').split("_")[2]
    try: await event.edit(f"✅ Video Size ကို ပြောင်းလဲလိုက်ပါပြီ။", buttons=get_main_menu_buttons(event.sender_id))
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_res"))
async def menu_res(event):
    buttons = [[Button.inline("HD 720p (Default)", b"set_res_720")], [Button.inline("FHD 1080p (High Quality)", b"set_res_1080")], [Button.inline("🔙 နောက်သို့", b"menu_back")]]
    try: await event.edit("📺 ဗီဒီယို Resolution ကို ရွေးချယ်ပါ-", buttons=buttons)
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=r"set_res_"))
async def set_res(event):
    user_res[event.sender_id] = event.data.decode('utf-8').split("_")[2]
    try: await event.edit(f"✅ Resolution ကို ပြောင်းလဲလိုက်ပါပြီ။", buttons=get_main_menu_buttons(event.sender_id))
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_voice"))
async def menu_voice(event):
    buttons = []
    buttons.append([Button.inline("🔊 လက်ရှိရွေးထားသော အသံကို စမ်းနားထောင်ရန်", b"test_voice_btn")])
    row = []
    for k, v in VOICE_MODES.items():
        row.append(Button.inline(v["name"], f"set_v_{k}".encode('utf-8')))
        if len(row) == 2: buttons.append(row); row = []
    if row: buttons.append(row)
    buttons.append([Button.inline("🔙 နောက်သို့", b"menu_back")])
    try: await event.edit("👇 အသံပုံစံ ကို ရွေးချယ်ပေးပါ-", buttons=buttons)
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"test_voice_btn"))
async def test_voice_btn(event):
    uid = event.sender_id; v_idx = user_voices.get(uid, "v1"); voice_config = VOICE_MODES.get(v_idx, VOICE_MODES["v1"])
    await event.answer("အသံကို ထုတ်လုပ်နေပါသည်... ခေတ္တစောင့်ပါ။")
    sample_text = "မင်္ဂလာပါ။ ယခုအသံကို ဘာသာစကားမျိုးစုံ ဖတ်နိုင်သော AI ဖြင့် အစမ်းဖတ်ပြနေခြင်း ဖြစ်ပါတယ်။ နားဆင်ပေးတဲ့အတွက် ကျေးဇူးတင်ပါတယ်။"
    out_path = f"temp/test_voice_{uid}_{int(time.time())}.mp3"
    try:
        communicate = edge_tts.Communicate(text=sample_text, voice=voice_config["voice"], rate=voice_config["rate"], pitch=voice_config["pitch"])
        await communicate.save(out_path)
        await bot.send_file(event.chat_id, out_path, caption=f"🎧 **Voice Test**\n🗣️ {voice_config['name']}")
        os.remove(out_path)
    except Exception as e:
        await event.respond(f"❌ Error: {str(e)}")
        if os.path.exists(out_path): os.remove(out_path)

@bot.on(events.CallbackQuery(pattern=r"set_v_"))
async def change_voice(event):
    voice_key = event.data.decode('utf-8').split("_", 2)[2]; user_voices[event.sender_id] = voice_key
    try: await event.edit(f"✅ အသံပုံစံ ပြောင်းလဲလိုက်ပါပြီ။", buttons=get_main_menu_buttons(event.sender_id))
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_speed"))
async def menu_speed(event):
    buttons = [[Button.inline("1.0x", b"set_speed_1.0x"), Button.inline("1.1x", b"set_speed_1.1x")], [Button.inline("1.2x", b"set_speed_1.2x"), Button.inline("1.3x", b"set_speed_1.3x")], [Button.inline("1.4x", b"set_speed_1.4x")], [Button.inline("🔙 နောက်သို့", b"menu_back")]]
    try: await event.edit("⚡ **Audio Speed ရွေးချယ်ရန်**", buttons=buttons)
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=r"set_speed_"))
async def change_speed(event):
    speed_val = event.data.decode('utf-8').split("_")[2]; user_speeds[event.sender_id] = speed_val
    try: await event.edit(f"✅ အမြန်နှုန်း ပြောင်းလဲလိုက်ပါပြီ။", buttons=get_main_menu_buttons(event.sender_id))
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_multivoice"))
async def toggle_multivoice(event):
    uid = event.sender_id; user_multivoice[uid] = not user_multivoice.get(uid, False)
    status = "✅ ဖွင့်ထားသည်" if user_multivoice[uid] else "❌ ပိတ်ထားသည်"
    try: await event.edit(f"🗣️ **Multi-Voice (အသံခွဲပြောခြင်း):** {status}\n(ယောက်ျားလေး/မိန်းကလေး အသံနှစ်မျိုး အလိုအလျောက် ခွဲဖတ်ပေးမည်)", buttons=get_advanced_menu_buttons(uid))
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_autotrim"))
async def toggle_autotrim(event):
    uid = event.sender_id; user_autotrim[uid] = not user_autotrim.get(uid, False)
    status = "✅ ဖွင့်ထားသည်" if user_autotrim[uid] else "❌ ပိတ်ထားသည်"
    try: await event.edit(f"✂️ **Auto Trim (Series Mode):** {status}\n(အသံမပါတဲ့ တိတ်ဆိတ်နေတဲ့ အခန်းတွေကို လုံးဝဖျက်ချလိုက်ပြီး အသံပါတဲ့အခန်းတွေကိုပဲ ဆက်တိုက်ဖတ်ပေးသွားပါမည်။)", buttons=get_advanced_menu_buttons(uid))
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_animsub"))
async def toggle_animsub(event):
    uid = event.sender_id; user_animsub[uid] = not user_animsub.get(uid, False)
    status = "✅ ဖွင့်ထားသည်" if user_animsub[uid] else "❌ ပိတ်ထားသည်"
    try: await event.edit(f"🌟 **Animated Subtitle (အသက်ဝင်စာတန်းထိုး):** {status}\n(စာတန်းထိုးလေးတွေက ငြိမ်နေတာမဟုတ်ဘဲ အနီးကပ်ပြသလိုမျိုး ဖောင်းပြီး ပေါ်လာမည်ဖြစ်သည်။)", buttons=get_advanced_menu_buttons(uid))
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_progressbar"))
async def toggle_progressbar(event):
    uid = event.sender_id; user_progressbar[uid] = not user_progressbar.get(uid, False)
    status = "✅ ဖွင့်ထားသည်" if user_progressbar[uid] else "❌ ပိတ်ထားသည်"
    try: await event.edit(f"⏳ **Progress Bar (အချိန်ပြဘားတန်း):** {status}\n(ဗီဒီယိုရဲ့အောက်ခြေမှာ အနီရောင်အချိန်ပြ ဘားတန်းလေး တဖြည်းဖြည်း ပြည့်သွားအောင် ထည့်ပေးမည်ဖြစ်သည်။)", buttons=get_advanced_menu_buttons(uid))
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_sub"))
async def toggle_sub(event):
    uid = event.sender_id; user_sub_mode[uid] = not user_sub_mode.get(uid, True) 
    status = "✅ ဖွင့်ထားသည်" if user_sub_mode[uid] else "❌ ပိတ်ထားသည်"
    try: await event.edit(f"📝 **စာတန်းထိုး:** {status}\n(၁၅-၂၀ လုံးအတွင်း၊ စာလုံးမကွဲအောင် အတိအကျ ညှိပေးထားသော စနစ်ဖြင့် ပေါ်ပေးပါမည်။)", buttons=get_main_menu_buttons(uid))
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_subcolor"))
async def menu_subcolor(event):
    buttons = []; row = []
    for val, name in SUB_COLOR_CHOICES:
        safe_val = val.replace("#", "HEX")
        row.append(Button.inline(name, f"set_subcol_{safe_val}".encode('utf-8')))
        if len(row) == 2: buttons.append(row); row = []
    if row: buttons.append(row)
    buttons.append([Button.inline("🔙 နောက်သို့", b"menu_back")])
    try: await event.edit("🎨 **စာတန်းထိုးအတွက် အရောင်ရွေးချယ်ပါ-**", buttons=buttons)
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=r"set_subcol_"))
async def set_subcol(event):
    val = event.data.decode('utf-8').split("_")[2]; val = val.replace("HEX", "#")
    user_sub_color[event.sender_id] = val
    user_sub_mode[event.sender_id] = True 
    try: await event.edit(f"✅ Subtitle အရောင်ကို ပြောင်းလဲလိုက်ပါပြီ။\n(စာတန်းထိုးစနစ်ကိုပါ အလိုအလျောက် ဖွင့်ပေးလိုက်ပါပြီ)", buttons=get_main_menu_buttons(event.sender_id))
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_flip"))
async def toggle_flip(event):
    uid = event.sender_id; user_flip_mode[uid] = not user_flip_mode.get(uid, False)
    status = "✅ ဖွင့်ထားသည်" if user_flip_mode[uid] else "❌ ပိတ်ထားသည်"
    try: await event.edit(f"↔️ **Video ဘယ်ညာလှန်ခြင်း (Flip):** {status}\n(Edit အတွက် ရုပ်ထွက်ကို Horizontal လှန်ပေးမည်ဖြစ်သည်။)", buttons=get_advanced_menu_buttons(uid))
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_bypass"))
async def toggle_bypass(event):
    uid = event.sender_id; user_bypass_mode[uid] = not user_bypass_mode.get(uid, False)
    status = "✅ ဖွင့်ထားသည်" if user_bypass_mode[uid] else "❌ ပိတ်ထားသည်"
    try: await event.edit(f"🛡️ **Auto Bypass Edit:** {status}\n(Copyright ရှောင်ရန် Camera Motion နှင့် Meta Data များကို အလိုအလျောက် ဖြတ်ထုတ်ပေးပါမည်။)", buttons=get_advanced_menu_buttons(uid))
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_blur"))
async def toggle_blur(event):
    uid = event.sender_id; user_blur_mode[uid] = not user_blur_mode.get(uid, False)
    status = "✅ ဖွင့်ထားသည်" if user_blur_mode[uid] else "❌ ပိတ်ထားသည်"
    try: await event.edit(f"🌫️ **Auto Blur Mask:** {status}\n(ဖွင့်ထားပါက မူရင်း video အောက်ခြေရှိ စာတန်းဟောင်းများကို အလိုအလျောက် ဝါးဖျောက်ပေးပါမည်။)", buttons=get_advanced_menu_buttons(uid))
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_title"))
async def toggle_title(event):
    uid = event.sender_id; user_title_mode[uid] = not user_title_mode.get(uid, False)
    status = "✅ ဖွင့်ထားသည်" if user_title_mode[uid] else "❌ ပိတ်ထားသည်"
    try: await event.edit(f"🏷️ **Video Title Overlay:** {status}\n(ဖွင့်ထားပါက AI ထုတ်ပေးတဲ့ Title ကို video ထိပ်မှာ တစ်ခါတည်း အမြဲကပ်ပြပေးပါမည်။)", buttons=get_main_menu_buttons(uid))
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_sublang"))
async def menu_sublang(event):
    buttons = []
    for code, name in SUB_LANGUAGES.items():
        disp_name = name
        if code == "en":
            disp_name = "English (အသံမြန်မာ၊ စာတန်းထိုး Eng)"
        elif code == "my":
            disp_name = "မြန်မာစာ (Default)"
        elif code == "my_en":
            disp_name = "မြန်မာ + English (စာတန်းထိုး ၂ မျိုးတွဲ)"
        buttons.append([Button.inline(f"🌐 {disp_name}", f"set_sublang_{code}".encode('utf-8'))])
    buttons.append([Button.inline("🔙 နောက်သို့", b"menu_advanced")])
    try: await event.edit("🌐 **စာတန်းထိုး ဘာသာစကား ရွေးချယ်ပါ**\n\n(Int'l Mode မပြောင်းထားသရွေ့ အသံက မြန်မာလိုပဲ အမြဲထွက်ပါမည်)", buttons=buttons)
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=r"set_sublang_"))
async def set_sublang(event):
    code = event.data.decode('utf-8').replace("set_sublang_", "")
    if code in SUB_LANGUAGES: user_sub_lang[event.sender_id] = code
    try: await event.edit(f"✅ Subtitle ဘာသာစကားကို **{SUB_LANGUAGES.get(code, code)}** သို့ ပြောင်းလဲလိုက်ပါပြီ။", buttons=get_advanced_menu_buttons(event.sender_id))
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_font"))
async def menu_font(event):
    buttons = []
    for f in AVAILABLE_FONTS:
        disp = os.path.basename(f)
        buttons.append([Button.inline(f"🔤 {disp}", f"set_font_{AVAILABLE_FONTS.index(f)}".encode('utf-8'))])
    buttons.append([Button.inline("🔙 နောက်သို့", b"menu_back")])
    try: await event.edit("🔤 စာတန်းထိုးနှင့် Title အတွက် Font ရွေးချယ်ပါ-", buttons=buttons)
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=r"set_font_"))
async def change_font(event):
    idx = int(event.data.decode('utf-8').split("_")[2])
    if 0 <= idx < len(AVAILABLE_FONTS): user_font[event.sender_id] = AVAILABLE_FONTS[idx]
    try: await event.edit(f"✅ Font ပြောင်းလဲလိုက်ပါပြီ။", buttons=get_main_menu_buttons(event.sender_id))
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_fontsize"))
async def menu_fontsize(event):
    buttons = []; row = []
    for val, name in FONT_SIZE_CHOICES:
        row.append(Button.inline(f"📏 {name}", f"set_fontsize_{val}".encode('utf-8')))
        if len(row) == 3: buttons.append(row); row = []
    if row: buttons.append(row)
    buttons.append([Button.inline("🔙 နောက်သို့", b"menu_back")])
    try: await event.edit("📏 စာတန်းထိုး အရွယ်အစား ရွေးချယ်ပါ-", buttons=buttons)
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=r"set_fontsize_"))
async def set_fontsize(event):
    val = int(event.data.decode('utf-8').split("_")[2])
    user_font_size[event.sender_id] = val
    try: await event.edit(f"✅ စာတန်းထိုး Font Size ကို **{val}** သို့ ပြောင်းလဲသတ်မှတ်လိုက်ပါပြီ။", buttons=get_main_menu_buttons(event.sender_id))
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_voicevolume"))
async def menu_voicevolume(event):
    uid = event.sender_id
    buttons = []
    row = []
    for val in (100, 200, 300, 400, 500, 600, 700):
        label = f"{'✅ ' if user_voice_volume.get(uid, 400) == val else ''}{val}%"
        row.append(Button.inline(label, f"set_voicevolume_{val}".encode()))
        if len(row) == 3: buttons.append(row); row = []
    if row: buttons.append(row)
    buttons.append([Button.inline("🔙 နောက်သို့", b"menu_back")])
    await event.edit(f"🔊 **Narration အသံအကျယ်**\nလက်ရှိ: {user_voice_volume.get(uid, 400)}%\n100–700% ကိုရွေးပါ။ 500% အထက်မှာ limiter ကြောင့် အသံအမြင့်ဆုံးပိုင်းကို ကာကွယ်ညှိပေးပါမည်။", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=r"set_voicevolume_"))
async def set_voicevolume(event):
    val = int(event.data.decode().rsplit("_", 1)[1])
    if val in (100, 200, 300, 400, 500, 600, 700): user_voice_volume[event.sender_id] = val
    await menu_voicevolume(event)

@bot.on(events.CallbackQuery(pattern=b"menu_trstyle"))
async def menu_trstyle(event):
    uid = event.sender_id
    styles = [(1,"ပါကျဲဘာသာပြန်ပုံစံ"),(2,"ဇာတ်ကြမ်း"),(3,"ပေါက်ကရ"),(4,"ဟာသ"),(5,"ဒရာမာ"),(6,"စစ်ကား"),(7,"ပေါင်းစပ်"),(8,"ဆန်းမာ")]
    buttons = []
    for sid, name in styles:
        prefix = "✅ " if user_translation_style.get(uid, 2) == sid else ""
        buttons.append([Button.inline(prefix + name, f"set_trstyle_{sid}".encode())])
    buttons.append([Button.inline("🔙 ပင်မစာမျက်နှာသို့", b"menu_back")])
    await event.edit("🎭 **ဘာသာပြန်ဇာတ်ကြောင်းစတိုင် ရွေးချယ်ပါ**\nရွေးချယ်မှုသည် နောက်ထုတ်မည့် Recap များတွင် အသုံးပြုပါမည်။", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=r"set_trstyle_"))
async def set_trstyle(event):
    sid = int(event.data.decode().rsplit("_", 1)[1])
    if sid in range(1, 9): user_translation_style[event.sender_id] = sid
    await menu_trstyle(event)

@bot.on(events.CallbackQuery(pattern=b"menu_help"))
async def menu_help(event):
    msg = ("ℹ️ **အထူးပြုလုပ်ချက်များ ထည့်သွင်းနည်း**\n\n💧 **Watermark ပြောင်းရန်:** Caption တွင် `/setwm [စာသား]` ဟု ရိုက်ပို့ပါ။\n🖼️ **Logo ပုံထည့်ရန်:** Logo ပုံကို ရွေးပြီး Caption တွင် `/setlogo` ဟု ရိုက်ပို့ပါ။ (ဖျက်လိုပါက `/removelogo`)\n🎵 **နောက်ခံ BGM တီးလုံးထည့်ရန်:** ၄မိနစ်စာခန့်ရှိသော Audio ဖိုင်ကိုရွေးပြီး Caption တွင် `/setbgm` ဟု ရိုက်ပို့ပါ။ Video အရှည်အတိုင်း အလိုလို Loop လုပ်ပေးပါမည်။ (ဖျက်လိုပါက `/removebgm`)")
    try: await event.edit(msg, buttons=[[Button.inline("🔙 နောက်သို့", b"menu_back")]])
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_back"))
async def menu_back(event):
    try: await event.edit("👇 စိတ်ကြိုက် ပြင်ဆင်ရန် အောက်ပါခလုတ်များကို အသုံးပြုပါ-", buttons=get_main_menu_buttons(event.sender_id))
    except MessageNotModifiedError: pass

@bot.on(events.NewMessage(pattern="/setwm"))
async def set_wm_text(event):
    if not _claim_incoming_event(event): return
    text = event.text.replace("/setwm", "").strip()
    if text: user_wm_text[event.sender_id] = text; await event.respond(f"✅ Watermark စာသားကို **{text}** သို့ ပြောင်းလဲလိုက်ပါပြီ။", buttons=get_main_menu_buttons(event.sender_id))

@bot.on(events.NewMessage(pattern="/setlogo"))
async def set_logo(event):
    if not _claim_incoming_event(event): return
    if event.photo: await event.download_media(file=f"temp/logo_{event.sender_id}.png"); await event.respond("✅ **Logo ပုံစံသစ်ကို အောင်မြင်စွာ မှတ်သားလိုက်ပါပြီ။**", buttons=get_main_menu_buttons(event.sender_id))
    else: await event.respond("⚠️ `/setlogo` ကို ပုံ (Photo) တစ်ပုံနှင့်အတူ Caption တွင်တွဲ၍ ပို့ပေးပါ။")

@bot.on(events.NewMessage(pattern="/removelogo"))
async def remove_logo(event):
    if not _claim_incoming_event(event): return
    path = f"temp/logo_{event.sender_id}.png"
    if os.path.exists(path): os.remove(path); await event.respond("✅ ကိုယ်ပိုင် Logo ကို ပယ်ဖျက်လိုက်ပါပြီ။", buttons=get_main_menu_buttons(event.sender_id))
    else: await event.respond("⚠️ မှတ်သားထားသော Logo မရှိသေးပါ။")

@bot.on(events.NewMessage(pattern="/setbgm"))
async def set_bgm(event):
    if not _claim_incoming_event(event): return
    if event.audio or event.document: await event.download_media(file=f"temp/bgm_{event.sender_id}.mp3"); await event.respond("✅ **နောက်ခံတီးလုံး (BGM) ကို အောင်မြင်စွာ မှတ်သားလိုက်ပါပြီ။**", buttons=get_main_menu_buttons(event.sender_id))
    else: await event.respond("⚠️ `/setbgm` ကို Audio ဖိုင် (mp3/wav) နှင့်အတူ Caption တွင်တွဲ၍ ပို့ပေးပါ။")

@bot.on(events.NewMessage(pattern="/removebgm"))
async def remove_bgm(event):
    if not _claim_incoming_event(event): return
    path = f"temp/bgm_{event.sender_id}.mp3"
    if os.path.exists(path): os.remove(path); await event.respond("✅ BGM ကို ပယ်ဖျက်လိုက်ပါပြီ။", buttons=get_main_menu_buttons(event.sender_id))
    else: await event.respond("⚠️ မှတ်သားထားသော BGM မရှိသေးပါ။")

@bot.on(events.NewMessage(pattern="/admin1999"))
async def admin_stats(event):
    if not _claim_incoming_event(event): return
    if event.sender_id != ADMIN_ID and getattr(await event.get_sender(), 'username', '').lower() != "kopyae131019": return
    if not user_stats: await event.respond("📊 လက်ရှိတွင် အသုံးပြုထားသော မှတ်တမ်း မရှိသေးပါ။"); return
    
    total_users = len(user_stats)
    total_videos = sum(u["count"] for u in user_stats.values())
    today_str = time.strftime("%Y-%m-%d")
    today_active = sum(1 for u in user_stats.values() if str(u["last_active"]).startswith(today_str))
    
    msg = f"👑 **ADMIN DASHBOARD** 👑\n━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"👥 စုစုပေါင်း အသုံးပြုသူ: **{total_users}** ဦး\n"
    msg += f"🎬 စုစုပေါင်း ထုတ်လုပ်မှု: **{total_videos}** ပုဒ်\n"
    msg += f"📅 ယနေ့ အသုံးပြုသူ: **{today_active}** ဦး\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    msg += "📝 **နောက်ဆုံး ထုတ်လုပ်မှု မှတ်တမ်း (Recent 15):**\n"
    if job_logs:
        for log in job_logs: msg += f"{log}\n"
    else:
        msg += "- မရှိသေးပါ -\n"
        
    msg += "\n🏆 **Top Users:**\n"
    for idx, (uid, data) in enumerate(sorted(user_stats.items(), key=lambda x: x[1]["count"], reverse=True)[:15], 1): 
        msg += f"**{idx}. {data['name']}**\n   └ 🎬: **{data['count']}** ပုဒ် | 🕒: {data['last_active']}\n"
    await event.respond(msg)

@bot.on(events.NewMessage(pattern=r"^/setkey(?:\s|$)"))
async def set_user_key(event):
    if not _claim_incoming_event(event): return
    parts = event.text.split(maxsplit=1)
    if len(parts) < 2:
        await event.respond(
            "🔑 **API Key များကို သီးခြားထည့်နိုင်ပါသည်**\n"
            "Gemini: `/setkey GEMINI_KEY1,GEMINI_KEY2,...`\n"
            "Groq: `/setkey groq GROQ_KEY1,GROQ_KEY2,...`\n"
            "Key တစ်ခုတည်းလည်း ထည့်နိုင်ပြီး အများဆုံး ၅ ခုအထိ လက်ခံပါသည်။"
        )
        return

    payload = parts[1].strip()
    is_groq_command = payload.lower().startswith("groq ")
    if is_groq_command:
        raw_keys = payload[5:].strip()
        keys = [k.strip() for k in re.split(r"[,\s]+", raw_keys) if k.strip()]
        keys = list(dict.fromkeys(k for k in keys if k.startswith("gsk_")))[:5]
        if not keys:
            await event.respond("❌ Groq Key မတွေ့ပါ။ `/setkey groq gsk_...,...` ပုံစံသုံးပါ။")
            return
        current = user_keys.get(event.sender_id, {"gemini": "", "groq": ""})
        current_gemini = current.get("gemini", "") if isinstance(current, dict) else str(current)
        user_keys[event.sender_id] = {"gemini": current_gemini, "groq": ",".join(keys)}
        await event.respond(
            f"✅ Groq API Key {len(keys)} ခု သိမ်းပြီးပါပြီ။\n"
            "🔁 တစ်ခု Authentication မအောင်မြင်ပါက နောက် Key ကို အလိုအလျောက် စမ်းသုံးပါမည်။"
        )
        return

    # Gemini keys: comma-separated; accept one through five.
    keys = [k.strip() for k in re.split(r"[,\s]+", payload) if k.strip()]
    keys = list(dict.fromkeys(k for k in keys if k.startswith(("AIza", "AQ."))))[:5]
    if not keys:
        await event.respond("❌ Gemini Key မတွေ့ပါ။ `/setkey GEMINI_KEY1,GEMINI_KEY2` ပုံစံသုံးပါ။")
        return
    current = user_keys.get(event.sender_id, {"gemini": "", "groq": ""})
    current_groq = current.get("groq", "") if isinstance(current, dict) else ""
    user_keys[event.sender_id] = {"gemini": ",".join(keys), "groq": current_groq}
    user_gemini_available_models[event.sender_id] = list(GEMINI_MODEL_CANDIDATES)
    user_gemini_model.setdefault(event.sender_id, "auto")
    await event.respond(
        f"✅ Gemini API Key {len(keys)} ခု သိမ်းပြီးပါပြီ။\n"
        "🔁 Key တစ်ခု quota/auth error ဖြစ်ပါက နောက် Key သို့ အလိုအလျောက် ပြောင်းသုံးပါမည်။\n"
        "Groq ထည့်ရန် `/setkey groq GROQ_KEY1,GROQ_KEY2` ကို သီးခြားပို့ပါ။"
    )

@bot.on(events.NewMessage(pattern="/queue"))
async def queue_status(event):
    if not _claim_incoming_event(event): return
    q = user_queues.get(event.sender_id); pending = q.qsize() if q else 0
    if user_queue_active.get(event.sender_id, False): await event.respond(f"🔁 လက်ရှိ Auto-Queue ဖြင့် ဆောင်ရွက်နေပါသည်။ တန်းစီနေသည့် အလုပ်: **{pending}** ခု")
    else: await event.respond("✅ လက်ရှိ Queue ထဲတွင် ဆောင်ရွက်နေသည့် အလုပ် မရှိပါ။")

@bot.on(events.NewMessage(pattern="/resetqueue"))
async def reset_queue_cmd(event):
    if not _claim_incoming_event(event): return
    if event.sender_id != ADMIN_ID and getattr(await event.get_sender(), 'username', '').lower() != "kopyae131019": 
        return
    global CURRENT_ACTIVE_USER, GLOBAL_RENDER_LOCK
    CURRENT_ACTIVE_USER = ""
    GLOBAL_RENDER_LOCK = asyncio.Semaphore(2)
    for uid in user_queues:
        while not user_queues[uid].empty():
            try: user_queues[uid].get_nowait()
            except: pass
        user_queue_active[uid] = False
    await event.respond("✅ **ရှင်းလင်းပြီးပါပြီ။** Queue အားလုံးနှင့် Lock ကို အတင်းဖျက်ချ (Reset) လိုက်ပါပြီ။ Bot ကို ပုံမှန်အတိုင်း ပြန်သုံးနိုင်ပါပြီ။")

# Global duplicate-update guard used by every incoming message handler.
# It prevents duplicate processing within this Python process.
_HANDLED_INCOMING_EVENTS = set()
_HANDLED_INCOMING_EVENTS_MAX = 10000

def _claim_incoming_event(event):
    try:
        key = (int(getattr(event, "chat_id", 0) or 0), int(getattr(event, "id", 0) or 0), int(getattr(event, "sender_id", 0) or 0))
        if key[1] == 0:
            return True
        if key in _HANDLED_INCOMING_EVENTS:
            logging.warning("Duplicate Telegram update ignored: chat=%s message=%s sender=%s", *key)
            return False
        _HANDLED_INCOMING_EVENTS.add(key)
        if len(_HANDLED_INCOMING_EVENTS) > _HANDLED_INCOMING_EVENTS_MAX:
            # Retain a bounded recent window without clearing the newest key.
            _HANDLED_INCOMING_EVENTS.clear()
            _HANDLED_INCOMING_EVENTS.add(key)
        return True
    except Exception:
        return True

@bot.on(events.NewMessage)
async def handle_message(event):
    if event.text and event.text.startswith('/'): return
    if not _claim_incoming_event(event): return
    user_id = event.sender_id
    is_valid, error_msg = await verify_telegram_id(user_id)
    if not is_valid:
        await event.respond(error_msg)
        return

    doc = getattr(event, "document", None)
    doc_mime = (getattr(doc, "mime_type", "") or "").lower() if doc else ""
    doc_name = ""
    if doc:
        for attr in (getattr(doc, "attributes", []) or []):
            if hasattr(attr, "file_name") and attr.file_name:
                doc_name = attr.file_name.lower()
                break
    video_exts = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpeg", ".mpg")
    is_vid_file = bool(event.video or (doc and (doc_mime.startswith("video/") or doc_name.endswith(video_exts))))
    url = event.text.strip() if event.text else ""
    
    is_yt = False if is_vid_file else is_youtube_link(url)
    if not is_yt and not is_vid_file: return

    if user_id not in user_keys: await event.respond("🔑 ကျေးဇူးပြု၍ အရင်ဆုံး `/setkey GEMINI_KEY1,GEMINI_KEY2` နှင့် `/setkey groq GROQ_KEY1,GROQ_KEY2` ဖြင့် Keys များ ထည့်ပေးပါ..."); return

    clean_url = ""
    if is_yt:
        match = re.search(r'(https?://[^\s]+)', url)
        clean_url = match.group(1) if match else url
    else:
        clean_url = url

    await start_position_calibration(event, user_id, clean_url, is_yt)

async def start_position_calibration(event, user_id, url, is_yt):
    status = await event.respond("📥 Preview အတွက် Video ကို ရယူနေပါသည်...")
    input_video = f"temp/calib_{user_id}_{time.time_ns()}.mp4"
    try:
        if is_yt: await asyncio.to_thread(download_youtube_video, url, input_video)
        else: await event.download_media(file=input_video)
    except Exception as e:
        try: await status.edit(f"❌ Video ရယူ၍မရပါ: {e}")
        except Exception: pass
        if os.path.exists(input_video): os.remove(input_video)
        return

    try:
        vid_dur = await asyncio.to_thread(get_media_duration, input_video)
        if vid_dur > 1200:
            await status.edit("❌ **ဗီဒီယို အရှည်ကြီးဖြစ်နေပါသည်။**\n\nတခြားသူများ အကြာကြီး စောင့်ဆိုင်းရမှုမှ ကာကွယ်ရန် မိနစ် ၂၀ ထက်ကျော်လွန်သော ဗီဒီယိုများကို လက်မခံပါ။ ကျေးဇူးပြု၍ ဗီဒီယိုကို ဖြတ်ပြီးမှ ပြန်တင်ပေးပါ။")
            if os.path.exists(input_video): os.remove(input_video)
            return
    except Exception as e: pass 

    try:
        cropped = await asyncio.to_thread(apply_content_crop_if_needed, input_video, f"calib_{user_id}")
        if cropped != input_video: os.remove(input_video); input_video = cropped
    except Exception as e: logging.warning(f"content crop step failed: {e}")

    if not user_preview_mode.get(user_id, True):
        try: await status.edit("📥 **Auto-Preview ပိတ်ထားသဖြင့် Auto-Queue သို့ တိုက်ရိုက် ထည့်သွင်းနေပါသည်...**")
        except Exception: pass
        if user_id not in user_queues: user_queues[user_id] = asyncio.Queue()
        await user_queues[user_id].put({"orig_event": event, "input_video": input_video})
        pending = user_queues[user_id].qsize()
        if not user_queue_active.get(user_id, False):
            user_queue_active[user_id] = True
            asyncio.create_task(auto_recap_worker(user_id))
        else:
            await event.respond(f"📥 **Auto-Queue** ထဲသို့ ထည့်သွင်းလိုက်ပါပြီ (နောက်ထပ် **{pending}** ခု စောင့်ဆိုင်းနေပါသည်)။")
        return

    p_form = user_platform.get(user_id, "yt"); p_res = user_res.get(user_id, "720")
    dim_w, dim_h = get_video_dimensions(p_form, p_res)
    raw_frame = f"temp/frame_{user_id}.jpg"
    user_preview_percent[user_id] = 0.30
    try: await asyncio.to_thread(extract_preview_frame, input_video, raw_frame, dim_w, dim_h, percent=user_preview_percent[user_id])
    except Exception as e:
        try: await status.edit(f"❌ Preview ပုံ ထုတ်၍မရပါ: {e}")
        except Exception: pass
        if os.path.exists(input_video): os.remove(input_video)
        return

    if user_id not in user_blur_y: user_blur_y[user_id] = 82
    if user_id not in user_sub_y: user_sub_y[user_id] = 82

    user_pending_calib[user_id] = {"input_video": input_video, "url": url, "is_yt": is_yt, "orig_event": event}
    try: await status.delete()
    except Exception: pass
    await send_calibration_preview(event.chat_id, user_id)

def _calib_buttons():
    return [
        [Button.inline("⬆️Blur အပေါ်အများ", b"calib_blur_up_big"), Button.inline("⬇️Blur အောက်အများ", b"calib_blur_down_big")],
        [Button.inline("⬆️Blur အပေါ်နည်း", b"calib_blur_up_small"), Button.inline("⬇️Blur အောက်အနည်း", b"calib_blur_down_small")],
        [Button.inline("↔️ Blur အကျယ် -5%", b"calib_blur_right_narrow"), Button.inline("↔️ Blur အကျယ် +5%", b"calib_blur_right_wide")],
        [Button.inline("⬆️Blur အပေါ်အကျယ်", b"calib_blur_top_wide"), Button.inline("⬇️Blur အောက်အကျယ်", b"calib_blur_bottom_wide")],
        [Button.inline("⬇️Blur အပေါ်အကျဉ်", b"calib_blur_top_narrow"), Button.inline("⬇️Blur အောက်အကျဉ်", b"calib_blur_bottom_narrow")],
        [Button.inline("⏮ Preview ပုံ -5s", b"calib_preview_prev"), Button.inline("Preview ပုံ +5s ⏭", b"calib_preview_next")],
        [Button.inline("📝 Sub ⬆️", b"calib_sub_up"), Button.inline("📝 Sub ⬇️", b"calib_sub_down")],
        [Button.inline("▶️ ဗီဒီယို စတင်ရန်", b"calib_confirm"), Button.inline("❌ ပယ်ဖျက်ရန်", b"calib_cancel")]
    ]

def _calib_caption(user_id):
    calib = user_pending_calib.get(user_id, {})
    try:
        dur = get_media_duration(calib.get("input_video", ""))
        preview_seconds = max(0.0, min(dur, dur * user_preview_percent.get(user_id, 0.30)))
    except Exception:
        preview_seconds = 0.0
    return (f"🖼️ Preview Frame: **{preview_seconds:.1f}s**\n"
            f"🌫️ Blur နေရာ: **{user_blur_y.get(user_id, 82)}%** | အကျယ်: **{user_blur_width.get(user_id, 100)}%** | "
            f"အပေါ်ချဲ့: **{user_blur_top_extra.get(user_id, 0)}%** | အောက်ချဲ့: **{user_blur_bottom_extra.get(user_id, 0)}%**\n"
            f"📝 Subtitle နေရာ: **{user_sub_y.get(user_id, 82)}%**\n"
            "အနီရောင်ဇုန် = Blur၊ အဝါရောင်ဇုန် = Subtitle\n"
            "Blur ခလုတ်များဖြင့် နေရာ/အကျယ်ကိုချိန်ပြီး 'ဗီဒီယို စတင်ရန်' နှိပ်ပါ။")

async def send_calibration_preview(chat_id, user_id):
    raw_frame = f"temp/frame_{user_id}.jpg"; preview_path = f"temp/calib_preview_{user_id}.jpg"
    font_file = user_font.get(user_id, DEFAULT_FONT_FILE)
    await asyncio.to_thread(render_calibration_preview, raw_frame, preview_path, user_blur_y.get(user_id, 82), user_sub_y.get(user_id, 82), user_blur_mode.get(user_id, False), font_file, user_blur_width.get(user_id, 100), user_blur_top_extra.get(user_id, 0), user_blur_bottom_extra.get(user_id, 0))
    msg = await bot.send_file(chat_id, preview_path, caption=_calib_caption(user_id), buttons=_calib_buttons())
    calib = user_pending_calib.get(user_id)
    if calib: calib["msg_id"] = msg.id

async def update_calibration_preview(event):
    uid = event.sender_id
    if uid not in user_pending_calib: await event.answer("⚠️ Session သက်တမ်းကုန်သွားပါပြီ။ Video/Link ကို ပြန်ပို့ပေးပါ။", alert=True); return
    raw_frame = f"temp/frame_{uid}.jpg"; preview_path = f"temp/calib_preview_{uid}.jpg"
    font_file = user_font.get(uid, DEFAULT_FONT_FILE)
    await asyncio.to_thread(render_calibration_preview, raw_frame, preview_path, user_blur_y.get(uid, 82), user_sub_y.get(uid, 82), user_blur_mode.get(uid, False), font_file, user_blur_width.get(uid, 100), user_blur_top_extra.get(uid, 0), user_blur_bottom_extra.get(uid, 0))
    try: await event.edit(file=preview_path, text=_calib_caption(uid), buttons=_calib_buttons())
    except MessageNotModifiedError: pass
    await event.answer()


async def change_preview_frame(event, delta):
    uid = event.sender_id
    calib = user_pending_calib.get(uid)
    if not calib:
        await event.answer("⚠️ Preview session မရှိတော့ပါ။ Video ကို ပြန်ပို့ပါ။", alert=True)
        return
    video = calib.get("input_video")
    try:
        dur = await asyncio.to_thread(get_media_duration, video)
        current = user_preview_percent.get(uid, 0.30) * dur
        target = max(0.3, min(max(0.3, dur - 0.3), current + delta))
        user_preview_percent[uid] = target / max(dur, 0.3)
        p_form = user_platform.get(uid, "yt"); p_res = user_res.get(uid, "720")
        dim_w, dim_h = get_video_dimensions(p_form, p_res)
        await asyncio.to_thread(extract_preview_frame, video, f"temp/frame_{uid}.jpg", dim_w, dim_h, percent=user_preview_percent[uid])
        await update_calibration_preview(event)
    except Exception as e:
        await event.answer(f"Preview ပြောင်းမရပါ: {str(e)[:120]}", alert=True)

@bot.on(events.CallbackQuery(pattern=b"calib_preview_prev"))
async def calib_preview_prev(event):
    await change_preview_frame(event, -5.0)

@bot.on(events.CallbackQuery(pattern=b"calib_preview_next"))
async def calib_preview_next(event):
    await change_preview_frame(event, 5.0)

@bot.on(events.CallbackQuery(pattern=b"calib_blur_up_big"))
async def calib_blur_up_big(event):
    uid = event.sender_id; user_blur_y[uid] = max(0, user_blur_y.get(uid, 82) - 8)
    await update_calibration_preview(event)

@bot.on(events.CallbackQuery(pattern=b"calib_blur_down_big"))
async def calib_blur_down_big(event):
    uid = event.sender_id; user_blur_y[uid] = min(88, user_blur_y.get(uid, 82) + 8)
    await update_calibration_preview(event)

@bot.on(events.CallbackQuery(pattern=b"calib_blur_up_small"))
async def calib_blur_up_small(event):
    uid = event.sender_id; user_blur_y[uid] = max(0, user_blur_y.get(uid, 82) - 1)
    await update_calibration_preview(event)

@bot.on(events.CallbackQuery(pattern=b"calib_blur_down_small"))
async def calib_blur_down_small(event):
    uid = event.sender_id; user_blur_y[uid] = min(88, user_blur_y.get(uid, 82) + 1)
    await update_calibration_preview(event)

@bot.on(events.CallbackQuery(pattern=b"calib_blur_narrow"))
async def calib_blur_narrow(event):
    uid = event.sender_id; user_blur_width[uid] = max(10, user_blur_width.get(uid, 100) - 5)
    await update_calibration_preview(event)

@bot.on(events.CallbackQuery(pattern=b"calib_blur_wide"))
async def calib_blur_wide(event):
    uid = event.sender_id; user_blur_width[uid] = min(100, user_blur_width.get(uid, 100) + 5)
    await update_calibration_preview(event)

@bot.on(events.CallbackQuery(pattern=b"calib_blur_top_wide"))
async def calib_blur_top_wide(event):
    uid = event.sender_id; user_blur_top_extra[uid] = min(30, user_blur_top_extra.get(uid, 0) + 3)
    user_blur_y[uid] = max(0, user_blur_y.get(uid, 82) - 3)
    await update_calibration_preview(event)

@bot.on(events.CallbackQuery(pattern=b"calib_blur_bottom_wide"))
async def calib_blur_bottom_wide(event):
    uid = event.sender_id; user_blur_bottom_extra[uid] = min(30, user_blur_bottom_extra.get(uid, 0) + 3)
    await update_calibration_preview(event)

@bot.on(events.CallbackQuery(pattern=b"calib_blur_right_narrow"))
async def calib_blur_right_narrow(event):
    uid = event.sender_id; user_blur_width[uid] = max(10, user_blur_width.get(uid, 100) - 5)
    await update_calibration_preview(event)

@bot.on(events.CallbackQuery(pattern=b"calib_blur_right_wide"))
async def calib_blur_right_wide(event):
    uid = event.sender_id; user_blur_width[uid] = min(100, user_blur_width.get(uid, 100) + 5)
    await update_calibration_preview(event)

@bot.on(events.CallbackQuery(pattern=b"calib_blur_left_narrow"))
async def calib_blur_left_narrow(event):
    uid = event.sender_id; user_blur_width[uid] = max(10, user_blur_width.get(uid, 100) - 5)
    await update_calibration_preview(event)

@bot.on(events.CallbackQuery(pattern=b"calib_blur_left_wide"))
async def calib_blur_left_wide(event):
    uid = event.sender_id; user_blur_width[uid] = min(100, user_blur_width.get(uid, 100) + 5)
    await update_calibration_preview(event)

@bot.on(events.CallbackQuery(pattern=b"calib_blur_top_narrow"))
async def calib_blur_top_narrow(event):
    uid = event.sender_id; user_blur_top_extra[uid] = max(-10, user_blur_top_extra.get(uid, 0) - 3)
    await update_calibration_preview(event)

@bot.on(events.CallbackQuery(pattern=b"calib_blur_bottom_narrow"))
async def calib_blur_bottom_narrow(event):
    uid = event.sender_id; user_blur_bottom_extra[uid] = max(-10, user_blur_bottom_extra.get(uid, 0) - 3)
    await update_calibration_preview(event)

@bot.on(events.CallbackQuery(pattern=b"calib_sub_up"))
async def calib_sub_up(event):
    uid = event.sender_id; user_sub_y[uid] = max(10, user_sub_y.get(uid, 82) - 3)
    await update_calibration_preview(event)

@bot.on(events.CallbackQuery(pattern=b"calib_sub_down"))
async def calib_sub_down(event):
    uid = event.sender_id; user_sub_y[uid] = min(90, user_sub_y.get(uid, 82) + 3)
    await update_calibration_preview(event)

@bot.on(events.CallbackQuery(pattern=b"calib_confirm"))
async def calib_confirm(event):
    uid = event.sender_id
    calib = user_pending_calib.pop(uid, None)
    if not calib: await event.answer("⚠️ Session သက်တမ်းကုန်သွားပါပြီ။ Video/Link ကို ပြန်ပို့ပေးပါ။", alert=True); return
    await event.answer("✅ Queue ထဲ ထည့်နေပါသည်...")
    try: await event.delete()
    except Exception: pass

    if uid not in user_queues: user_queues[uid] = asyncio.Queue()
    await user_queues[uid].put({"orig_event": calib["orig_event"], "input_video": calib["input_video"]})
    pending = user_queues[uid].qsize()

    if not user_queue_active.get(uid, False):
        user_queue_active[uid] = True; asyncio.create_task(auto_recap_worker(uid))
    else: await calib["orig_event"].respond(f"📥 **Auto-Queue** ထဲသို့ ထည့်သွင်းလိုက်ပါပြီ (နောက်ထပ် **{pending}** ခု စောင့်ဆိုင်းနေပါသည်)။")

@bot.on(events.CallbackQuery(pattern=b"calib_cancel"))
async def calib_cancel(event):
    uid = event.sender_id; calib = user_pending_calib.pop(uid, None)
    if calib and os.path.exists(calib["input_video"]): os.remove(calib["input_video"])
    frame_path = f"temp/frame_{uid}.jpg"
    if os.path.exists(frame_path): os.remove(frame_path)
    try: await event.edit(text="❌ ပယ်ဖျက်လိုက်ပါပြီ။", buttons=None)
    except MessageNotModifiedError: pass
    await event.answer()

def apply_original_intro_audio(original_video, rendered_video, user_id):
    """Deprecated: hybrid audio is now assembled per timeline interval.

    A fixed opening segment or scene-cut boundary would override the per-video
    dialogue/recap decision, so this compatibility function intentionally does nothing.
    """
    return rendered_video


async def process_recap_job(job_item, user_id):
    global CURRENT_ACTIVE_USER
    event = job_item["orig_event"]; input_video = job_item["input_video"]
    sender = await event.get_sender()
    sender_name = getattr(sender, 'first_name', '') or getattr(sender, 'username', '') or f"User_{user_id}"

    u_gemini = json.dumps(user_keys[user_id], ensure_ascii=False)
    v_idx = user_voices.get(user_id, "v1"); selected_voice_config = VOICE_MODES[v_idx]
    selected_speed = user_speeds.get(user_id, "1.1x")

    status = await event.respond("📥 စနစ်ကို စတင်နေပါသည်...")
    _job_clock = time.monotonic()
    _stage_clock = _job_clock
    _stage_name = "Video"
    _stage_elapsed = {"Video": 0.0, "AI Script": 0.0, "Audio": 0.0, "Render": 0.0, "Upload": 0.0}
    _stage_done = set()
    _stage_progress = {"Video": 0, "AI Script": 0, "Audio": 0, "Render": 0, "Upload": 0}
    _stage_notes = {}
    _stage_order = ["Video", "AI Script", "Audio", "Render", "Upload"]

    def _fmt_elapsed(seconds):
        seconds = max(0, int(seconds))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def _stage_time(name):
        extra = max(0.0, time.monotonic() - _stage_clock) if _stage_name == name else 0.0
        return _fmt_elapsed(_stage_elapsed[name] + extra)

    def _progress_line(name, label, active_note=None):
        done = name in _stage_done
        active = name == _stage_name and not done
        icon = "✅" if done else ("🔄" if active else "⌛")
        if done:
            detail, percent = "ပြီးပါပြီ", 100
        elif active:
            detail = active_note or _stage_notes.get(name, "လုပ်ဆောင်နေသည်...")
            percent = max(0, min(99, int(_stage_progress.get(name, 0))))
        else:
            detail, percent = "စောင့်ဆိုင်းနေသည်", 0
        filled = max(0, min(10, percent // 10))
        bar = "[" + "■" * filled + "□" * (10 - filled) + "]"
        return f"{label}: {icon} {detail} ({_stage_time(name)})\\n{bar} {percent}%"

    def _panel(active_note=None):
        total = _fmt_elapsed(time.monotonic() - _job_clock)
        rows = [
            "🎬 **Auto-Generator (Fast Edition) 😉**",
            _progress_line("Video", "📥 Video"),
            _progress_line("AI Script", "🧠 AI Script"),
            _progress_line("Audio", "🎙️ Audio"),
            _progress_line("Render", "🔄 Render", active_note if _stage_name == "Render" else None),
            _progress_line("Upload", "📤 Upload", active_note if _stage_name == "Upload" else None),
            f"⏱️ **Total time: {total}**",
        ]
        return "\n".join(rows)

    async def _set_stage(name, note=None):
        nonlocal _stage_clock, _stage_name
        if name != _stage_name:
            _stage_elapsed[_stage_name] += max(0.0, time.monotonic() - _stage_clock)
            _stage_done.add(_stage_name)
            _stage_progress[_stage_name] = 100
            _stage_name = name
            _stage_progress[name] = 0
            _stage_clock = time.monotonic()
        try:
            await status.edit(_panel(note))
        except Exception:
            pass

    async def update_status_func(text_msg):
        msg = str(text_msg)
        if msg.startswith("PROGRESS|"):
            try:
                _, stage, pct, note = msg.split("|", 3)
                if stage in _stage_progress:
                    _stage_progress[stage] = max(0, min(99, int(float(pct))))
                    _stage_notes[stage] = note
                    if stage != _stage_name:
                        await _set_stage(stage, note)
                    else:
                        try: await status.edit(_panel(note))
                        except Exception: pass
            except Exception as progress_err:
                logging.warning("Progress update ignored: %s", str(progress_err)[:120])
            return
        low = msg.lower()
        if "ဗီဒီယိုမှ အသံ" in msg or "extract audio" in low or "extracting audio" in low:
            await _set_stage("Video", "ဗီဒီယိုကို လက်ခံပြီး Audio ခွဲထုတ်နေသည်...")
        elif "stable whisper" in low or "transcrib" in low or "ဘာသာပြန်" in msg or "script" in low:
            await _set_stage("AI Script", "စာသားပြင်ဆင်နေသည်...")
        elif "tts engine" in low or "voice" in low or "အသံများ ထုတ်လုပ်" in msg or "အသံ (audio)" in msg:
            await _set_stage("Audio", "AI Voice အသံထုတ်နေသည်...")
        elif "ffmpeg synchronization" in low or "render" in low or "ဗီဒီယိုနှင့် အသံကို ပေါင်းစပ်" in msg or "original အသံမှ recap" in low:
            encoder_note = ("GPU ဖြင့် Video နှင့် Audio ပေါင်းနေသည်" if FFMPEG_ENCODER == "h264_nvenc"
                            else "GPU မရပါ၊ CPU ဖြင့် Video နှင့် Audio ပေါင်းနေသည်။ နည်းနည်းကြာမည်")
            await _set_stage("Render", encoder_note)
        else:
            try:
                await status.edit(_panel(msg))
            except Exception:
                pass

    voice_label = selected_voice_config["name"]
    output_video = f"temp/out_{user_id}_{time.time_ns()}.mp4"; extracted_audio_path = f"temp/extract_{user_id}_{time.time_ns()}.mp3" 

    try:
        await update_status_func("၁။ 📥 ဗီဒီယိုမှ အသံ (Audio) ကို စတင်ခွဲထုတ်နေပါသည်...")
        await asyncio.to_thread(extract_audio_ffmpeg, input_video, extracted_audio_path)
        
        if not os.path.exists(extracted_audio_path) or os.path.getsize(extracted_audio_path) < 1024:
            raise Exception("❌ ဗီဒီယိုတွင် အသံ (Audio) လုံးဝမပါဝင်သဖြင့် AI မှ နားထောင်၍မရနိုင်ပါ။ အသံပါသော ဗီဒီယိုကိုသာ တင်ပေးပါ။")
        try:
            extracted_dur = await asyncio.to_thread(get_media_duration, extracted_audio_path)
            if extracted_dur <= 0.5:
                raise Exception("❌ ဗီဒီယိုတွင် အသံ (Audio) လုံးဝမပါဝင်သဖြင့် AI မှ နားထောင်၍မရနိုင်ပါ။ အသံပါသော ဗီဒီယိုကိုသာ တင်ပေးပါ။")
        except Exception as e:
            if "Audio" in str(e): raise e
            else: raise Exception("❌ ဗီဒီယိုတွင် အသံ (Audio) လုံးဝမပါဝင်သဖြင့် AI မှ နားထောင်၍မရနိုင်ပါ။ အသံပါသော ဗီဒီယိုကိုသာ တင်ပေးပါ။")

        if GLOBAL_RENDER_LOCK.locked():
            try: await status.edit(f"⏳ **Global Queue တွင် ခေတ္တစောင့်ဆိုင်းနေပါသည်...**\n(လက်ရှိ ထုတ်လုပ်နေသူ: 👤 **{CURRENT_ACTIVE_USER}**)")
            except MessageNotModifiedError: pass
        
        async with GLOBAL_RENDER_LOCK:
            CURRENT_ACTIVE_USER = sender_name 
            try:
                story_title, story_hook, story_hashtags, tb_path, final_cursor_dur = await advanced_sync_pipeline(
                    extracted_audio_path, u_gemini, input_video, output_video, selected_voice_config, selected_speed, user_id, update_status_func
                )
                # Original dialogue preservation is handled per detected speech segment inside the timeline render.
            except Exception as pipeline_err:
                raise pipeline_err
            finally:
                CURRENT_ACTIVE_USER = "" 
        
        if os.path.exists(extracted_audio_path): os.remove(extracted_audio_path)
        
        if os.path.exists(output_video):
            await _set_stage("Upload", "ဆာဗာသို့ တင်နေသည်...")

            if user_id not in user_stats: user_stats[user_id] = {"name": sender_name, "count": 0, "last_active": ""}
            user_stats[user_id]["count"] += 1
            current_time_str = time.strftime("%Y-%m-%d %H:%M:%S")
            user_stats[user_id]["last_active"] = current_time_str
            job_logs.insert(0, f"⏱️ {current_time_str[11:]} - 👤 {sender_name}")
            if len(job_logs) > 15: job_logs.pop()

            file_size_mb = os.path.getsize(output_video) / (1024 * 1024)
            actual_dur = await asyncio.to_thread(get_media_duration, output_video)
            dur_mins = int(actual_dur // 60); dur_secs = int(actual_dur % 60)
            
            sub_status = "ဖွင့်ထားသည်" if user_sub_mode.get(user_id, True) else "ပိတ်ထားသည်"
            sub_lang_str = SUB_LANGUAGES.get(user_sub_lang.get(user_id, "my"), "မြန်မာ")
            p_res_str = user_res.get(user_id, "720"); p_form_str = user_platform.get(user_id, "yt").upper()
            
            ch_mid_m = int((actual_dur/2) // 60)
            ch_mid_s = int((actual_dur/2) % 60)
            chapters = f"⏱️ 00:00 - အစ\n⏱️ {ch_mid_m:02d}:{ch_mid_s:02d} - အလယ်ပိုင်း\n⏱️ {dur_mins:02d}:{dur_secs:02d} - ဇာတ်သိမ်း"

            caption_text = (
                f"🎬 **{story_title}**\n\n"
                f"{story_hashtags}\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Video Information**\n"
                f"⏱️ ကြာချိန်: {dur_mins}m {dur_secs}s\n"
                f"💾 ဖိုင်ဆိုဒ်: {file_size_mb:.2f} MB\n"
                f"📺 Resolution: {p_res_str}p ({p_form_str})\n"
                f"🎙️ အသံ: {voice_label} (Speed: {selected_speed}, Volume: {user_voice_volume.get(user_id, 300)}%)\n"
                f"📝 စာတန်းထိုး: {sub_status} ({sub_lang_str}) | Font: {user_font_size.get(user_id, 35)}pt\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔖 **Chapters**\n{chapters}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"✅ [Auto-Queue Master v93.0]\n"
                f"@r4nzzyy"
            )

            _upload_start = time.monotonic()
            _last_upload_edit = [0.0, -1]
            async def _upload_progress(sent, total):
                if total:
                    pct = min(99, int(sent * 100 / total))
                    now = time.monotonic()
                    if pct != _last_upload_edit[1] and (now - _last_upload_edit[0] >= 1.0 or pct >= 99):
                        _stage_progress["Upload"] = pct
                        _stage_notes["Upload"] = f"Telegram သို့ တင်နေသည် ({sent / 1048576:.1f}/{total / 1048576:.1f} MB)"
                        _last_upload_edit[:] = [now, pct]
                        try: await status.edit(_panel(_stage_notes["Upload"]))
                        except Exception: pass
            await bot.send_file(event.chat_id, output_video, caption=caption_text, progress_callback=_upload_progress)
            _stage_elapsed["Upload"] += time.monotonic() - _upload_start
            _stage_done.add("Upload")
            if os.path.exists(output_video): os.remove(output_video)

        _stage_elapsed[_stage_name] += max(0.0, time.monotonic() - _stage_clock)
        _stage_done.add(_stage_name)
        _stage_name = "Upload"
        _stage_clock = time.monotonic()
        try:
            await status.edit(_panel("✅ ပြီးဆုံးပါပြီ"))
        except Exception: pass

        if os.path.exists(input_video): os.remove(input_video)
    except Exception as e:
        # Keep the error in the existing status message; do not send a second copy.
        try: await status.edit(f"❌ Error: {str(e)}")
        except Exception as edit_err: logging.warning(f"Could not edit status message to show error: {edit_err}")
        if os.path.exists(input_video): os.remove(input_video)
        if os.path.exists(extracted_audio_path): os.remove(extracted_audio_path)

async def auto_recap_worker(user_id):
    queue = user_queues[user_id]
    try:
        while not queue.empty():
            job_item = await queue.get()
            try:
                # The global slot covers extraction, Groq/Gemini, TTS, FFmpeg
                # rendering and Telegram upload—not just the final render.
                if GLOBAL_JOB_SEMAPHORE.locked():
                    try:
                        await job_item["orig_event"].respond(
                            f"⏳ Global Queue ထဲတွင် စောင့်ဆိုင်းနေပါသည်။ တစ်ချိန်တည်း အလုပ်လုပ်နိုင်သူ {MAX_CONCURRENT_JOBS} ဦးသာရှိပြီး သင့်အလုပ်ကို အလိုအလျောက် စတင်ပေးပါမည်။"
                        )
                    except Exception:
                        pass
                async with GLOBAL_JOB_SEMAPHORE:
                    await process_recap_job(job_item, user_id)
            except Exception as e:
                logging.error(f"Job failed for user {user_id}: {e}")
                try: await job_item["orig_event"].respond(f"❌ အလုပ်မအောင်မြင်ပါ: {str(e)[:200]}")
                except: pass
            finally:
                queue.task_done()
    except Exception as e: logging.error(f"Worker crashed for user {user_id}: {e}")
    finally:
        user_queue_active[user_id] = False
        # Race guard: if another job arrived while this worker was exiting, restart.
        if not user_queues[user_id].empty():
            user_queue_active[user_id] = True
            asyncio.create_task(auto_recap_worker(user_id))

async def main():
    # Process-level lock: prevents two copies of this script in the same runtime
    # from both answering Telegram updates. Separate Colab runtimes must still be stopped manually.
    try:
        import fcntl
        _lock_file = open('/tmp/sanma_telegram_bot.lock', 'w')
        fcntl.flock(_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        globals()['_BOT_PROCESS_LOCK_FILE'] = _lock_file
    except (ImportError, BlockingIOError, OSError):
        raise RuntimeError('ဒီ Runtime ထဲမှာ Bot instance တစ်ခု run နေပြီးသားပါ။ အဟောင်းကို Stop လုပ်ပြီးမှ ပြန်စပါ။')
    threading.Thread(target=run_health_check_server, daemon=True).start()
    await bot.start(bot_token=BOT_TOKEN)
    
    await bot(SetBotCommandsRequest(
        scope=BotCommandScopeDefault(),
        lang_code='',
        commands=[
            BotCommand(command="start", description="Bot ကို စတင်ရန်"),
            BotCommand(command="setkey", description="API Keys များ ထည့်ရန်"),
            BotCommand(command="queue", description="လက်ရှိ အလုပ်တန်းစီနေမှုကို ကြည့်ရန်"),
            BotCommand(command="resetqueue", description="Queue များကို ရှင်းလင်းရန် (Admin)"),
            BotCommand(command="setwm", description="Watermark ပြောင်းရန်"),
            BotCommand(command="setlogo", description="Logo ပုံထည့်ရန် (Caption တွင်ရေးပါ)"),
            BotCommand(command="removelogo", description="Logo ဖျက်ရန်"),
            BotCommand(command="setbgm", description="BGM နောက်ခံတေးထည့်ရန် (Caption တွင်ရေးပါ)"),
            BotCommand(command="removebgm", description="BGM ဖျက်ရန်")
        ]
    ))
    
    logging.info("✅ Bot started successfully.")
    await bot.run_until_disconnected()

try:
    bot.loop.run_until_complete(main())
except Exception as e:
    print(f"Bot Error: {e}")
