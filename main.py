import os
import sys
import json
import time
import asyncio
import subprocess
import tempfile
import re
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from groq import Groq
import google.generativeai as genai
import edge_tts
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ==========================================
# 1. Telegram Credentials & Concurrency
# ==========================================
API_ID = 32971636
API_HASH = "54178f4e37ec82caaa218ff1a2d8e8c0"
BOT_TOKEN = "8879423250:AAGXIed2jtt-bP48TuST8ywoGUBk4hL1b0g"

# လူ ၃ ယောက် အပြိုင် လုပ်ဆောင်မည့် ကန့်သတ်ချက်
SEMAPHORE = asyncio.Semaphore(3)

app = Client("SANMA_Recap_Bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ==========================================
# 2. Key & Settings Database
# ==========================================
DB_FILE = "user_database.json"

DEFAULT_SETTINGS = {
    "style": "အကြမ်းစား",
    "voice": "မောင်ဘကျော်",
    "pitch": "+0Hz",
    "speed": "1.0",
    "orig_audio": True,
    "blur_style": "Blur အပေါ်အများ",
    "sub_pos": "အောက်များ",
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
        db[u_str] = {"groq_key": None, "gemini_key": None, "settings": DEFAULT_SETTINGS.copy()}
        save_db(db)
    return db[u_str]

def update_user_data(user_id, key=None, val=None, setting_key=None, setting_val=None):
    db = load_db()
    u_str = str(user_id)
    if u_str not in db:
        db[u_str] = {"groq_key": None, "gemini_key": None, "settings": DEFAULT_SETTINGS.copy()}
    
    if key and val:
        db[u_str][key] = val
    if setting_key and setting_val is not None:
        db[u_str]["settings"][setting_key] = setting_val
    save_db(db)

# ==========================================
# 3. Voice & Persona Mappings
# ==========================================
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

FONTS = [
    ("ပြည်ထောင်စု Bold", "Fonts/Pyidaungsu-2.5.3_Bold.ttf"),
    ("ပြည်ထောင်စု Reg", "Fonts/Pyidaungsu-2.5.3_Regular.ttf"),
    ("ပြည်ထောင်စု v1.8 Bold", "Fonts/Pyidaungsu-1.8.3_Bold.ttf"),
    ("ပြည်ထောင်စု v1.8 Reg", "Fonts/Pyidaungsu-1.8.3_Regular.ttf"),
    ("ပြည်ထောင်စု Numbers", "Fonts/Pyidaungsu-1.8.3_Numbers.ttf"),
    ("Noto Sans Myanmar", "Fonts/NotoSansMyanmar-Regular.ttf"),
    ("Noto Serif Black", "Fonts/NotoSerifMyanmar-Black.ttf"),
    ("ဝင်းရိုး ဖောင့်", "Fonts/A13_WenYoe-Regular.ttf"),
    ("Myanmar Default", "Fonts/myanmar_font.ttf")
]

# ==========================================
# 4. Settings Keyboards (UI Design သစ်)
# ==========================================
def main_settings_keyboard(u_data):
    s = u_data["settings"]
    orig_str = "ဖွင့်ထား ✅" if s["orig_audio"] else "ပိတ်ထား ❌"
    
    kb = [
        [
            InlineKeyboardButton(f"🎭 စတိုင်: {s['style']}", callback_data="menu_style"),
            InlineKeyboardButton(f"🎙️ အသံ: {s['voice']}", callback_data="menu_voice")
        ],
        [
            InlineKeyboardButton(f"⚡ အသံနှုန်း/Pitch", callback_data="menu_audio_fx"),
            InlineKeyboardButton(f"🎛️ Combo အသံများ", callback_data="menu_combo")
        ],
        [
            InlineKeyboardButton(f"🔊 မူရင်းအသံ [{orig_str}]", callback_data="toggle_orig_audio"),
            InlineKeyboardButton(f"📝 Sub နေရာ: {s['sub_pos']}", callback_data="menu_sub_pos")
        ],
        [
            InlineKeyboardButton(f"🖼️ Blur: {s['blur_style']}", callback_data="menu_blur"),
            InlineKeyboardButton(f"🔤 Font ရွေးရန်", callback_data="menu_font")
        ],
        [
            InlineKeyboardButton("🔑 API Keys စစ်ဆေး/ထည့်ရန်", callback_data="menu_keys")
        ]
    ]
    return InlineKeyboardMarkup(kb)

# ==========================================
# 5. Telegram Handlers for Settings & Keys
# ==========================================
@app.on_message(filters.command("setgroq") & filters.private)
async def cmd_set_groq(client, message):
    if len(message.command) > 1:
        key = message.command[1].strip()
        update_user_data(message.from_user.id, key="groq_key", val=key)
        await message.reply_text("✅ **Groq API Key** ကို သိမ်းဆည်းပြီးပါပြီ။")
    else:
        await message.reply_text("⚠️ ပုံစံ: `/setgroq gsk_xxxxxx`")

@app.on_message(filters.command("setgemini") & filters.private)
async def cmd_set_gemini(client, message):
    if len(message.command) > 1:
        key = message.command[1].strip()
        update_user_data(message.from_user.id, key="gemini_key", val=key)
        await message.reply_text("✅ **Gemini API Key** ကို သိမ်းဆည်းပြီးပါပြီ။")
    else:
        await message.reply_text("⚠️ ပုံစံ: `/setgemini AIzaxxxxxx`")

@app.on_message(filters.command("start") & filters.private)
async def cmd_start(client, message):
    u_data = get_user_data(message.from_user.id)
    text = (
        "🎬 **SANMA Movie Recap Automation Bot မှ ကြိုဆိုပါသည်။**\n\n"
        "🔑 **API Keys အခြေအနေ:**\n"
        f"• Groq Key: {'✅ ရှိပါသည်' if u_data['groq_key'] else '❌ မရှိသေးပါ (`/setgroq` ဖြင့်ထည့်ပါ)'}\n"
        f"• Gemini Key: {'✅ ရှိပါသည်' if u_data['gemini_key'] else '❌ မရှိသေးပါ (`/setgemini` ဖြင့်ထည့်ပါ)'}\n\n"
        "ဗီဒီယို ပေးပို့ပြီးသည်နှင့် Recap ကို စက္ကန့်ပိုင်းအတွင်း အလိုအလျောက် ထုတ်လုပ်ပေးပါမည်။\n"
        "👇 ဆက်တင်များကို အောက်ပါ Menu တွင် ပြင်ဆင်နိုင်ပါသည် -"
    )
    await message.reply_text(text, reply_markup=main_settings_keyboard(u_data))

@app.on_callback_query()
async def callback_handler(client, query: CallbackQuery):
    data = query.data
    u_id = query.from_user.id
    u_data = get_user_data(u_id)
    
    if data == "main_menu":
        await query.message.edit_text("⚙️ **Recap Bot ဆက်တင်များ ပြင်ဆင်ရန်:**", reply_markup=main_settings_keyboard(u_data))
        
    elif data == "toggle_orig_audio":
        curr = u_data["settings"]["orig_audio"]
        update_user_data(u_id, setting_key="orig_audio", setting_val=not curr)
        u_data = get_user_data(u_id)
        await query.message.edit_reply_markup(reply_markup=main_settings_keyboard(u_data))

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
        blur_options = [
            "Blur အပေါ်အများ", "Blur အောက်အများ",
            "Blur အပေါ်နည်း", "Blur အောက်အနည်း",
            "Blur ဘေးအကျဉ်း", "Blur ဘေးအကျယ်",
            "Blur အပေါ်အကျယ်", "Blur အောက်အကျယ်"
        ]
        btns = []
        for i in range(0, len(blur_options), 2):
            btns.append([
                InlineKeyboardButton(blur_options[i], callback_data=f"set_b_{blur_options[i]}"),
                InlineKeyboardButton(blur_options[i+1], callback_data=f"set_b_{blur_options[i+1]}")
            ])
        btns.append([InlineKeyboardButton("🔙 ပြန်ထွက်မည်", callback_data="main_menu")])
        await query.message.edit_text("🖼️ **Blur ပုံစံ ရွေးချယ်ပါ:**", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("set_b_"):
        b_val = data.replace("set_b_", "")
        update_user_data(u_id, setting_key="blur_style", setting_val=b_val)
        u_data = get_user_data(u_id)
        await query.message.edit_text(f"✅ Blur ကို **{b_val}** သို့ သတ်မှတ်ပြီးပါပြီ။", reply_markup=main_settings_keyboard(u_data))

    elif data == "menu_sub_pos":
        sub_options = ["အောက်များ", "ပေါ်များ", "အောက်နည်း", "ပေါ်နည်း"]
        btns = [[InlineKeyboardButton(op, callback_data=f"set_sp_{op}")] for op in sub_options]
        btns.append([InlineKeyboardButton("🔙 ပြန်ထွက်မည်", callback_data="main_menu")])
        await query.message.edit_text("📝 **စာတန်းထိုး (Subtitle) နေရာ ရွေးချယ်ပါ:**", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("set_sp_"):
        sp_val = data.replace("set_sp_", "")
        update_user_data(u_id, setting_key="sub_pos", setting_val=sp_val)
        u_data = get_user_data(u_id)
        await query.message.edit_text(f"✅ Subtitle နေရာကို **{sp_val}** သို့ သတ်မှတ်လိုက်ပါပြီ။", reply_markup=main_settings_keyboard(u_data))

    elif data == "menu_font":
        btns = [[InlineKeyboardButton(name, callback_data=f"set_fnt_{path}")] for name, path in FONTS]
        btns.append([InlineKeyboardButton("🔙 ပြန်ထွက်မည်", callback_data="main_menu")])
        await query.message.edit_text("🔤 **အသုံးပြုမည့် မြန်မာဖောင့်ကို ရွေးပါ:**", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("set_fnt_"):
        f_path = data.replace("set_fnt_", "")
        update_user_data(u_id, setting_key="font", setting_val=f_path)
        u_data = get_user_data(u_id)
        await query.message.edit_text("✅ ဖောင့်ကို အောင်မြင်စွာ ပြောင်းလဲလိုက်ပါပြီ။", reply_markup=main_settings_keyboard(u_data))

# ==========================================
# 6. Live Progress Bar Updater
# ==========================================
async def update_progress_ui(msg, step_idx, step_pct, start_time):
    # step_idx: 0=Videoမှအသံထုတ်, 1=AI Script, 2=Audio, 3=Render, 4=Upload
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
            text += f"{name}: ✅ ပြီးပါပြီ \n     [■■■■■■■■■■] 100%\n"
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
# 7. AI Translation (Gemini -> Groq Fallback)
# ==========================================
async def generate_recap_script(groq_key, gemini_key, raw_transcript, style):
    system_prompt = (
        f"You are a professional Movie Recap Scriptwriter in Burmese language. "
        f"Translate and rewrite the following transcript into an engaging Movie Recap in '{style}' style. "
        f"CRITICAL: The very first sentence MUST be an ultra-catchy HOOK that immediately grabs the audience's attention! "
        f"Use natural, vivid Burmese spoken storytelling style. Do not include markdown headers or meta descriptions. Just the voiceover script."
    )
    
    # 1. Try Gemini 3.5 Flash
    try:
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel("gemini-2.5-flash") # Stable Fast Flash
        response = await asyncio.to_thread(model.generate_content, f"{system_prompt}\n\nTranscript:\n{raw_transcript}")
        if response.text:
            return response.text.strip()
    except Exception as e:
        print(f"Gemini 3.5 Flash failed: {e}. Trying Gemini 3.8 / Pro...")

    # 2. Try Gemini Flash Alternative
    try:
        model2 = genai.GenerativeModel("gemini-1.5-flash")
        response = await asyncio.to_thread(model2.generate_content, f"{system_prompt}\n\nTranscript:\n{raw_transcript}")
        if response.text:
            return response.text.strip()
    except Exception as e:
        print(f"Gemini alternative failed: {e}. Falling back to Groq...")

    # 3. Fallback to Groq Llama-3.3-70b
    try:
        client = Groq(api_key=groq_key)
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_transcript}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.7
        )
        return chat_completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"Groq fallback failed: {e}")
        return raw_transcript # If all fails, use raw transcript

# ==========================================
# 8. Center Thumbnail Photo Generator
# ==========================================
def generate_center_thumbnail(video_path, output_thumb_path, font_path, title_text):
    temp_frame = output_thumb_path + "_temp.jpg"
    # Extract frame from 15% timestamp
    subprocess.run(["ffmpeg", "-y", "-ss", "00:00:03", "-i", video_path, "-vframes", "1", "-q:v", "2", temp_frame], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    if not os.path.exists(temp_frame):
        img = Image.new('RGB', (1080, 1920), color=(20, 20, 20))
    else:
        img = Image.open(temp_frame).convert("RGBA")
        os.remove(temp_frame)
        
    img = img.resize((1080, 1920))
    
    # Create dark vignette overlay for eye-catching center readability
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)
    draw_ov.rectangle([0, 700, 1080, 1220], fill=(0, 0, 0, 160)) # Center dark banner
    img = Image.alpha_composite(img, overlay).convert("RGB")
    
    draw = ImageDraw.Draw(img)
    try:
        fnt = ImageFont.truetype(font_path, 75)
    except Exception:
        fnt = ImageFont.load_default()
        
    # Center text calculation
    lines = [title_text[:20], title_text[20:40]] if len(title_text) > 20 else [title_text]
    y_text = 900
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=fnt)
        w = bbox[2] - bbox[0]
        x = (1080 - w) / 2
        # Draw thick shadow/stroke
        for offset in [(-3, -3), (3, -3), (-3, 3), (3, 3), (0, 4), (4, 0)]:
            draw.text((x + offset[0], y_text + offset[1]), line, font=fnt, fill=(0, 0, 0))
        draw.text((x, y_text), line, font=fnt, fill=(255, 235, 59)) # Vibrant yellow title
        y_text += 95
        
    img.save(output_thumb_path, "JPEG", quality=95)

# ==========================================
# 9. Main Video Pipeline (3-Concurrency)
# ==========================================
@app.on_message(filters.video & filters.private)
async def process_video_message(client, message):
    u_id = message.from_user.id
    u_data = get_user_data(u_id)
    
    if not u_data["groq_key"] or not u_data["gemini_key"]:
        await message.reply_text("⚠️ ကျေးဇူးပြု၍ ပထမဦးစွာ `/setgroq သင့်KEY` နှင့် `/setgemini သင့်KEY` ကို အသုံးပြု၍ Key များ ထည့်ပေးပါ။")
        return

    progress_msg = await message.reply_text("⏳ စတင်ရန် တန်းစီစောင့်ဆိုင်းနေပါသည်... (Max 3 Jobs)")
    
    async with SEMAPHORE:
        start_time = time.time()
        with tempfile.TemporaryDirectory() as workdir:
            input_video = os.path.join(workdir, "input.mp4")
            compressed_audio = os.path.join(workdir, "audio_comp.mp3")
            recap_audio = os.path.join(workdir, "recap_tts.mp3")
            srt_path = os.path.join(workdir, "subs.srt")
            output_video = os.path.join(workdir, "final_recap.mp4")
            thumb_path = os.path.join(workdir, "thumb.jpg")
            
            # Step 0: Download & Extract Audio
            await update_progress_ui(progress_msg, 0, 30, start_time)
            await message.download(file_name=input_video)
            
            await update_progress_ui(progress_msg, 0, 75, start_time)
            # FFmpeg: Extract mono 16kHz 32k mp3 (<25MB guaranteed)
            subprocess.run([
                "ffmpeg", "-y", "-i", input_video,
                "-vn", "-ar", "16000", "-ac", "1", "-b:a", "32k",
                compressed_audio
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            await update_progress_ui(progress_msg, 0, 100, start_time)
            
            # Step 1: AI Transcription & Scriptwriting
            await update_progress_ui(progress_msg, 1, 35, start_time)
            groq_client = Groq(api_key=u_data["groq_key"])
            
            # Groq Whisper
            with open(compressed_audio, "rb") as f:
                transcription = groq_client.audio.transcriptions.create(
                    file=(os.path.basename(compressed_audio), f.read()),
                    model="whisper-large-v3",
                    response_format="text"
                )
            
            await update_progress_ui(progress_msg, 1, 75, start_time)
            # Gemini -> Groq Fallback Script Generation
            recap_script = await generate_recap_script(
                u_data["groq_key"],
                u_data["gemini_key"],
                transcription,
                u_data["settings"]["style"]
            )
            await update_progress_ui(progress_msg, 1, 100, start_time)
            
            # Step 2: Audio Synthesis (Edge-TTS)
            await update_progress_ui(progress_msg, 2, 45, start_time)
            s_set = u_data["settings"]
            tts_voice = VOICE_MAP.get(s_set["voice"], "my-MM-ThihaNeural")
            
            # Generate Edge-TTS audio with Pitch & Rate
            communicate = edge_tts.Communicate(
                text=recap_script,
                voice=tts_voice,
                pitch=s_set["pitch"],
                rate=f"{s_set['speed']}x"
            )
            await communicate.save(recap_audio)
            
            # Fast SRT generation for Subtitles
            # Simple clean timing generator matching recap duration
            dur_proc = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", recap_audio], stdout=subprocess.PIPE, text=True)
            try:
                audio_dur = float(dur_proc.stdout.strip())
            except Exception:
                audio_dur = 30.0
                
            words = recap_script.split()
            chunk_size = 6
            chunks = [" ".join(words[i:i+chunk_size]) for i in range(0, len(words), chunk_size)]
            sec_per_chunk = audio_dur / max(len(chunks), 1)
            
            with open(srt_path, "w", encoding="utf-8") as srt_file:
                for idx, chk in enumerate(chunks):
                    t_start = idx * sec_per_chunk
                    t_end = (idx + 1) * sec_per_chunk
                    s_h, s_rem = divmod(int(t_start), 3600); s_m, s_s = divmod(s_rem, 60); s_ms = int((t_start - int(t_start)) * 1000)
                    e_h, e_rem = divmod(int(t_end), 3600); e_m, e_s = divmod(e_rem, 60); e_ms = int((t_end - int(t_end)) * 1000)
                    srt_file.write(f"{idx+1}\n{s_h:02d}:{s_m:02d}:{s_s:02d},{s_ms:03d} --> {e_h:02d}:{e_m:02d}:{e_s:02d},{e_ms:03d}\n{chk}\n\n")
            await update_progress_ui(progress_msg, 2, 100, start_time)
            
            # Step 3: FFmpeg Render (Blur, Subtitle, Audio Ducking)
            await update_progress_ui(progress_msg, 3, 20, start_time)
            
            # Subtitle Position calculation
            # BorderStyle=1 (Outline only, NO black box), Outline=2 (Black border), PrimaryColour=&H00FFFFFF (White)
            margin_v = "30"
            alignment = "2" # Bottom Center
            if s_set["sub_pos"] == "အောက်များ":
                margin_v = "25"; alignment = "2"
            elif s_set["sub_pos"] == "အောက်နည်း":
                margin_v = "75"; alignment = "2"
            elif s_set["sub_pos"] == "ပေါ်များ":
                margin_v = "25"; alignment = "6" # Top Center
            elif s_set["sub_pos"] == "ပေါ်နည်း":
                margin_v = "75"; alignment = "6"
                
            sub_style = f"FontName={s_set['font']},FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2.5,Shadow=0,Alignment={alignment},MarginV={margin_v}"
            escaped_srt = srt_path.replace(":", "\\:").replace("\\", "/")
            
            # Blur Canvas (TikTok 9:16 - 1080x1920)
            filter_complex = (
                f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:5[bg];"
                f"[0:v]scale=1080:-1[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,subtitles={escaped_srt}:force_style='{sub_style}'[v]"
            )
            
            # Audio Mixing / Original Audio Retention (Audio Ducking)
            if s_set["orig_audio"]:
                audio_filter = "[0:a]volume=0.15[orig];[1:a]volume=3.5[tts];[orig][tts]amix=inputs=2:duration=first[a]"
            else:
                audio_filter = "[1:a]volume=3.5[a]"
                
            await update_progress_ui(progress_msg, 3, 60, start_time)
            
            render_cmd = [
                "ffmpeg", "-y",
                "-i", input_video,
                "-i", recap_audio,
                "-filter_complex", f"{filter_complex};{audio_filter}",
                "-map", "[v]", "-map", "[a]",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24",
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",
                output_video
            ]
            subprocess.run(render_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Generate Center Thumbnail Photo
            generate_center_thumbnail(output_video, thumb_path, s_set["font"], f"{s_set['style']} Recap")
            await update_progress_ui(progress_msg, 3, 100, start_time)
            
            # Step 4: Uploading to Telegram
            await update_progress_ui(progress_msg, 4, 50, start_time)
            await client.send_video(
                chat_id=message.chat.id,
                video=output_video,
                thumb=thumb_path if os.path.exists(thumb_path) else None,
                caption=f"🎬 **{s_set['style']} Movie Recap**\n🎙️ အသံ: {s_set['voice']}\n⚡ Pitch/Speed: {s_set['pitch']} / {s_set['speed']}x",
                reply_to_message_id=message.id
            )
            await update_progress_ui(progress_msg, 4, 100, start_time)

# ==========================================
# 10. Start Application
# ==========================================
if __name__ == "__main__":
    print("🚀 SANMA Movie Recap Bot is running on GitHub/Fadehost...")
    app.run()
