import os
import sys
import json
import time
import asyncio
import subprocess
import tempfile
import zipfile
import urllib.request
import re
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto
from groq import Groq
import google.generativeai as genai
import edge_tts
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ==========================================
# 1. မြန်မာဖောင့် (၉) ခု စစ်ဆေးခြင်းနှင့် Auto-Extract/Download စနစ်
# ==========================================
REQUIRED_FONTS = [
    "Fonts/Pyidaungsu-2.5.3_Bold.ttf",
    "Fonts/Pyidaungsu-2.5.3_Regular.ttf",
    "Fonts/Pyidaungsu-1.8.3_Bold.ttf",
    "Fonts/Pyidaungsu-1.8.3_Regular.ttf",
    "Fonts/Pyidaungsu-1.8.3_Numbers.ttf",
    "Fonts/NotoSansMyanmar-Regular.ttf",
    "Fonts/NotoSerifMyanmar-Black.ttf",
    "Fonts/A13_WenYoe-Regular.ttf",
    "Fonts/myanmar_font.ttf"
]

def ensure_fonts_ready():
    os.makedirs("Fonts", exist_ok=True)
    missing = [f for f in REQUIRED_FONTS if not os.path.exists(f)]
    if not missing:
        print("✅ မြန်မာဖောင့် (၉) ခုလုံး အဆင်သင့်ရှိပါသည်။")
        return

    print(f"⏳ ဖောင့် {len(missing)} ခု ရှာမတွေ့ပါ။ ဒေါင်းလုဒ်/ဖြည်ထုတ်ခြင်း စတင်နေပါသည်...")
    
    # ဆာဗာ သို့မဟုတ် Local folder ထဲရှိ .zip ဖိုင်များမှ အလိုအလျောက် ဖြည်ထုတ်ခြင်း
    for item in os.listdir("."):
        if item.endswith(".zip"):
            try:
                with zipfile.ZipFile(item, 'r') as zf:
                    zf.extractall(".")
                print(f"📦 Local Zip ({item}) မှ ဖောင့်များကို ဖြည်ထုတ်ပြီးပါပြီ။")
            except Exception as e:
                pass

    # ပြန်လည်စစ်ဆေးခြင်း
    missing = [f for f in REQUIRED_FONTS if not os.path.exists(f)]
    if not missing:
        print("✅ ဖောင့် (၉) ခုလုံး အောင်မြင်စွာ ပြည့်စုံသွားပါပြီ။")
        return

    # GitHub Repo ပေါ်မှ bot_assets.zip ကို Auto-Download ဆွဲယူခြင်း
    download_urls = [
        "https://raw.githubusercontent.com/kaung566/burmese-auto6-bot/main/bot_assets.zip",
        "https://github.com/kaung566/burmese-auto6-bot/raw/main/bot_assets.zip"
    ]
    for url in download_urls:
        try:
            temp_zip = "temp_fonts_dl.zip"
            urllib.request.urlretrieve(url, temp_zip)
            with zipfile.ZipFile(temp_zip, 'r') as zf:
                zf.extractall(".")
            if os.path.exists(temp_zip):
                os.remove(temp_zip)
            print("🌐 GitHub မှ ဖောင့် zip ကို Auto-Download ဆွဲယူပြီး ဖြည်ထုတ်ပြီးပါပြီ။")
            break
        except Exception:
            pass

ensure_fonts_ready()

# ==========================================
# 2. Telegram Credentials & Concurrency
# ==========================================
API_ID = 32971636
API_HASH = "54178f4e37ec82caaa218ff1a2d8e8c0"
BOT_TOKEN = "8879423250:AAGXIed2jtt-bP48TuST8ywoGUBk4hL1b0g"

# အယောက် ၃၀ ပြိုင်တူလက်ခံသော်လည်း Fadehost ပေါ်တွင် ၃ ယောက်စီသာ တပြိုင်နက် Render လုပ်မည့် Semaphore
SEMAPHORE = asyncio.Semaphore(3)

app = Client("SANMA_Recap_Bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ==========================================
# 3. Database & Settings
# ==========================================
DB_FILE = "user_database.json"

DEFAULT_SETTINGS = {
    "style": "အကြမ်းစား",
    "voice": "မောင်ရွှေရိုး",
    "pitch": "+0Hz",
    "speed": "1.0",
    "orig_audio": True,
    "preview": True,
    "blur_style": "Blur အပေါ်အများ",
    "blur_pos": 63,
    "blur_size": 8,
    "sub_pos": "Sub အောက်များ",
    "sub_y_pct": 85,
    "font": "Fonts/Pyidaungsu-2.5.3_Bold.ttf"
}

def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_data(user_id):
    db = load_db()
    u_str = str(user_id)
    if u_str not in db:
        db[u_str] = {
            "gemini_keys": [],
            "groq_key": None,
            "settings": DEFAULT_SETTINGS.copy(),
            "preview_state": {}
        }
        save_db(db)
    return db[u_str]

def update_user_data(user_id, gemini_keys=None, groq_key=None, setting_key=None, setting_val=None, preview_state=None):
    db = load_db()
    u_str = str(user_id)
    if u_str not in db:
        db[u_str] = {
            "gemini_keys": [],
            "groq_key": None,
            "settings": DEFAULT_SETTINGS.copy(),
            "preview_state": {}
        }
    
    if gemini_keys is not None:
        db[u_str]["gemini_keys"] = gemini_keys
    if groq_key is not None:
        db[u_str]["groq_key"] = groq_key
    if setting_key and setting_val is not None:
        db[u_str]["settings"][setting_key] = setting_val
    if preview_state is not None:
        db[u_str]["preview_state"] = preview_state
    save_db(db)

# ==========================================
# 4. Voice, Font & Style Configuration (၉ မျိုးတိကျစွာ ထည့်သွင်းထားသည်)
# ==========================================
FONTS = [
    ("ပြည်ထောင်စု v2.5.3 Bold", "Fonts/Pyidaungsu-2.5.3_Bold.ttf"),
    ("ပြည်ထောင်စု v2.5.3 Regular", "Fonts/Pyidaungsu-2.5.3_Regular.ttf"),
    ("ပြည်ထောင်စု v1.8.3 Bold", "Fonts/Pyidaungsu-1.8.3_Bold.ttf"),
    ("ပြည်ထောင်စု v1.8.3 Regular", "Fonts/Pyidaungsu-1.8.3_Regular.ttf"),
    ("ပြည်ထောင်စု Numbers", "Fonts/Pyidaungsu-1.8.3_Numbers.ttf"),
    ("Noto Sans Myanmar", "Fonts/NotoSansMyanmar-Regular.ttf"),
    ("Noto Serif Black", "Fonts/NotoSerifMyanmar-Black.ttf"),
    ("ဝင်းရိုး ဖောင့်", "Fonts/A13_WenYoe-Regular.ttf"),
    ("Default Myanmar Font", "Fonts/myanmar_font.ttf")
]

VOICE_MAP = {
    "မောင်ဘကျော်": "my-MM-ThihaNeural",
    "မယ်ဖွား": "my-MM-NilarNeural",
    "မောင်ရွှေရိုး": "my-MM-ThihaNeural",
    "မောင်သာဒင်": "my-MM-ThihaNeural",
    "ဘိုးထွန်း": "my-MM-ThihaNeural",
    "မယ်သိင်္ဂီ": "my-MM-NilarNeural",
    "ဘသောင်း": "my-MM-ThihaNeural",
    "မြသီ": "my-MM-NilarNeural",
    "ဘညွန့်": "my-MM-ThihaNeural",
    "မယ်နု": "my-MM-NilarNeural",
    "မယ်စိန်": "my-MM-NilarNeural",
    "ပိုးထောင်": "my-MM-ThihaNeural",
    "မယ်နန်း": "my-MM-NilarNeural",
    "ကျော်စွာ": "my-MM-ThihaNeural"
}

STYLES = ["အကြမ်းစား", "အချစ်", "ဟာသ", "သည်းထိတ်ရင်ဖို", "လျှို့ဝှက်ဆန်းကြယ်", "သမိုင်းနန်းတွင်း", "ပုံမှန်"]

BLUR_STYLES = [
    "Blur အပေါ်အများ", "Blur အောက်အများ",
    "Blur အပေါ်နည်း", "Blur အောက်အနည်း",
    "Blur ဘေးအကျဉ်း", "Blur ဘေးအကျယ်",
    "Blur အပေါ်အကျယ်", "Blur အောက်အကျယ်"
]

SUB_POSITIONS = ["Sub အပေါ်များ", "Sub အောက်များ", "Sub အပေါ်နည်း", "Sub အောက်နည်း"]

# ==========================================
# 5. UI Keyboards & Settings
# ==========================================
def main_settings_keyboard(u_data):
    s = u_data["settings"]
    orig_str = "ဖွင့်ထား ✅" if s.get("orig_audio", True) else "ပိတ်ထား ❌"
    prev_str = "ဖွင့်ထား ✅" if s.get("preview", True) else "ပိတ်ထား ❌"
    
    kb = [
        [
            InlineKeyboardButton(f"🎭 စတိုင်: {s['style']}", callback_data="menu_style"),
            InlineKeyboardButton(f"🎙️ အသံ: {s['voice']}", callback_data="menu_voice")
        ],
        [
            InlineKeyboardButton("⚡ အသံနှုန်း/Pitch", callback_data="menu_audio_fx"),
            InlineKeyboardButton("🎛️ Combo အသံများ", callback_data="menu_combo")
        ],
        [
            InlineKeyboardButton(f"🔊 မူရင်းအသံ [{orig_str}]", callback_data="toggle_orig_audio"),
            InlineKeyboardButton(f"👁️ Preview [{prev_str}]", callback_data="toggle_preview")
        ],
        [
            InlineKeyboardButton("📝 Sub နေရာ", callback_data="menu_sub_pos"),
            InlineKeyboardButton("🖼️ Blur ပုံစံ", callback_data="menu_blur")
        ],
        [
            InlineKeyboardButton("🔤 Font ရွေးရန်", callback_data="menu_font"),
            InlineKeyboardButton("🔑 API Keys စစ်ဆေး/ထည့်ရန်", callback_data="menu_keys")
        ]
    ]
    return InlineKeyboardMarkup(kb)

def preview_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬜ Blur ⬆️", callback_data="pv_blur_up"), InlineKeyboardButton("⬜ Blur ⬇️", callback_data="pv_blur_down")],
        [InlineKeyboardButton("↕️ Blur Size +", callback_data="pv_blur_size_plus"), InlineKeyboardButton("↕️ Blur Size -", callback_data="pv_blur_size_minus")],
        [InlineKeyboardButton("📝 Sub ⬆️", callback_data="pv_sub_up"), InlineKeyboardButton("📝 Sub ⬇️", callback_data="pv_sub_down")],
        [InlineKeyboardButton("🔄 ပုံအသစ်ပြောင်းမည် (Frame Change)", callback_data="pv_frame_change")],
        [InlineKeyboardButton("▶️ ဗီဒီယို စတင်ရန်", callback_data="pv_start"), InlineKeyboardButton("❌ ပယ်ဖျက်ရန်", callback_data="pv_cancel")]
    ])

# ==========================================
# 6. Telegram Command & Key Handlers
# ==========================================
@app.on_message(filters.command(["setkey", "setkeys"]) & filters.private)
async def cmd_set_keys(client, message):
    text = message.text
    gemini_found = re.findall(r'(AQ\.[A-Za-z0-9_\-]+|AIza[A-Za-z0-9_\-]+)', text)
    groq_found = re.findall(r'(gsk_[A-Za-z0-9_\-]+)', text)
    
    u_id = message.from_user.id
    u_data = get_user_data(u_id)
    
    current_gemini = u_data.get("gemini_keys", [])
    current_groq = u_data.get("groq_key", None)
    
    if gemini_found:
        current_gemini = list(set(current_gemini + gemini_found))
    if groq_found:
        current_groq = groq_found[0]
        
    update_user_data(u_id, gemini_keys=current_gemini, groq_key=current_groq)
    
    reply = (
        "✅ **API Key များ သိမ်းဆည်းပြီးပါပြီ:**\n"
        f"• Gemini Key အရေအတွက်: **{len(current_gemini)} ခု**\n"
        f"• Groq Key: {'✅ မှတ်သားပြီး' if current_groq else '❌ မတွေ့ရှိပါ'}"
    )
    await message.reply_text(reply)

@app.on_message(filters.command("setgroq") & filters.private)
async def cmd_set_groq(client, message):
    if len(message.command) > 1:
        key = message.command[1].strip()
        update_user_data(message.from_user.id, groq_key=key)
        await message.reply_text("✅ **Groq API Key** သိမ်းဆည်းပြီးပါပြီ။")
    else:
        await message.reply_text("⚠️ ပုံစံ: `/setgroq gsk_xxxxxx`")

@app.on_message(filters.command("setgemini") & filters.private)
async def cmd_set_gemini(client, message):
    if len(message.command) > 1:
        keys = [k.strip() for k in message.command[1].split(",") if k.strip()]
        update_user_data(message.from_user.id, gemini_keys=keys)
        await message.reply_text(f"✅ **Gemini API Key ({len(keys)} ခု)** သိမ်းဆည်းပြီးပါပြီ။")
    else:
        await message.reply_text("⚠️ ပုံစံ: `/setgemini key1,key2`")

@app.on_message(filters.command("start") & filters.private)
async def cmd_start(client, message):
    u_data = get_user_data(message.from_user.id)
    g_count = len(u_data.get("gemini_keys", []))
    groq_ok = "✅ ရှိပါသည်" if u_data.get("groq_key") else "❌ မရှိသေးပါ"
    
    text = (
        "⚙️ **Recap Bot ဆက်တင်များ ပြင်ဆင်ရန်:**\n\n"
        f"🔑 **API Keys:** Gemini ({g_count} ခု) | Groq ({groq_ok})\n"
        "*(Key ထည့်ရန် `/setkey` ဖြင့် Gemini, Groq key များ ပို့နိုင်ပါသည်)*"
    )
    await message.reply_text(text, reply_markup=main_settings_keyboard(u_data))

# ==========================================
# 7. Callback Handler (All Controls & Menus)
# ==========================================
@app.on_callback_query()
async def callback_handler(client, query: CallbackQuery):
    data = query.data
    u_id = query.from_user.id
    u_data = get_user_data(u_id)
    
    if data == "main_menu":
        await query.message.edit_text("⚙️ **Recap Bot ဆက်တင်များ ပြင်ဆင်ရန်:**", reply_markup=main_settings_keyboard(u_data))
        
    elif data == "toggle_orig_audio":
        curr = u_data["settings"].get("orig_audio", True)
        update_user_data(u_id, setting_key="orig_audio", setting_val=not curr)
        u_data = get_user_data(u_id)
        await query.message.edit_reply_markup(reply_markup=main_settings_keyboard(u_data))

    elif data == "toggle_preview":
        curr = u_data["settings"].get("preview", True)
        update_user_data(u_id, setting_key="preview", setting_val=not curr)
        u_data = get_user_data(u_id)
        await query.message.edit_reply_markup(reply_markup=main_settings_keyboard(u_data))

    elif data == "menu_keys":
        g_count = len(u_data.get("gemini_keys", []))
        groq_status = "✅ မှတ်သားထားပြီး" if u_data.get("groq_key") else "❌ မရှိသေးပါ"
        text = (
            "🔑 **လက်ရှိ API Keys အခြေအနေ:**\n\n"
            f"• Gemini Keys: **{g_count} ခု**\n"
            f"• Groq Key: **{groq_status}**\n\n"
            "Key ထည့်ရန် အောက်ပါအတိုင်း ပေးပို့နိုင်ပါသည်:\n"
            "`/setkey GeminiKey1,GeminiKey2`\n"
            "`GroqKey`"
        )
        btns = [[InlineKeyboardButton("🔙 ပြန်ထွက်မည်", callback_data="main_menu")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(btns))

    elif data == "menu_style":
        btns = [[InlineKeyboardButton(st, callback_data=f"set_st_{st}")] for st in STYLES]
        btns.append([InlineKeyboardButton("🔙 ပြန်ထွက်မည်", callback_data="main_menu")])
        await query.message.edit_text("🎭 **ဘာသာပြန် စတိုင် ရွေးချယ်ပါ (Hook စာသား ပါဝင်ပါမည်):**", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("set_st_"):
        st = data.replace("set_st_", "")
        update_user_data(u_id, setting_key="style", setting_val=st)
        u_data = get_user_data(u_id)
        await query.message.edit_text(f"✅ စတိုင်ကို **{st}** သို့ ပြောင်းလိုက်ပါပြီ။", reply_markup=main_settings_keyboard(u_data))

    elif data == "menu_voice":
        v_list = list(VOICE_MAP.keys())
        btns = []
        for i in range(0, len(v_list), 2):
            row = [InlineKeyboardButton(v_list[i], callback_data=f"set_vc_{v_list[i]}")]
            if i + 1 < len(v_list):
                row.append(InlineKeyboardButton(v_list[i+1], callback_data=f"set_vc_{v_list[i+1]}"))
            btns.append(row)
        btns.append([InlineKeyboardButton("🔙 ပြန်ထွက်မည်", callback_data="main_menu")])
        await query.message.edit_text("🎙️ **အသံကာရိုက်တာ ရွေးချယ်ပါ:**", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("set_vc_"):
        vc = data.replace("set_vc_", "")
        update_user_data(u_id, setting_key="voice", setting_val=vc)
        u_data = get_user_data(u_id)
        await query.message.edit_text(f"✅ အသံကို **{vc}** သို့ ပြောင်းလိုက်ပါပြီ။", reply_markup=main_settings_keyboard(u_data))

    elif data == "menu_audio_fx":
        btns = [
            [InlineKeyboardButton("Pitch: +20Hz", callback_data="fx_p_+20Hz"), InlineKeyboardButton("Pitch: +30Hz", callback_data="fx_p_+30Hz")],
            [InlineKeyboardButton("Pitch: +40Hz", callback_data="fx_p_+40Hz"), InlineKeyboardButton("Pitch: +50Hz", callback_data="fx_p_+50Hz")],
            [InlineKeyboardButton("Pitch: +60Hz", callback_data="fx_p_+60Hz"), InlineKeyboardButton("Speed: 1.0x", callback_data="fx_s_1.0")],
            [InlineKeyboardButton("Speed: 1.1x", callback_data="fx_s_1.1"), InlineKeyboardButton("Speed: 1.2x", callback_data="fx_s_1.2")],
            [InlineKeyboardButton("Speed: 1.3x", callback_data="fx_s_1.3")],
            [InlineKeyboardButton("🔙 ပြန်ထွက်မည်", callback_data="main_menu")]
        ]
        await query.message.edit_text("⚡ **Pitch နှင့် Speed ချိန်ညှိရန်:**", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("fx_p_"):
        p = data.replace("fx_p_", "")
        update_user_data(u_id, setting_key="pitch", setting_val=p)
        await query.answer(f"Pitch ကို {p} သတ်မှတ်ပြီးပါပြီ")

    elif data.startswith("fx_s_"):
        s = data.replace("fx_s_", "")
        update_user_data(u_id, setting_key="speed", setting_val=s)
        await query.answer(f"Speed ကို {s}x သတ်မှတ်ပြီးပါပြီ")

    elif data == "menu_combo":
        combos = [
            ("⚡ သွက်လက်မြန်ဆန်", "+30Hz", "1.2"),
            ("🗿 လေးနက်တည်ငြိမ်", "-20Hz", "1.0"),
            ("🔥 အက်ရှင်ဇာတ်ရှိန်", "+50Hz", "1.2"),
            ("😂 ဟာသပေါ့ပေါ့ပါးပါး", "+40Hz", "1.1"),
            ("✨ ပုံမှန်အချိုးကျ", "+0Hz", "1.0")
        ]
        btns = [[InlineKeyboardButton(c[0], callback_data=f"combo_{i}")] for i, c in enumerate(combos)]
        btns.append([InlineKeyboardButton("🔙 ပြန်ထွက်မည်", callback_data="main_menu")])
        await query.message.edit_text("🎛️ **အသင့်သုံး ပေါင်းစပ်အသံ ခလုတ် (၅) မျိုး:**", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("combo_"):
        idx = int(data.replace("combo_", ""))
        combos = [
            ("သွက်လက်မြန်ဆန်", "+30Hz", "1.2"),
            ("လေးနက်တည်ငြိမ်", "-20Hz", "1.0"),
            ("အက်ရှင်ဇာတ်ရှိန်", "+50Hz", "1.2"),
            ("ဟာသပေါ့ပေါ့ပါးပါး", "+40Hz", "1.1"),
            ("ပုံမှန်အချိုးကျ", "+0Hz", "1.0")
        ]
        chosen = combos[idx]
        update_user_data(u_id, setting_key="pitch", setting_val=chosen[1])
        update_user_data(u_id, setting_key="speed", setting_val=chosen[2])
        u_data = get_user_data(u_id)
        await query.message.edit_text(f"✅ ပေါင်းစပ်အသံ **{chosen[0]}** ကို သတ်မှတ်လိုက်ပါပြီ။", reply_markup=main_settings_keyboard(u_data))

    elif data == "menu_blur":
        btns = []
        for i in range(0, len(BLUR_STYLES), 2):
            btns.append([
                InlineKeyboardButton(BLUR_STYLES[i], callback_data=f"set_b_{BLUR_STYLES[i]}"),
                InlineKeyboardButton(BLUR_STYLES[i+1], callback_data=f"set_b_{BLUR_STYLES[i+1]}")
            ])
        btns.append([InlineKeyboardButton("🔙 ပြန်ထွက်မည်", callback_data="main_menu")])
        await query.message.edit_text("🖼️ **Blur စတိုင် (၈) မျိုး ရွေးချယ်ပါ:**", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("set_b_"):
        b_val = data.replace("set_b_", "")
        update_user_data(u_id, setting_key="blur_style", setting_val=b_val)
        u_data = get_user_data(u_id)
        await query.message.edit_text(f"✅ Blur ကို **{b_val}** သတ်မှတ်ပြီးပါပြီ။", reply_markup=main_settings_keyboard(u_data))

    elif data == "menu_sub_pos":
        btns = [[InlineKeyboardButton(op, callback_data=f"set_sp_{op}")] for op in SUB_POSITIONS]
        btns.append([InlineKeyboardButton("🔙 ပြန်ထွက်မည်", callback_data="main_menu")])
        await query.message.edit_text("📝 **Sub နေရာ (၄) မျိုး ရွေးချယ်ပါ:**", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("set_sp_"):
        sp_val = data.replace("set_sp_", "")
        update_user_data(u_id, setting_key="sub_pos", setting_val=sp_val)
        u_data = get_user_data(u_id)
        await query.message.edit_text(f"✅ Sub နေရာကို **{sp_val}** သတ်မှတ်ပြီးပါပြီ။", reply_markup=main_settings_keyboard(u_data))

    elif data == "menu_font":
        btns = [[InlineKeyboardButton(name, callback_data=f"set_fnt_{path}")] for name, path in FONTS]
        btns.append([InlineKeyboardButton("🔙 ပြန်ထွက်မည်", callback_data="main_menu")])
        await query.message.edit_text("🔤 **အသုံးပြုမည့် မြန်မာဖောင့် (၉) မျိုးမှ ရွေးပါ:**", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("set_fnt_"):
        f_path = data.replace("set_fnt_", "")
        update_user_data(u_id, setting_key="font", setting_val=f_path)
        u_data = get_user_data(u_id)
        await query.message.edit_text("✅ ဖောင့်ကို အောင်မြင်စွာ ပြောင်းလဲလိုက်ပါပြီ။", reply_markup=main_settings_keyboard(u_data))

    # Interactive Preview Callbacks
    elif data.startswith("pv_"):
        p_state = u_data.get("preview_state", {})
        if not p_state:
            await query.answer("နမူနာ သက်တမ်းကုန်သွားပါပြီ", show_alert=True)
            return
            
        action = data.replace("pv_", "")
        if action == "blur_up":
            p_state["blur_pos"] = max(10, p_state.get("blur_pos", 63) - 5)
        elif action == "blur_down":
            p_state["blur_pos"] = min(90, p_state.get("blur_pos", 63) + 5)
        elif action == "blur_size_plus":
            p_state["blur_size"] = min(30, p_state.get("blur_size", 8) + 2)
        elif action == "blur_size_minus":
            p_state["blur_size"] = max(2, p_state.get("blur_size", 8) - 2)
        elif action == "sub_up":
            p_state["sub_y"] = max(10, p_state.get("sub_y", 63) - 5)
        elif action == "sub_down":
            p_state["sub_y"] = min(90, p_state.get("sub_y", 63) + 5)
        elif action == "frame_change":
            p_state["frame_pct"] = (p_state.get("frame_pct", 15) + 15) % 85 + 5
        elif action == "cancel":
            update_user_data(u_id, preview_state={})
            await query.message.delete()
            return
        elif action == "start":
            asyncio.create_task(run_full_render(client, query.message, u_id, p_state))
            return
            
        update_user_data(u_id, preview_state=p_state)
        new_thumb = p_state["frame_img"]
        generate_preview_overlay(p_state["raw_frame"], new_thumb, p_state["blur_pos"], p_state["blur_size"], p_state["sub_y"], u_data["settings"]["font"])
        
        caption = (
            f"⬜ Blur နေရာ: {p_state['blur_pos']}% (Size: {p_state['blur_size']}%)\n"
            f"📝 Subtitle နေရာ: {p_state['sub_y']}%\n"
            f"⏱️ စာတန်းထိုးပေါ်မည့် နမူနာပြကွက်: {p_state.get('frame_pct', 15)}%\n"
            "*(ပုံတွင် စာတန်းမပါပါက '🔄 ပုံအသစ်ပြောင်းမည်' နှိပ်ပါ)*"
        )
        try:
            await query.message.edit_media(
                media=InputMediaPhoto(new_thumb, caption=caption),
                reply_markup=preview_keyboard()
            )
        except Exception:
            pass

# ==========================================
# 8. Preview Overlay Generator
# ==========================================
def generate_preview_overlay(raw_frame, output_path, blur_pos, blur_size, sub_y, font_path):
    img = Image.open(raw_frame).convert("RGBA").resize((720, 1280))
    w, h = img.size
    
    b_center = int(h * (blur_pos / 100.0))
    b_half = int(h * (blur_size / 200.0))
    b_top = max(0, b_center - b_half)
    b_bot = min(h, b_center + b_half)
    
    box = (0, b_top, w, b_bot)
    ic = img.crop(box)
    ic = ic.filter(ImageFilter.GaussianBlur(15))
    img.paste(ic, box)
    
    # Yellow Highlight Band
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)
    draw_ov.rectangle([0, b_top, w, b_bot], fill=(255, 235, 59, 90))
    img = Image.alpha_composite(img, overlay).convert("RGB")
    
    draw = ImageDraw.Draw(img)
    try:
        fnt = ImageFont.truetype(font_path, 34)
    except Exception:
        fnt = ImageFont.load_default()
        
    sub_text = "စာတန်းထိုးနေရာ"
    bbox = draw.textbbox((0, 0), sub_text, font=fnt)
    sw = bbox[2] - bbox[0]
    sx = (w - sw) / 2
    sy = int(h * (sub_y / 100.0))
    
    # White text with black outline only (No black box)
    for offset in [(-2, -2), (2, -2), (-2, 2), (2, 2), (0, 3), (3, 0)]:
        draw.text((sx + offset[0], sy + offset[1]), sub_text, font=fnt, fill=(0, 0, 0))
    draw.text((sx, sy), sub_text, font=fnt, fill=(255, 255, 255))
    
    img.save(output_path, "JPEG", quality=90)

# ==========================================
# 9. Live Progress Bar (Fast Edition UI)
# ==========================================
async def update_progress_ui(msg, step_idx, step_pct, start_time):
    elapsed = int(time.time() - start_time)
    mins, secs = divmod(elapsed, 60)
    time_str = f"{mins}m {secs}s"
    
    steps_meta = [
        "📥 Videoမှအသံထုတ်",
        "🧠 AI Script",
        "🎙️ Audio",
        "🔄 Render",
        "📤 Upload"
    ]
    
    text = "Fast Edition) 😉\n\n"
    for i, name in enumerate(steps_meta):
        if i < step_idx:
            text += f"{name}: ✅ ရရှိပါပြီ \n     [■■■■■■■■■■] 100%\n"
        elif i == step_idx:
            bars = int(step_pct / 10)
            bar_str = "■" * bars + "□" * (10 - bars)
            status_text = "✅ ပြီးပါပြီ" if step_pct == 100 else "လုပ်ဆောင်နေသည်..."
            text += f"{name}: {status_text} \n     [{bar_str}] {step_pct}%\n"
        else:
            text += f"{name}: စောင့်ဆိုင်းနေပါသည်...\n     [□□□□□□□□□□] 0%\n"
            
    text += f"\n⏱ Total time: [{time_str}]"
    try:
        await msg.edit_text(text)
    except Exception:
        pass

# ==========================================
# 10. AI Translation (Gemini Keys Fallback -> Groq)
# ==========================================
async def generate_recap_script(groq_key, gemini_keys, raw_transcript, style):
    system_prompt = (
        f"You are a master Burmese movie recap storyteller. Translate and rewrite this transcript into an engaging, thrilling Burmese Movie Recap in '{style}' style. "
        f"CRITICAL HOOK: The very first sentence MUST be an ultra-catchy HOOK that immediately shocks and glues the audience! "
        f"Natural spoken Burmese narrative only. No meta talk or headers."
    )
    
    # 1. Try Gemini Keys sequentially
    for g_key in gemini_keys:
        try:
            genai.configure(api_key=g_key)
            model = genai.GenerativeModel("gemini-2.5-flash")
            response = await asyncio.to_thread(model.generate_content, f"{system_prompt}\n\nTranscript:\n{raw_transcript}")
            if response.text:
                return response.text.strip()
        except Exception:
            try:
                model_alt = genai.GenerativeModel("gemini-1.5-flash")
                response = await asyncio.to_thread(model_alt.generate_content, f"{system_prompt}\n\nTranscript:\n{raw_transcript}")
                if response.text:
                    return response.text.strip()
            except Exception:
                continue
                
    # 2. Fallback to Groq Llama-3.3
    if groq_key:
        try:
            client = Groq(api_key=groq_key)
            completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": raw_transcript}
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.7
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            print(f"Groq fallback failed: {e}")
            
    return raw_transcript

# ==========================================
# 11. Center Thumbnail Generator (အလယ်ဗဟို စာသားအသစ် ဒီဇိုင်း)
# ==========================================
def generate_center_thumbnail(video_path, output_thumb_path, font_path, title_text):
    temp_frame = output_thumb_path + "_raw.jpg"
    subprocess.run(["ffmpeg", "-y", "-ss", "00:00:03", "-i", video_path, "-vframes", "1", "-q:v", "2", temp_frame], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    if os.path.exists(temp_frame):
        img = Image.open(temp_frame).convert("RGBA").resize((1080, 1920))
        os.remove(temp_frame)
    else:
        img = Image.new('RGB', (1080, 1920), color=(15, 15, 15))
        
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)
    draw_ov.rectangle([0, 720, 1080, 1200], fill=(0, 0, 0, 175))
    img = Image.alpha_composite(img, overlay).convert("RGB")
    
    draw = ImageDraw.Draw(img)
    try:
        fnt = ImageFont.truetype(font_path, 80)
    except Exception:
        fnt = ImageFont.load_default()
        
    lines = [title_text[:22], title_text[22:44]] if len(title_text) > 22 else [title_text]
    y_pos = 910
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=fnt)
        w = bbox[2] - bbox[0]
        x = (1080 - w) / 2
        for off in [(-4, -4), (4, -4), (-4, 4), (4, 4), (0, 5), (5, 0)]:
            draw.text((x + off[0], y_pos + off[1]), line, font=fnt, fill=(0, 0, 0))
        draw.text((x, y_pos), line, font=fnt, fill=(255, 235, 59))
        y_pos += 105
        
    img.save(output_thumb_path, "JPEG", quality=95)

# ==========================================
# 12. Main Processing & Concurrency Pipeline
# ==========================================
@app.on_message(filters.video & filters.private)
async def incoming_video_handler(client, message):
    u_id = message.from_user.id
    u_data = get_user_data(u_id)
    
    if not u_data.get("gemini_keys") and not u_data.get("groq_key"):
        await message.reply_text("⚠️ ကျေးဇူးပြု၍ API Keys အရင်ထည့်ပါ။ ပုံစံ:\n`/setkey GeminiKey1,GeminiKey2`\n`GroqKey`")
        return
        
    if u_data["settings"].get("preview", True):
        status_msg = await message.reply_text("🔍 နမူနာပြကွက် (Preview) ဖန်တီးနေပါသည်...")
        with tempfile.TemporaryDirectory() as td:
            video_temp = os.path.join(td, "vid_p.mp4")
            raw_f = os.path.join(td, "raw_frame.jpg")
            preview_img = os.path.join(td, f"preview_{u_id}.jpg")
            
            await message.download(file_name=video_temp)
            subprocess.run(["ffmpeg", "-y", "-ss", "00:00:03", "-i", video_temp, "-vframes", "1", "-q:v", "2", raw_f], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            p_state = {
                "video_msg_id": message.id,
                "raw_frame": raw_f,
                "frame_img": preview_img,
                "blur_pos": u_data["settings"].get("blur_pos", 63),
                "blur_size": u_data["settings"].get("blur_size", 8),
                "sub_y": u_data["settings"].get("sub_y_pct", 63),
                "frame_pct": 15
            }
            generate_preview_overlay(raw_f, preview_img, p_state["blur_pos"], p_state["blur_size"], p_state["sub_y"], u_data["settings"]["font"])
            update_user_data(u_id, preview_state=p_state)
            
            caption = (
                f"⬜ Blur နေရာ: {p_state['blur_pos']}% (Size: {p_state['blur_size']}%)\n"
                f"📝 Subtitle နေရာ: {p_state['sub_y']}%\n"
                f"⏱️ စာတန်းထိုးပေါ်မည့် နမူနာပြကွက်: 15%\n"
                "*(ပုံတွင် စာတန်းမပါပါက '🔄 ပုံအသစ်ပြောင်းမည်' နှိပ်ပါ)*"
            )
            await message.reply_photo(photo=preview_img, caption=caption, reply_markup=preview_keyboard())
            await status_msg.delete()
        return

    await run_full_render(client, message, u_id, {})

async def run_full_render(client, trigger_msg, u_id, p_state):
    u_data = get_user_data(u_id)
    progress_msg = await trigger_msg.reply_text("⏳ စတင်ရန် တန်းစီစောင့်ဆိုင်းနေပါသည်... (Max 3 Jobs)")
    
    async with SEMAPHORE:
        start_time = time.time()
        with tempfile.TemporaryDirectory() as workdir:
            input_video = os.path.join(workdir, "input.mp4")
            comp_audio = os.path.join(workdir, "audio_comp.mp3")
            recap_audio = os.path.join(workdir, "recap_tts.mp3")
            srt_path = os.path.join(workdir, "subs.srt")
            output_video = os.path.join(workdir, "final_recap.mp4")
            thumb_path = os.path.join(workdir, "thumb.jpg")
            
            # Step 0: Download & Extract Audio
            await update_progress_ui(progress_msg, 0, 30, start_time)
            v_id = p_state.get("video_msg_id", trigger_msg.id)
            v_msg = await client.get_messages(trigger_msg.chat.id, v_id)
            await v_msg.download(file_name=input_video)
            
            await update_progress_ui(progress_msg, 0, 80, start_time)
            subprocess.run([
                "ffmpeg", "-y", "-i", input_video,
                "-vn", "-ar", "16000", "-ac", "1", "-b:a", "32k",
                comp_audio
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            await update_progress_ui(progress_msg, 0, 100, start_time)
            
            # Step 1: Transcription & AI Script
            await update_progress_ui(progress_msg, 1, 35, start_time)
            groq_c = Groq(api_key=u_data["groq_key"])
            
            with open(comp_audio, "rb") as f:
                transcription = groq_c.audio.transcriptions.create(
                    file=(os.path.basename(comp_audio), f.read()),
                    model="whisper-large-v3",
                    response_format="text"
                )
            
            await update_progress_ui(progress_msg, 1, 75, start_time)
            recap_script = await generate_recap_script(
                u_data.get("groq_key"),
                u_data.get("gemini_keys", []),
                transcription,
                u_data["settings"]["style"]
            )
            await update_progress_ui(progress_msg, 1, 100, start_time)
            
            # Step 2: Edge-TTS Narration
            await update_progress_ui(progress_msg, 2, 45, start_time)
            s_set = u_data["settings"]
            tts_v = VOICE_MAP.get(s_set["voice"], "my-MM-ThihaNeural")
            
            comm = edge_tts.Communicate(
                text=recap_script,
                voice=tts_v,
                pitch=s_set["pitch"],
                rate=f"{s_set['speed']}x"
            )
            await comm.save(recap_audio)
            
            dur_p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", recap_audio], stdout=subprocess.PIPE, text=True)
            try:
                audio_dur = float(dur_p.stdout.strip())
            except Exception:
                audio_dur = 30.0
                
            words = recap_script.split()
            chunk_size = 5
            chunks = [" ".join(words[i:i+chunk_size]) for i in range(0, len(words), chunk_size)]
            sec_chk = audio_dur / max(len(chunks), 1)
            
            with open(srt_path, "w", encoding="utf-8") as srt_f:
                for idx, chk in enumerate(chunks):
                    t0 = idx * sec_chk; t1 = (idx + 1) * sec_chk
                    sh, sr = divmod(int(t0), 3600); sm, ss = divmod(sr, 60); sms = int((t0 - int(t0)) * 1000)
                    eh, er = divmod(int(t1), 3600); em, es = divmod(er, 60); ems = int((t1 - int(t1)) * 1000)
                    srt_f.write(f"{idx+1}\n{sh:02d}:{sm:02d}:{ss:02d},{sms:03d} --> {eh:02d}:{em:02d}:{es:02d},{ems:03d}\n{chk}\n\n")
            await update_progress_ui(progress_msg, 2, 100, start_time)
            
            # Step 3: FFmpeg Render (Blur, Subtitle, Original Audio Ducking)
            await update_progress_ui(progress_msg, 3, 25, start_time)
            
            align = "2"; margin_v = "40"
            sub_setting = s_set.get("sub_pos", "Sub အောက်များ")
            if "အောက်များ" in sub_setting:
                align = "2"; margin_v = "35"
            elif "အောက်နည်း" in sub_setting:
                align = "2"; margin_v = "120"
            elif "အပေါ်များ" in sub_setting:
                align = "6"; margin_v = "35"
            elif "အပေါ်နည်း" in sub_setting:
                align = "6"; margin_v = "120"
                
            sub_style = f"FontName={s_set['font']},FontSize=19,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2.8,Shadow=0,Alignment={align},MarginV={margin_v}"
            escaped_srt = srt_path.replace(":", "\\:").replace("\\", "/")
            
            filter_v = (
                f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:5[bg];"
                f"[0:v]scale=1080:-1[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,subtitles={escaped_srt}:force_style='{sub_style}'[v]"
            )
            
            # 🔊 Original Audio Ducking (စကားပြောသည့်အခန်း မူရင်းအသံ ငြိမ်သွားမည်၊ တိတ်သည့်အခန်း ၁၀၀% ပြန်ထွက်မည်)
            if s_set.get("orig_audio", True):
                filter_a = (
                    "[0:a][1:a]sidechaincompress=threshold=0.03:ratio=25:attack=10:release=300[ducked];"
                    "[ducked][1:a]amix=inputs=2:duration=first[a]"
                )
            else:
                filter_a = "[1:a]volume=3.5[a]"
                
            await update_progress_ui(progress_msg, 3, 60, start_time)
            render_cmd = [
                "ffmpeg", "-y",
                "-i", input_video,
                "-i", recap_audio,
                "-filter_complex", f"{filter_v};{filter_a}",
                "-map", "[v]", "-map", "[a]",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24",
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",
                output_video
            ]
            subprocess.run(render_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            generate_center_thumbnail(output_video, thumb_path, s_set["font"], f"{s_set['style']} Recap")
            await update_progress_ui(progress_msg, 3, 100, start_time)
            
            # Step 4: Uploading to Telegram
            await update_progress_ui(progress_msg, 4, 60, start_time)
            await client.send_video(
                chat_id=trigger_msg.chat.id,
                video=output_video,
                thumb=thumb_path if os.path.exists(thumb_path) else None,
                caption=f"🎬 **{s_set['style']} Movie Recap**\n🎙️ အသံ: {s_set['voice']}\n⚡ Speed: {s_set['speed']}x",
                reply_to_message_id=v_id
            )
            await update_progress_ui(progress_msg, 4, 100, start_time)

# ==========================================
# 13. Start Bot
# ==========================================
if __name__ == "__main__":
    print("🚀 SANMA Movie Recap Bot is running on GitHub/Fadehost...")
    app.run()
