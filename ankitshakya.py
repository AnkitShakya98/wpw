
import os
import time
import datetime
import aiohttp
import aiofiles
import asyncio
import logging
import requests
import tgcrypto
import subprocess
import concurrent.futures
import sys
import hashlib
import shutil
import asyncio
import re

from utils import progress_bar

from pyrogram import Client, filters
from pyrogram.types import Message

from pytube import Playlist
from yt_dlp import YoutubeDL
import yt_dlp as youtube_dl
        
import os
import re
import requests
import subprocess
import asyncio
from pywidevine.cdm import Cdm
from pywidevine.device import Device
from pywidevine.pssh import PSSH

CDM_PATH = "pywidevine.wvd"

async def download_drm_video(mpd_url, pallycon_token, output_name):
    # Extension add karna
    if not output_name.endswith('.mp4'):
        output_name += '.mp4'
        
    try:
        # ================= HEADER 1 =================
        # MPD fetch karne ke liye (Akamai/Appx CDN Header)
        # Isme studyparcham ka referer nahi jayega, na hi cookie
        mpd_headers = {
            'accept': '*/*',
            'referer': 'https://appx-play.akamai.net.in/',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36'
        }
        
        # 1. Fetch PSSH from MPD
        print(f"[*] Fetching MPD for PSSH: {output_name}")
        res = requests.get(mpd_url, headers=mpd_headers)
        pssh_match = re.search(r'<cenc:pssh[^>]*>(.*?)</cenc:pssh>', res.text, re.DOTALL)
        if not pssh_match:
            print("[-] PSSH not found in MPD manifest.")
            return None
        pssh_b64 = pssh_match.group(1).strip()
        
        # 2. Widevine Key Fetch (Apni .wvd path ka dhyaan rakhna)
        device = Device.load(CDM_PATH)
        cdm = Cdm.from_device(device)
        session_id = cdm.open()
        
        challenge = cdm.get_license_challenge(session_id, PSSH(pssh_b64))
        
        # ================= HEADER 2 =================
        # DRM License fetch karne ke liye (Study Parcham API)
        drm_url = 'https://platform.studyparcham.in/api/scienceandfun/drm'
        drm_headers = {
            'authority': 'platform.studyparcham.in',
            'pallycon-customdata-v2': pallycon_token,
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36'
        }
        
        print("[*] Requesting license from DRM server...")
        license_res = requests.post(drm_url, headers=drm_headers, data=challenge)
        cdm.parse_license(session_id, license_res.content)
        
        keys = [f"{key.kid.hex}:{key.key.hex()}" for key in cdm.get_keys(session_id) if key.type == "CONTENT"]
        cdm.close(session_id)
        
        if not keys:
            print("[-] No content keys returned.")
            return None
            
        print(f"[+] Decryption Keys found: {keys}")
        
        # 3. yt-dlp & mp4decrypt commands
        enc_vid = "enc_vid.mp4"
        enc_aud = "enc_aud.m4a"
        dec_vid = "dec_vid.mp4"
        dec_aud = "dec_aud.m4a"
        
        # yt-dlp me bhi Header 1 (Akamai Referer) use karenge
        yt_dlp_cmd = [
            'yt-dlp', 
            '--allow-unplayable-formats',
            '--add-header', 'Referer: https://appx-play.akamai.net.in/',
            '--add-header', 'User-Agent: Mozilla/5.0 (Linux; Android 10; K)'
        ]
        
        print("[*] Downloading encrypted streams via yt-dlp...")
        subprocess.run(yt_dlp_cmd + ['-f', 'bestvideo', '-o', enc_vid, mpd_url], check=True)
        subprocess.run(yt_dlp_cmd + ['-f', 'bestaudio', '-o', enc_aud, mpd_url], check=True)
        
        key_args = []
        for k in keys:
            key_args.extend(['--key', k])
            
        print("[*] Decrypting streams...")
        subprocess.run(['mp4decrypt'] + key_args + [enc_vid, dec_vid], check=True)
        subprocess.run(['mp4decrypt'] + key_args + [enc_aud, dec_aud], check=True)
        
        print("[*] Merging decrypted streams...")
        subprocess.run(['ffmpeg', '-y', '-i', dec_vid, '-i', dec_aud, '-c', 'copy', output_name], check=True)
        
        # Cleanup temporary files
        for file in [enc_vid, enc_aud, dec_vid, dec_aud]:
            if os.path.exists(file):
                os.remove(file)
                
        return output_name
        
    except Exception as e:
        print(f"DRM Error: {e}")
        return None



def xxdurations(filename):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                             "format=duration", "-of",
                             "default=noprint_wrappers=1:nokey=1", filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT)
    return float(result.stdout)

def duration(filename):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                             "format=duration", "-of",
                             "default=noprint_wrappers=1:nokey=1", filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    return float(result.stdout)

    return 0.0
        

def exec(cmd):
    process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = process.stdout.decode()
    print(output)
    return output


def pull_run(work, cmds):
    with concurrent.futures.ThreadPoolExecutor(max_workers=work) as executor:
        print("Waiting for tasks to complete")
        fut = executor.map(exec, cmds)


async def aio(url, name):
    k = f'{name}.pdf'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(k, mode='wb')
                await f.write(await resp.read())
                await f.close()
    return k


async def download(url, name):
    ka = f'{name}.pdf'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(ka, mode='wb')
                await f.write(await resp.read())
                await f.close()
    return ka


def parse_vid_info(info):
    info = info.strip().split("\n")
    new_info = []
    temp = []
    for i in info:
        if "[" not in i and '---' not in i:
            while "  " in i:
                i = i.replace("  ", " ")
            i = i.strip().split("|")[0].split(" ", 2)
            try:
                if "RESOLUTION" not in i[2] and i[2] not in temp and "audio" not in i[2]:
                    temp.append(i[2])
                    new_info.append((i[0], i[2]))
            except:
                pass
    return new_info


def vid_info(info):
    info = info.strip().split("\n")
    new_info = dict()
    temp = []
    for i in info:
        if "[" not in i and '---' not in i:
            while "  " in i:
                i = i.replace("  ", " ")
            i = i.strip().split("|")[0].split(" ", 3)
            try:
                if "RESOLUTION" not in i[2] and i[2] not in temp and "audio" not in i[2]:
                    temp.append(i[2])
                    new_info[f'{i[2]}'] = f'{i[0]}'
            except:
                pass
    return new_info


async def run(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    stdout, stderr = await proc.communicate()

    print(f'[{cmd!r} exited with {proc.returncode}]')
    if proc.returncode == 1:
        return False
    if stdout:
        return f'[stdout]\n{stdout.decode()}'
    if stderr:
        return f'[stderr]\n{stderr.decode()}'


def old_download(url, file_name, chunk_size=1024 * 10):
    if os.path.exists(file_name):
        os.remove(file_name)
    r = requests.get(url, allow_redirects=True, stream=True)
    with open(file_name, 'wb') as fd:
        for chunk in r.iter_content(chunk_size=chunk_size):
            if chunk:
                fd.write(chunk)
    return file_name


def human_readable_size(size, decimal_places=2):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if size < 1024.0 or unit == 'PB':
            break
        size /= 1024.0
    return f"{size:.{decimal_places}f} {unit}"


def time_name():
    date = datetime.date.today()
    now = datetime.datetime.now()
    current_time = now.strftime("%H%M%S")
    return f"{date} {current_time}.mp4"


def get_playlist_videos(playlist_url):
    try:
        playlist = Playlist(playlist_url)
        playlist_title = playlist.title
        videos = {}
        for video in playlist.videos:
            try:
                video_title = video.title
                video_url = video.watch_url
                videos[video_title] = video_url
            except Exception as e:
                logging.error(f"Could not retrieve video details: {e}")
        return playlist_title, videos
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return None, None


def get_all_videos(channel_url):
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'skip_download': True
    }

    all_videos = []
    with YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(channel_url, download=False)

        if 'entries' in result:
            channel_name = result['title']
            all_videos.extend(result['entries'])

            video_links = {index + 1: (video['title'], video['url']) for index, video in enumerate(all_videos)}
            return video_links, channel_name
        else:
            return None, None


def save_to_file(video_links, channel_name):
    import re
    sanitized_channel_name = re.sub(r'[^\w\s-]', '', channel_name).strip().replace(' ', '_')
    filename = f"{sanitized_channel_name}.txt"
    with open(filename, 'w', encoding='utf-8') as file:
        for number, (title, url) in video_links.items():
            if url.startswith("https://"):
                formatted_url = url
            elif "shorts" in url:
                formatted_url = f"https://www.youtube.com{url}"
            else:
                formatted_url = f"https://www.youtube.com/watch?v={url}"
            file.write(f"{number}. {title}: {formatted_url}\n")
    return filename

# =====================================================================
#  ✅ SECURE PDF DOWNLOAD (Working version - no duplicates)
# =====================================================================
async def download_secure_pdf(url, name):
    """
    Termux bypass headers ke sath secure PDF download karne ka working function.
    """
    clean_name = f"{name}.pdf"
    print(f"[Secure PDF] Download suru ho raha hai: {clean_name}", flush=True)
    
    cmd = [
        "curl", "-L",
        "-H", "User-Agent: Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
        "-H", "Referer: https://appx-play.akamai.net.in/",
        "-o", clean_name,
        url
    ]
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd, 
            stdout=asyncio.subprocess.DEVNULL, 
            stderr=asyncio.subprocess.PIPE
        )
        
        _, stderr_data = await process.communicate()
        
        if process.returncode == 0 and os.path.exists(clean_name):
            print(f"[Secure PDF] Download safal raha: {clean_name}", flush=True)
            return clean_name
        else:
            err_msg = stderr_data.decode(errors='ignore').strip() if stderr_data else "Unknown"
            print(f"[Secure PDF] Error: Curl download process fail ho gaya. Log: {err_msg}", flush=True)
            return None
    except Exception as e:
        print(f"[Secure PDF] Exception error: {str(e)}", flush=True)
        return None

# =====================================================================
#  ✅ SECURE VIDEO DOWNLOAD (Working version - no duplicates)
# =====================================================================
async def download_secure_video(url, name):
    """
    Normal HLS (.m3u8) video streams ko bypass headers ke sath download aur copy karne ka working function.
    """
    clean_name = f"{name}.mp4" if not name.endswith(".mp4") else name
    print(f"[Secure Video] Stream compile hona suru ho gaya hai: {clean_name}", flush=True)
    
    cmd = [
        "ffmpeg", "-y",
        "-user_agent", "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
        "-headers", "Referer: https://appx-play.akamai.net.in/\r\n",
        "-i", url,
        "-c", "copy",
        clean_name
    ]
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd, 
            stdout=asyncio.subprocess.DEVNULL, 
            stderr=asyncio.subprocess.PIPE
        )
        
        while True:
            line_bytes = await process.stderr.readline()
            if not line_bytes:
                break
            line = line_bytes.decode(errors='ignore').strip()
            if "frame=" in line or "time=" in line or "speed=" in line:
                print(f"[Secure Video Process] {line}", flush=True)
            
        await process.wait()
        
        if process.returncode == 0 and os.path.exists(clean_name):
            print(f"[Secure Video] Conversion complete ho gaya: {clean_name}", flush=True)
            return clean_name
        else:
            print("[Secure Video] Error: FFmpeg run completed with failure.", flush=True)
            return None
    except Exception as e:
        print(f"[Secure Video] Exception error: {str(e)}", flush=True)
        return None



# =====================================================================
#  ✅ APPX SIGNED VIDEO DOWNLOAD (Using requests)
# =====================================================================
def download_appx_signed_sync(url, name):
    """
    Download video using requests for appx signed URLs (Synchronous version)
    Returns downloaded file path or None
    """
    try:
        headers = {
            'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 1000005; Build)",
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Referer': "https://player.akamai.net.in/"
        }
        
        if not name.endswith('.mkv'):
            name = name + '.mkv'
            
        print(f"\n📥 [Appx] Downloading video...")
        print(f"🎬 Saving as: {name}")
        
        response = requests.get(url, headers=headers, stream=True, timeout=60)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(name, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        progress = (downloaded / total_size) * 100
                        print(f"\r📊 Progress: {progress:.1f}%", end="", flush=True)
        
        print(f"\n✅ Successfully downloaded: {name}")
        return name
        
    except Exception as e:
        print(f"❌ Error downloading {url}: {str(e)}")
        return None


async def download_appx_signed(url, name):
    """
    Download video using requests for appx signed URLs (Async wrapper)
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, download_appx_signed_sync, url, name)


# =====================================================================
#  ✅ APPX VIDEO DOWNLOAD (XOR Decryption with requests + mmap)
# =====================================================================
async def download_appx_video(url, name, enc_key):
    """
    Appx encrypted video download with XOR header decryption.
    Uses requests for download, mmap for XOR decryption.
    Returns decrypted file path or None.
    """
    import mmap
    import hashlib
    
    if not name.endswith('.mkv'):
        name = name + '.mkv'
    
    temp_name = f"temp_encrypted_{os.getpid()}.mkv"
    final_name = name
    
    print(f"[Appx Video] Downloading encrypted video...", flush=True)
    
    # Download using the signed downloader
    downloaded = await download_appx_signed(url, temp_name)
    
    if not downloaded or not os.path.exists(temp_name):
        print(f"[Appx Video] Download failed", flush=True)
        return None
    
    print(f"[Appx Video] Download complete, decrypting XOR header...", flush=True)
    
    try:
        # XOR Decrypt header using mmap
        with open(temp_name, "r+b") as f:
            file_size = os.path.getsize(temp_name)
            num_bytes = min(28, file_size)
            
            with mmap.mmap(f.fileno(), length=num_bytes, access=mmap.ACCESS_WRITE) as mmapped_file:
                for i in range(num_bytes):
                    key_byte = ord(enc_key[i]) if i < len(enc_key) else i % 256
                    mmapped_file[i] = mmapped_file[i] ^ key_byte
        
        # Rename to final name
        os.rename(temp_name, final_name)
        print(f"[Appx Video] ✅ Successfully decrypted: {final_name}", flush=True)
        return final_name
        
    except Exception as e:
        print(f"[Appx Video] ❌ Decryption error: {str(e)}", flush=True)
        if os.path.exists(temp_name):
            os.remove(temp_name)
        return None


# =====================================================================
#  ✅ APPX PDF DOWNLOAD (AES-128-CBC Decryption)
# =====================================================================
async def download_appx_pdf(url, name, enc_key):
    """
    Appx encrypted PDF download with AES-128-CBC decryption.
    Returns decrypted file path or None.
    """
    import hashlib
    
    if not name.endswith('.pdf'):
        name = name + '.pdf'
    
    temp_enc_file = f"temp_encrypted_{os.getpid()}.pdf"
    final_name = name
    temp_cipher = f"temp_cipher_{os.getpid()}.bin"
    temp_plain = f"temp_plain_{os.getpid()}.pdf"
    
    print(f"[Appx PDF] Downloading encrypted PDF...", flush=True)
    
    # Download with curl (keep existing method)
    cmd_download = [
        "curl", "-L", "-s",
        "-H", "User-Agent: Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
        "-H", "Referer: https://appx-play.akamai.net.in/",
        "-o", temp_enc_file,
        url
    ]
    
    try:
        # Download
        process = await asyncio.create_subprocess_exec(
            *cmd_download,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr_data = await process.communicate()
        
        if process.returncode != 0 or not os.path.exists(temp_enc_file):
            print(f"[Appx PDF] Download failed", flush=True)
            return None
        
        # Check if already plain PDF
        with open(temp_enc_file, 'rb') as f:
            if f.read(4) == b'%PDF':
                os.rename(temp_enc_file, final_name)
                print(f"[Appx PDF] Already plain PDF: {final_name}", flush=True)
                return final_name
        
        print(f"[Appx PDF] Download complete, decrypting AES-128-CBC...", flush=True)
        
        # Read IV and ciphertext
        with open(temp_enc_file, 'rb') as f:
            file_bytes = f.read()
        
        if len(file_bytes) < 32:
            print(f"[Appx PDF] File too small", flush=True)
            os.remove(temp_enc_file)
            return None
        
        iv_bytes = file_bytes[:16]
        ciphertext_bytes = file_bytes[16:]
        
        with open(temp_cipher, 'wb') as f:
            f.write(ciphertext_bytes)
        
        hex_iv = iv_bytes.hex()
        
        # Candidate keys
        candidates = [
            enc_key.encode('utf-8')[:16].ljust(16, b'\x00'),
            hashlib.md5(enc_key.encode('utf-8')).digest(),
            hashlib.sha256(enc_key.encode('utf-8')).digest()[:16]
        ]
        
        success = False
        
        for cand_bytes in candidates:
            hex_key = cand_bytes.hex()
            
            # Method 1: Standard decryption
            cmd_decrypt = [
                "openssl", "aes-128-cbc", "-d",
                "-K", hex_key,
                "-iv", hex_iv,
                "-in", temp_cipher,
                "-out", temp_plain
            ]
            
            proc = await asyncio.create_subprocess_exec(
                *cmd_decrypt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.wait()
            
            if os.path.exists(temp_plain) and os.path.getsize(temp_plain) > 100:
                with open(temp_plain, 'rb') as f:
                    if f.read(4) == b'%PDF':
                        os.rename(temp_plain, final_name)
                        success = True
                        break
                if os.path.exists(temp_plain):
                    os.remove(temp_plain)
            
            # Method 2: Zero IV decryption
            cmd_zero = [
                "openssl", "aes-128-cbc", "-d",
                "-K", hex_key,
                "-iv", "00000000000000000000000000000000",
                "-in", temp_enc_file,
                "-out", temp_plain
            ]
            
            proc = await asyncio.create_subprocess_exec(
                *cmd_zero,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.wait()
            
            if os.path.exists(temp_plain) and os.path.getsize(temp_plain) > 100:
                with open(temp_plain, 'rb') as f:
                    if f.read(4) == b'%PDF':
                        os.rename(temp_plain, final_name)
                        success = True
                        break
                if os.path.exists(temp_plain):
                    os.remove(temp_plain)
        
        # Cleanup
        for f in [temp_enc_file, temp_cipher, temp_plain]:
            if os.path.exists(f):
                os.remove(f)
        
        if success:
            print(f"[Appx PDF] ✅ Successfully decrypted: {final_name}", flush=True)
            return final_name
        else:
            print(f"[Appx PDF] ❌ Decryption failed", flush=True)
            return None
            
    except Exception as e:
        print(f"[Appx PDF] ❌ Error: {str(e)}", flush=True)
        for f in [temp_enc_file, temp_cipher, temp_plain]:
            if os.path.exists(f):
                os.remove(f)
        return None


            
# =====================================================================
#  ✅ FALLBACK DOWNLOAD FUNCTIONS
# =====================================================================


async def download_video(url,cmd, name):
    download_cmd = f'{cmd} -R 25 --fragment-retries 25 --external-downloader aria2c --downloader-args "aria2c: -x 16 -j 32"'
    global failed_counter
    print(download_cmd)
    logging.info(download_cmd)
    k = subprocess.run(download_cmd, shell=True)
    if "visionias" in cmd and k.returncode != 0 and failed_counter <= 10:
        failed_counter += 1
        await asyncio.sleep(5)
        await download_video(url, cmd, name)
    failed_counter = 0
    try:
        if os.path.isfile(name):
            return name
        elif os.path.isfile(f"{name}.webm"):
            return f"{name}.webm"
        name = name.split(".")[0]
        if os.path.isfile(f"{name}.mkv"):
            return f"{name}.mkv"
        elif os.path.isfile(f"{name}.mp4"):
            return f"{name}.mp4"
        elif os.path.isfile(f"{name}.mp4.webm"):
            return f"{name}.mp4.webm"

        return name
    except FileNotFoundError as exc:
        return os.path.isfile.splitext[0] + "." + "mp4"
        

async def send_doc(bot: Client, m: Message, cc, ka, cc1, prog, count, name):
    reply = await m.reply_text(f"**Uploading ..🚀..** - `{name}`\n<pre><code>╰────⌈𝐀𝐧𝐤𝐢𝐭 𝐒𝐡𝐚𝐤𝐲𝐚™🇮🇳⌋────╯</code></pre>")
    time.sleep(1)
    start_time = time.time()
    await m.reply_document(ka, caption=cc1)
    count += 1
    await reply.delete(True)
    time.sleep(1)
    os.remove(ka)
    time.sleep(3)


async def send_vid(bot: Client, m: Message, cc, filename, thumb, name, prog):
    subprocess.run(f'ffmpeg -i "{filename}" -ss 00:00:12 -vframes 1 "{filename}.jpg"', shell=True)
    await prog.delete(True)
    reply = await m.reply_text(f"**Uploading ..🚀..** - `{name}`\n<pre><code>╰────⌈𝐀𝐧𝐤𝐢𝐭 𝐒𝐡𝐚𝐤𝐲𝐚™🇮🇳⌋────╯</code></pre>")
    try:
        thumbnail = f"{filename}.jpg" if thumb == "no" else thumb
    except Exception as e:
        await m.reply_text(str(e))
        return

    dur = int(duration(filename))
    start_time = time.time()

    try:
        await m.reply_video(filename, caption=cc, supports_streaming=True, height=720, width=1280,
                            thumb=thumbnail, duration=dur,
                            progress=progress_bar, progress_args=(reply, start_time))
    except Exception:
        await m.reply_document(filename, caption=cc, progress=progress_bar, progress_args=(reply, start_time))

    os.remove(filename)
    os.remove(f"{filename}.jpg")
    await reply.delete(True)
