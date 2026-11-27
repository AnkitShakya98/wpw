import os
import re
import uuid
import json
import asyncio
import logging
import aiohttp
import urllib.parse
from datetime import datetime
from pyrogram import filters, Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from vars import API_ID, API_HASH, BOT_TOKEN
from utils import progress_bar

app = Client(
    "bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)
# ==========================================
# ⚙️ CONFIG
# ==========================================
DOWNLOAD_DIR = "downloads"
ARIA2_CONNECTIONS = 16
OWNER_NAME = "Ankit Shakya"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

log = logging.getLogger(__name__)

# ==========================================
# 🧠 STATE
# ==========================================
db_cache = {}
user_states = {}
pending_tokens = {}
pending_cookies = {}
user_quality = {}
pending_batch = {}
sent_msg_ids = {}

# ==========================================
# 🔧 HELPERS
# ==========================================
def get_pw_headers(token):
    return {
        'authority': 'api.penpencil.co',
        'accept': '*/*',
        'authorization': f'Bearer {token}',
        'client-id': '5eb393ee95fab7468a79d189',
        'client-type': 'WEB',
        'client-version': '3219',
        'content-type': 'application/json',
        'origin': 'https://www.pw.live',
        'randomid': str(uuid.uuid4()),
        'referer': 'https://www.pw.live/',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139.0.0.0 Safari/537.36',
        'x-sdk-version': '0.0.20'
    }

def get_learnx_headers(cookie, batch_id, sub_slug, child_id, topic_id=""):
    return {
        'authority': 'www.learnxpw.site',
        'accept': '*/*',
        'cookie': cookie,
        'referer': f"https://www.learnxpw.site/watch?batchId={batch_id}&SubjectId={sub_slug}&ChildId={child_id}&Type=penpencilvdo&VideoUrl=&isLocked=true&topicId={urllib.parse.quote(topic_id)}",
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/109.0.0.0 Safari/537.36',
    }

async def fetch_api(url, headers):
    log.info(f"🌐 API GET: {url[:120]}")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=30) as r:
                if r.status == 200:
                    return json.loads(await r.text())
                log.warning(f"⚠️ API {r.status}: {url[:80]}")
        except Exception as e:
            log.error(f"❌ fetch_api: {e}")
    return None

def natural_sort_key(text):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r'(\d+)', text or "")]

def clean_filename(title, owner):
    n = (title.replace("\t","").replace(":","").replace("/","")
         .replace("+","").replace("#","").replace("|","")
         .replace("@","").replace("*","").replace("https","")
         .replace("http","").strip())
    return f"{n[:60]} {owner}".strip()

def build_caption(count, name1, ext, res, b_name):
    num = str(count).zfill(3)
    if ext == "pdf":
        return (
            f"**\n╭──────.★..─╮\n{num}\n╰─..★.──────╯**\n\n"
            f"**📝 Title:** {name1} \n"
            f"**├── Extention :** {OWNER_NAME}.pdf\n"
            f"**├── Resolution :** [None]\n\n"
            f"<pre><code>📚 Batch Name: {b_name}</code></pre>\n\n"
            f"**📥 Extracted By :**\n╭──────────.✨..─╮\n\n      {OWNER_NAME}\n\n╰─..✨.──────────╯\n\n"
            f"**<pre><code>━━━━━✦𝐀𝐍𝐊𝐈𝐓❤️✦━━━━━</code></pre>**"
        )
    return (
        f"**\n╭──────.★..─╮\n{num}\n╰─..★.──────╯**\n\n"
        f"**📝 Title:** {name1} \n"
        f"**├── Extention :** {OWNER_NAME}.mkv\n"
        f"**├── Resolution :** [{res}]\n\n"
        f"<pre><code>📚 Batch Name: {b_name}</code></pre>\n\n"
        f"**📥 Extracted By :**\n╭──────────.✨..─╮\n\n      {OWNER_NAME}\n\n╰─..✨.──────────╯\n\n"
        f"**<pre><code>━━━━━✦𝐀𝐍𝐊𝐈𝐓❤️✦━━━━━</code></pre>**"
    )

async def validate_token(token):
    data = await fetch_api(
        "https://api.penpencil.co/batch-service/v1/batches/purchased-batches?page=1&type=ALL&amount=free",
        get_pw_headers(token)
    )
    return bool(data and data.get("success"))

# ==========================================
# 🎬 SIGNED URL + PDF
# ==========================================
async def get_signed_url(batch_id, sub_slug, child_id, topic, cookie):
    url = f"https://www.learnxpw.site/api/video-url?batch_id={batch_id}&subject_id={sub_slug}&video_id={child_id}"
    for attempt in range(3):
        data = await fetch_api(url, get_learnx_headers(cookie, batch_id, sub_slug, child_id, topic))
        if data and data.get("success"):
            d = data["data"]
            return d.get("url","") + d.get("signedUrl","")
        log.warning(f"⚠️ signed_url retry {attempt+1}/3")
        await asyncio.sleep(2)
    return None

async def get_pdf_url(batch_id, sub_slug, pdf_id, attachment_id, topic, cookie):
    url = f"https://www.learnxpw.site/api/GetPdf?BatchId={batch_id}&SubjectId={sub_slug}&PdfId={pdf_id}&AttachmentId={attachment_id}"
    for attempt in range(3):
        data = await fetch_api(url, get_learnx_headers(cookie, batch_id, sub_slug, pdf_id, topic))
        if data and data.get("success"):
            d = data["data"]
            return d.get("baseUrl","") + d.get("key","")
        await asyncio.sleep(2)
    return None

# ==========================================
# ⬇️ DOWNLOAD
# ==========================================
async def get_m3u8_from_api(signed_url, quality):
    api = f"https://ankitshakyaxapi.vercel.app/download?mpd_url={urllib.parse.quote(signed_url, safe='')}&quality={quality}"
    log.info(f"🎞️ m3u8 API: quality={quality}")
    async with aiohttp.ClientSession() as s:
        try:
            async with s.get(api, timeout=60) as r:
                if r.status == 200:
                    text = (await r.text()).strip()
                    if text.startswith("#EXTM3U"):
                        path = os.path.join(DOWNLOAD_DIR, f"{uuid.uuid4().hex}.m3u8")
                        with open(path, "w") as f:
                            f.write(text)
                        return path
                    if text.startswith("http"):
                        return text
                    try:
                        d = json.loads(text)
                        return d.get("url") or d.get("m3u8") or d.get("playlist")
                    except:
                        pass
        except Exception as e:
            log.error(f"❌ get_m3u8: {e}")
    return None

async def download_m3u8(m3u8_source, filepath):
    cmd = [
        "yt-dlp",
        "--downloader", "aria2c",
        "--downloader-args", f"aria2c:-x {ARIA2_CONNECTIONS} -s {ARIA2_CONNECTIONS} -k 1M",
        "--hls-prefer-native",
        "-o", filepath,
        m3u8_source
    ]
    log.info(f"⬇️ yt-dlp: {os.path.basename(filepath)}")
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()
    for f in os.listdir(os.path.dirname(filepath)):
        if f.startswith(os.path.basename(filepath)):
            return os.path.join(os.path.dirname(filepath), f)
    return None

async def download_pdf(url, filepath):
    log.info(f"⬇️ PDF: {os.path.basename(filepath)}")
    async with aiohttp.ClientSession() as s:
        try:
            async with s.get(url, timeout=120) as r:
                if r.status == 200:
                    with open(filepath, "wb") as f:
                        f.write(await r.read())
                    return filepath
        except Exception as e:
            log.error(f"❌ pdf: {e}")
    return None

# ==========================================
# 📋 ITEM LIST BUILDER
# ==========================================
def build_item_list(items, batch_name):
    lines = [f"📦 **Batch:** `{batch_name}`\n", f"📊 **Total:** `{len(items)}` items\n"]
    for i, it in enumerate(items, start=1):
        if it["type"] == "LECTURE":
            lines.append(f"`{i}.` 🎬 {it['topic']}")
        else:
            lines.append(f"`{i}.` 📄 {it['topic']}")
    return "\n".join(lines)

# ==========================================
# 🔑 /pw
# ==========================================
@app.on_message(filters.command("pw") & filters.private)
async def pw_cmd(client, message):
    uid = message.from_user.id
    log.info(f"📩 /pw from {uid}")
    pending_tokens.pop(uid, None)
    pending_cookies.pop(uid, None)
    pending_batch.pop(uid, None)
    sent_msg_ids.pop(uid, None)
    user_states[uid] = {"state": "WAIT_FOR_TOKEN"}
    await message.reply_text("🔑 **Step 1/2 — PW JWT Token bhejein:**")

@app.on_message(filters.command("cancel") & filters.private)
async def cancel_cmd(client, message):
    uid = message.from_user.id
    log.info(f"📩 /cancel from {uid}")
    user_states.pop(uid, None)
    pending_tokens.pop(uid, None)
    pending_cookies.pop(uid, None)
    pending_batch.pop(uid, None)
    await message.reply_text("❌ Cancelled. `/pw` se dobara shuru karein.")

# ==========================================
# 📝 TEXT HANDLER
# ==========================================
@app.on_message(filters.text & filters.private)
async def handle_text(client, message):
    uid = message.from_user.id
    log.info(f"📩 TEXT from {uid}: '{message.text[:40]}' | state={user_states.get(uid)}")

    if uid not in user_states:
        return
    st = user_states[uid].get("state")

    # ---------- TOKEN ----------
    if st == "WAIT_FOR_TOKEN":
        token = message.text.strip()
        try: await message.delete()
        except: pass
        proc = await message.reply_text("⏳ Token verify...")
        log.info(f"🔑 token verify for {uid}")
        if await validate_token(token):
            pending_tokens[uid] = token
            user_states[uid] = {"state": "WAIT_FOR_COOKIES"}
            await proc.edit_text("✅ **Token valid!**\n\n🍪 **Step 2/2 — Cookies bhejein:**\nFormat: `lx_in_cf=...`")
        else:
            user_states.pop(uid, None)
            await proc.edit_text("❌ Invalid token. `/pw` dobara.")
        return

    # ---------- COOKIES ----------
    if st == "WAIT_FOR_COOKIES":
        cookie = message.text.strip()
        try: await message.delete()
        except: pass
        if "lx_in_cf=" not in cookie:
            return await message.reply_text("❌ Cookies me `lx_in_cf=` hona chahiye.")
        pending_cookies[uid] = cookie
        user_states.pop(uid, None)
        log.info(f"🍪 cookies saved for {uid}")
        await message.reply_text("✅ Cookies saved!")
        await show_main_menu(message)
        return

    # ---------- SEARCH ----------
    if st == "WAIT_FOR_BATCH_SEARCH":
        q = message.text.strip()
        user_states.pop(uid, None)
        proc = await message.reply_text(f"⏳ Searching '{q}'...")
        log.info(f"🔍 search '{q}' for {uid}")
        token = pending_tokens.get(uid)
        if not token:
            return await proc.edit_text("❌ Token missing.")
        data = await fetch_api(
            f"https://api.penpencil.co/v3/batches/search?name={urllib.parse.quote(q)}",
            get_pw_headers(token)
        )
        if data and data.get("success") and data.get("data"):
            buttons = []
            for b in data["data"]:
                u = uuid.uuid4().hex[:8]
                db_cache[u] = {"b_id": b.get("_id"), "name": b.get("name")}
                buttons.append([InlineKeyboardButton((b.get("name") or "?")[:55], callback_data=f"bat_{u}")])
            buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_main")])
            log.info(f"✅ {len(data['data'])} batches found")
            await proc.edit_text(f"🔍 Results for '{q}':", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await proc.edit_text("❌ Batch nahi mila.")
        return

    # ---------- DATE ----------
    if st == "WAIT_FOR_DATE":
        u = user_states[uid].get("uid")
        ds = message.text.strip()
        try:
            datetime.strptime(ds, "%Y-%m-%d")
        except ValueError:
            return await message.reply_text("❌ `YYYY-MM-DD` format")
        user_states.pop(uid, None)
        token, cookie = pending_tokens.get(uid), pending_cookies.get(uid)
        quality = user_quality.get(uid, "720")
        log.info(f"📅 date {ds} for {uid}, quality={quality}")
        if not token or not cookie:
            return await message.reply_text("❌ `/pw` bhejein.")
        proc = await message.reply_text(f"⏳ Fetching {ds}...")
        await prepare_schedule_items(proc, uid, ds, token, cookie, quality)
        return

    # ---------- INDEX ----------
    if st == "WAIT_FOR_INDEX":
        try:
            idx = int(message.text.strip())
        except ValueError:
            return await message.reply_text("❌ Number bhejein")
        pb = pending_batch.get(uid)
        if not pb:
            user_states.pop(uid, None)
            return await message.reply_text("❌ Session expired.")
        total = len(pb["items"])
        if idx < 1 or idx > total:
            return await message.reply_text(f"❌ Index 1-{total}")
        user_states.pop(uid, None)
        try: await message.delete()
        except: pass
        items_to_dl = pb["items"][idx-1:]
        log.info(f"▶️ index {idx}/{total} download start for {uid}")
        await start_download(client, message, uid, items_to_dl, idx, total, pb)
        return

# ==========================================
# 🏠 MENUS
# ==========================================
async def show_main_menu(message):
    log.info(f"🏠 main menu for {message.from_user.id}")
    buttons = [[InlineKeyboardButton("🔍 Search Batch", callback_data="menu_search")]]
    await message.reply_text("👋 **Welcome!**\nOption:", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"^back_main$"))
async def back_main(c, cb: CallbackQuery):
    log.info(f"🔙 back_main from {cb.from_user.id}")
    await cb.answer()
    buttons = [[InlineKeyboardButton("🔍 Search Batch", callback_data="menu_search")]]
    await cb.message.edit_text("👋 **Welcome!**\nOption:", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"^menu_search$"))
async def menu_search(c, cb: CallbackQuery):
    log.info(f"🔍 menu_search from {cb.from_user.id}")
    await cb.answer()
    user_states[cb.from_user.id] = {"state": "WAIT_FOR_BATCH_SEARCH"}
    await cb.message.edit_text("✍️ **Batch ka naam type karein:**")

# ==========================================
# 🎯 BATCH → QUALITY
# ==========================================
@app.on_callback_query(filters.regex(r"^bat_(.*)"))
async def batch_selected(c, cb: CallbackQuery):
    log.info(f"🎯 bat selected: {cb.data}")
    await cb.answer()
    uid = cb.matches[0].group(1)
    b = db_cache.get(uid)
    if not b:
        return await cb.answer("❌ Expired", show_alert=True)
    buttons = [
        [InlineKeyboardButton("🎬 1080p", callback_data=f"q_1080_{uid}")],
        [InlineKeyboardButton("🎬 720p", callback_data=f"q_720_{uid}")],
        [InlineKeyboardButton("🎬 480p", callback_data=f"q_480_{uid}")],
        [InlineKeyboardButton("🎬 360p", callback_data=f"q_360_{uid}")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
    ]
    await cb.message.edit_text(f"✅ **Batch:** `{b['name']}`\n\n🎯 **Quality chunein:**", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"^q_(\d+)_(.*)$"))
async def quality_selected(c, cb: CallbackQuery):
    log.info(f"🎯 quality selected: {cb.data}")
    await cb.answer()
    quality, uid = cb.matches[0].group(1), cb.matches[0].group(2)
    b = db_cache.get(uid)
    if not b:
        return await cb.answer("❌ Expired", show_alert=True)
    user_quality[cb.from_user.id] = quality
    log.info(f"✅ quality {quality}p for {cb.from_user.id}")
    buttons = [
        [InlineKeyboardButton("📅 Schedule", callback_data=f"opt_sch_{uid}")],
        [InlineKeyboardButton("📚 Chapter Wise", callback_data=f"opt_chp_{uid}")],
        [InlineKeyboardButton("📒 Study Material", callback_data=f"opt_stu_{uid}")],
        [InlineKeyboardButton("📥 Full Batch", callback_data=f"full_{uid}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"bat_{uid}")]
    ]
    await cb.message.edit_text(
        f"✅ **Batch:** `{b['name']}`\n🎯 **Quality:** `{quality}p`\n\nKya download karna hai?",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ==========================================
# 📅 SCHEDULE
# ==========================================
@app.on_callback_query(filters.regex(r"^opt_sch_(.*)"))
async def schedule_menu(c, cb: CallbackQuery):
    log.info(f"📅 schedule_menu: {cb.data}")
    await cb.answer()
    uid = cb.matches[0].group(1)
    buttons = [
        [InlineKeyboardButton("📅 Today", callback_data=f"sch_today_{uid}")],
        [InlineKeyboardButton("🗓 Specific Date", callback_data=f"sch_date_{uid}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"q_{user_quality.get(cb.from_user.id,'720')}_{uid}")]
    ]
    await cb.message.edit_text("📅 **Din chunein:**", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"^sch_today_(.*)"))
async def schedule_today(c, cb: CallbackQuery):
    log.info(f"📅 sch_today: {cb.data}")
    await cb.answer("⏳ Fetching...")
    uid = cb.matches[0].group(1)
    token, cookie = pending_tokens.get(cb.from_user.id), pending_cookies.get(cb.from_user.id)
    quality = user_quality.get(cb.from_user.id, "720")
    if not token or not cookie:
        return await cb.answer("❌ `/pw`", show_alert=True)
    await prepare_schedule_items(cb.message, cb.from_user.id, datetime.today().strftime('%Y-%m-%d'), token, cookie, quality)

@app.on_callback_query(filters.regex(r"^sch_date_(.*)"))
async def schedule_date(c, cb: CallbackQuery):
    log.info(f"📅 sch_date: {cb.data}")
    await cb.answer()
    uid = cb.matches[0].group(1)
    user_states[cb.from_user.id] = {"state": "WAIT_FOR_DATE", "uid": uid}
    await cb.message.edit_text("✍️ **Date (`YYYY-MM-DD`):**")

async def prepare_schedule_items(message_obj, uid, target_date, token, cookie, quality):
    data = db_cache.get(uid)
    if not data:
        return await message_obj.edit_text("❌ Expired")
    batch_id, batch_name = data["b_id"], data["name"]
    log.info(f"📅 preparing schedule for {uid}: {target_date}")
    await message_obj.edit_text(f"⏳ **{target_date}** fetch...")

    details = await fetch_api(f"https://api.penpencil.co/v3/batches/{batch_id}/details", get_pw_headers(token))
    sub_map = {}
    if details and details.get("success"):
        for s in details.get("data", {}).get("subjects", []):
            if s.get("_id") and s.get("slug"):
                sub_map[s["_id"]] = s["slug"]

    res = await fetch_api(
        f"https://api.penpencil.co/v2/batches/{batch_id}/weekly-schedules?batchId={batch_id}&batchSubjectId=&startDate={target_date}&endDate={target_date}&page=1",
        get_pw_headers(token)
    )
    if not (res and res.get("success") and res.get("data")):
        return await message_obj.edit_text(f"❌ `{target_date}` me kuch nahi.")

    items = []
    for item in res["data"]:
        typ = item.get("type", "")
        det = item.get("videoDetails") if typ == "LECTURE" else item.get("notesDetails")
        if not det:
            det = item.get("videoDetails") or item.get("notesDetails") or item.get("bulkScheduleDetails") or {}
        if not det: continue
        sch_id = det.get("_id")
        so = det.get("subjectId", {})
        sub_id = so.get("_id","") if isinstance(so, dict) else ""
        if not sub_id or not sch_id: continue
        sub_slug = sub_map.get(sub_id, sub_id)

        dr = await fetch_api(
            f"https://api.penpencil.co/v1/batches/{batch_id}/subject/{sub_id}/schedule/{sch_id}/schedule-details",
            get_pw_headers(token)
        )
        if not (dr and dr.get("success") and dr.get("data")): continue
        d = dr["data"]
        topic = d.get("topic", "Class")

        vid = d.get("videoDetails") or {}
        if vid.get("videoUrl") or vid.get("embedCode"):
            items.append({"type": "LECTURE", "topic": topic, "sch_id": sch_id, "sub_slug": sub_slug})

        for hw in d.get("homeworkIds", []):
            for att in hw.get("attachmentIds", []):
                key = att.get("key")
                if not key: continue
                items.append({
                    "type": "PDF",
                    "topic": hw.get("topic", topic),
                    "pdf_url": att.get("baseUrl","") + key,
                })

    if not items:
        return await message_obj.edit_text("❌ Koi item nahi mila.")

    pending_batch[uid] = {
        "items": items,
        "batch_name": batch_name,
        "batch_id": batch_id,
        "token": token,
        "cookie": cookie,
        "quality": quality,
    }
    user_states[uid] = {"state": "WAIT_FOR_INDEX"}

    lst = build_item_list(items, batch_name)
    buttons = [[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]
    log.info(f"📋 {len(items)} items prepared for {uid}")
    await message_obj.edit_text(
        f"{lst}\n\n✍️ **Total {len(items)} items. Kis index se download karna hai? (1-{len(items)})**",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ==========================================
# 📚 CHAPTER
# ==========================================
@app.on_callback_query(filters.regex(r"^opt_chp_(.*)"))
async def chapter_subjects(c, cb: CallbackQuery):
    log.info(f"📚 opt_chp: {cb.data}")
    await cb.answer()
    uid = cb.matches[0].group(1)
    token = pending_tokens.get(cb.from_user.id)
    b = db_cache.get(uid)
    if not b or not token:
        return await cb.answer("❌ Expired", show_alert=True)
    await cb.message.edit_text("⏳ Subjects...")
    data = await fetch_api(f"https://api.penpencil.co/v3/batches/{b['b_id']}/details", get_pw_headers(token))
    if not (data and data.get("success")):
        return await cb.message.edit_text("❌ Error")
    buttons = []
    for s in data["data"].get("subjects", []):
        u = uuid.uuid4().hex[:8]
        db_cache[u] = {"b_id": b["b_id"], "batch_name": b["name"], "sub_id": s["_id"], "sub_slug": s.get("slug","")}
        buttons.append([InlineKeyboardButton(s.get("subject","?"), callback_data=f"chp_sub_{u}")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"q_{user_quality.get(cb.from_user.id,'720')}_{uid}")])
    await cb.message.edit_text("📚 **Subject:**", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"^chp_sub_(.*)"))
async def chapter_list(c, cb: CallbackQuery):
    log.info(f"📚 chp_sub: {cb.data}")
    await cb.answer()
    uid = cb.matches[0].group(1)
    d = db_cache.get(uid)
    token = pending_tokens.get(cb.from_user.id)
    if not d or not token:
        return await cb.answer("❌ Expired", show_alert=True)
    await cb.message.edit_text("⏳ Chapters...")
    res = await fetch_api(
        f"https://api.penpencil.co/batch-service/v1/batch-tags/{d['b_id']}/subject/{d['sub_id']}/topics?page=1&batchTagType=UNITS&limit=20",
        get_pw_headers(token)
    )
    if not (res and res.get("success")):
        return await cb.message.edit_text("❌ Error")
    chs = res.get("data", [])
    chs.sort(key=lambda x: natural_sort_key(x.get("name","")))
    buttons = []
    for ch in chs:
        u = uuid.uuid4().hex[:8]
        db_cache[u] = {**d, "tag_id": ch["_id"], "name": ch.get("name")}
        buttons.append([InlineKeyboardButton(ch.get("name","")[:40], callback_data=f"chp_item_{u}")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"opt_chp_{uid}")])
    await cb.message.edit_text("📑 **Chapter:**", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"^chp_item_(.*)"))
async def chapter_prepare(c, cb: CallbackQuery):
    log.info(f"📚 chp_item: {cb.data}")
    await cb.answer("⏳ Fetching...")
    uid = cb.matches[0].group(1)
    d = db_cache.get(uid)
    token, cookie = pending_tokens.get(cb.from_user.id), pending_cookies.get(cb.from_user.id)
    quality = user_quality.get(cb.from_user.id, "720")
    if not d or not token or not cookie:
        return await cb.answer("❌ Expired", show_alert=True)
    await prepare_tag_items(cb.message, cb.from_user.id, d, token, cookie, quality)

# ==========================================
# 📒 STUDY
# ==========================================
@app.on_callback_query(filters.regex(r"^opt_stu_(.*)"))
async def study_subjects(c, cb: CallbackQuery):
    log.info(f"📒 opt_stu: {cb.data}")
    await cb.answer()
    uid = cb.matches[0].group(1)
    token = pending_tokens.get(cb.from_user.id)
    b = db_cache.get(uid)
    if not b or not token:
        return await cb.answer("❌ Expired", show_alert=True)
    await cb.message.edit_text("⏳ Subjects...")
    data = await fetch_api(f"https://api.penpencil.co/v3/batches/{b['b_id']}/details", get_pw_headers(token))
    if not (data and data.get("success")):
        return await cb.message.edit_text("❌ Error")
    buttons = []
    for s in data["data"].get("subjects", []):
        u = uuid.uuid4().hex[:8]
        db_cache[u] = {"b_id": b["b_id"], "batch_name": b["name"], "sub_id": s["_id"], "sub_slug": s.get("slug","")}
        buttons.append([InlineKeyboardButton(s.get("subject","?"), callback_data=f"stu_sub_{u}")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"q_{user_quality.get(cb.from_user.id,'720')}_{uid}")])
    await cb.message.edit_text("📚 **Subject:**", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"^stu_sub_(.*)"))
async def study_folders(c, cb: CallbackQuery):
    log.info(f"📒 stu_sub: {cb.data}")
    await cb.answer()
    uid = cb.matches[0].group(1)
    d = db_cache.get(uid)
    token = pending_tokens.get(cb.from_user.id)
    if not d or not token:
        return await cb.answer("❌ Expired", show_alert=True)
    await cb.message.edit_text("⏳ Folders...")
    res = await fetch_api(
        f"https://api.penpencil.co/batch-service/v1/batch-tags/{d['b_id']}/subject/{d['sub_id']}/topics?page=1&batchTagType=STUDY_MATERIAL&limit=20",
        get_pw_headers(token)
    )
    if not (res and res.get("success")):
        return await cb.message.edit_text("❌ Error")
    fs = res.get("data", [])
    fs.sort(key=lambda x: natural_sort_key(x.get("name","")))
    buttons = []
    for fo in fs:
        u = uuid.uuid4().hex[:8]
        db_cache[u] = {**d, "tag_id": fo["_id"], "name": fo.get("name")}
        buttons.append([InlineKeyboardButton(fo.get("name","")[:40], callback_data=f"stu_item_{u}")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"opt_stu_{uid}")])
    await cb.message.edit_text("📑 **Folder:**", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"^stu_item_(.*)"))
async def study_prepare(c, cb: CallbackQuery):
    log.info(f"📒 stu_item: {cb.data}")
    await cb.answer("⏳ Fetching...")
    uid = cb.matches[0].group(1)
    d = db_cache.get(uid)
    token, cookie = pending_tokens.get(cb.from_user.id), pending_cookies.get(cb.from_user.id)
    quality = user_quality.get(cb.from_user.id, "720")
    if not d or not token or not cookie:
        return await cb.answer("❌ Expired", show_alert=True)
    await prepare_tag_items(cb.message, cb.from_user.id, d, token, cookie, quality)

# ==========================================
# 🔄 TAG ITEMS PREPARER
# ==========================================
async def prepare_tag_items(message_obj, user_id, d, token, cookie, quality):
    batch_id = d["b_id"]; batch_name = d["batch_name"]
    sub_id = d["sub_id"]; sub_slug = d.get("sub_slug", sub_id)
    tag_id = d["tag_id"]; title = d.get("name","Content")
    log.info(f"🔍 preparing tag items: {title} for {user_id}")

    await message_obj.edit_text(f"⏳ **{title}** fetch...")
    all_entries = []
    skip, limit = 0, 20
    while skip < 2000:
        res = await fetch_api(
            f"https://api.penpencil.co/batch-service/v3/batch-subject-schedules/{batch_id}/subject/{sub_id}/contents?skip={skip}&limit={limit}&contentType=ALL&contentFilter=ALL&tagId={tag_id}",
            get_pw_headers(token)
        )
        if not (res and res.get("success") and res.get("data")): break
        all_entries.extend(res["data"])
        if len(res["data"]) < limit: break
        skip += limit
        await asyncio.sleep(0.2)

    all_entries.sort(key=lambda e: natural_sort_key(e.get("data",{}).get("topic","")))
    items = []
    for entry in all_entries:
        item = entry.get("data", {})
        topic = item.get("topic", "Unknown")
        typ = entry.get("type","")
        if typ == "LECTURE":
            real_id = item.get("_id")
            items.append({"type": "LECTURE", "topic": topic, "sch_id": real_id, "sub_slug": sub_slug})
        for hw in item.get("homeworkIds", []):
            for att in hw.get("attachmentIds", []):
                key = att.get("key")
                if not key: continue
                items.append({
                    "type": "PDF",
                    "topic": hw.get("topic", topic),
                    "pdf_url": att.get("baseUrl","") + key,
                })

    if not items:
        return await message_obj.edit_text("❌ Koi item nahi mila.")

    pending_batch[user_id] = {
        "items": items,
        "batch_name": batch_name,
        "batch_id": batch_id,
        "sub_slug": sub_slug,
        "token": token,
        "cookie": cookie,
        "quality": quality,
    }
    user_states[user_id] = {"state": "WAIT_FOR_INDEX"}

    lst = build_item_list(items, batch_name)
    buttons = [[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]
    log.info(f"📋 {len(items)} items prepared for {user_id}")
    await message_obj.edit_text(
        f"{lst}\n\n✍️ **Total {len(items)} items. Kis index se download karna hai? (1-{len(items)})**",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ==========================================
# 📥 FULL BATCH
# ==========================================
@app.on_callback_query(filters.regex(r"^full_(.*)"))
async def full_batch(c, cb: CallbackQuery):
    log.info(f"📥 full_batch: {cb.data}")
    await cb.answer("⏳ Full batch...")
    uid = cb.matches[0].group(1)
    d = db_cache.get(uid)
    token, cookie = pending_tokens.get(cb.from_user.id), pending_cookies.get(cb.from_user.id)
    quality = user_quality.get(cb.from_user.id, "720")
    if not d or not token or not cookie:
        return await cb.answer("❌ Expired", show_alert=True)

    batch_id, batch_name = d["b_id"], d["name"]
    await cb.message.edit_text(f"⏳ Full: `{batch_name}`...")

    det = await fetch_api(f"https://api.penpencil.co/v3/batches/{batch_id}/details", get_pw_headers(token))
    if not (det and det.get("success")):
        return await cb.message.edit_text("❌ Error")

    subs = det["data"].get("subjects", [])
    subs.sort(key=lambda s: natural_sort_key(s.get("subject","")))

    items = []
    for s in subs:
        sid, sslug = s["_id"], s.get("slug","")
        chs = []
        page = 1
        while page <= 20:
            r = await fetch_api(
                f"https://api.penpencil.co/batch-service/v1/batch-tags/{batch_id}/subject/{sid}/topics?page={page}&batchTagType=UNITS&limit=20",
                get_pw_headers(token)
            )
            if not (r and r.get("success")): break
            c2 = r.get("data", [])
            chs.extend(c2)
            if len(c2) < 20: break
            page += 1
            await asyncio.sleep(0.2)

        chs.sort(key=lambda c: natural_sort_key(c.get("name","")))
        for ch in chs:
            tag_id = ch.get("_id")
            if not tag_id: continue
            all_entries = []
            skip, limit = 0, 20
            while skip < 2000:
                res = await fetch_api(
                    f"https://api.penpencil.co/batch-service/v3/batch-subject-schedules/{batch_id}/subject/{sid}/contents?skip={skip}&limit={limit}&contentType=ALL&contentFilter=ALL&tagId={tag_id}",
                    get_pw_headers(token)
                )
                if not (res and res.get("success") and res.get("data")): break
                all_entries.extend(res["data"])
                if len(res["data"]) < limit: break
                skip += limit
                await asyncio.sleep(0.2)

            all_entries.sort(key=lambda e: natural_sort_key(e.get("data",{}).get("topic","")))
            for entry in all_entries:
                item = entry.get("data", {})
                topic = item.get("topic", "Unknown")
                typ = entry.get("type","")
                if typ == "LECTURE":
                    real_id = item.get("_id")
                    items.append({"type": "LECTURE", "topic": topic, "sch_id": real_id, "sub_slug": sslug})
                for hw in item.get("homeworkIds", []):
                    for att in hw.get("attachmentIds", []):
                        key = att.get("key")
                        if not key: continue
                        items.append({
                            "type": "PDF",
                            "topic": hw.get("topic", topic),
                            "pdf_url": att.get("baseUrl","") + key,
                        })

    if not items:
        return await cb.message.edit_text("❌ Koi item nahi mila.")

    pending_batch[cb.from_user.id] = {
        "items": items,
        "batch_name": batch_name,
        "batch_id": batch_id,
        "token": token,
        "cookie": cookie,
        "quality": quality,
    }
    user_states[cb.from_user.id] = {"state": "WAIT_FOR_INDEX"}

    lst = build_item_list(items, batch_name)
    buttons = [[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]
    log.info(f"📋 {len(items)} full items for {cb.from_user.id}")
    await cb.message.edit_text(
        f"{lst}\n\n✍️ **Total {len(items)} items. Kis index se download karna hai? (1-{len(items)})**",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ==========================================
# ⬇️ DOWNLOAD LOOP
# ==========================================
async def start_download(client, message, user_id, items, start_idx, total, pb):
    batch_name = pb["batch_name"]
    batch_id = pb["batch_id"]
    token = pb["token"]
    cookie = pb["cookie"]
    quality = pb["quality"]

    log.info(f"⬇️ download start {start_idx}-{total} for {user_id}")
    sent_msg_ids[user_id] = []
    prog = await message.reply_text(f"⏳ Download shuru: {start_idx}/{total}")

    count = start_idx - 1

    for i, it in enumerate(items, start=start_idx):
        count += 1
        try:
            if it["type"] == "LECTURE":
                await prog.edit_text(f"🎬 [{i}/{total}] `{it['topic']}`")
                log.info(f"🎬 video {i}/{total}: {it['topic']}")
                signed = await get_signed_url(batch_id, it["sub_slug"], it["sch_id"], it["topic"], cookie)
                if signed:
                    m3u8 = await get_m3u8_from_api(signed, quality)
                    if m3u8:
                        n1 = clean_filename(it["topic"], OWNER_NAME)
                        fp = os.path.join(DOWNLOAD_DIR, f"{n1}.mkv")
                        f = await download_m3u8(m3u8, fp)
                        if f:
                            cap = build_caption(count, n1, "mkv", f"{quality}p", batch_name)
                            await message.reply_document(
                                document=f,
                                caption=cap,
                                progress=progress_bar,
                                progress_args=(prog, asyncio.get_event_loop().time())
                            )
                            try: os.remove(f)
                            except: pass
                            log.info(f"✅ uploaded video {i}/{total}")
            else:
                await prog.edit_text(f"📄 [{i}/{total}] `{it['topic']}`")
                log.info(f"📄 pdf {i}/{total}: {it['topic']}")
                n1 = clean_filename(it["topic"], OWNER_NAME)
                fp = os.path.join(DOWNLOAD_DIR, f"{n1}.pdf")
                f = await download_pdf(it["pdf_url"], fp)
                if f:
                    cap = build_caption(count, n1, "pdf", None, batch_name)
                    await message.reply_document(
                        document=f,
                        caption=cap,
                        progress=progress_bar,
                        progress_args=(prog, asyncio.get_event_loop().time())
                    )
                    try: os.remove(f)
                    except: pass
                    log.info(f"✅ uploaded pdf {i}/{total}")
        except Exception as e:
            log.error(f"❌ item {i}: {e}")

    try:
        await prog.delete()
    except: pass
    sent_msg_ids[user_id] = []
    pending_batch.pop(user_id, None)
    log.info(f"✅ download complete for {user_id}")


app.run()
