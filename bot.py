import os
import asyncio
import subprocess
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import yt_dlp

API_TOKEN = '8095268426:AAEPH2gdZ37dQnaRKy_YYmWf2NHDNiji60w'

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    await message.reply(
        "👋 Hello! Send me a YouTube or m3u8 link, and I'll help you download the video!\n"
        "After sending the link, I'll show you a quality selection popup.\n"
        "Supported:\n- YouTube videos\n- m3u8 live/recorded streams\n"
        "You'll get the video right here (playable), or as a document if not supported!"
    )

@dp.message_handler(lambda message: message.text and ('youtube.com' in message.text or 'youtu.be' in message.text or message.text.endswith('.m3u8')))
async def process_video_link(message: types.Message):
    url = message.text.strip()
    if url.endswith('.m3u8'):
        # m3u8 conversion flow
        await message.reply("Detected m3u8 link. Converting to mp4...")
        user_id = message.from_user.id
        output_file = f"m3u8_{user_id}.mp4"
        msg = await bot.send_message(user_id, "🔄 Downloading and converting...")

        # ffmpeg command for m3u8 to mp4
        cmd = [
            "ffmpeg", "-i", url, "-c", "copy", "-bsf:a", "aac_adtstoasc", output_file, "-y"
        ]
        process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, stderr = await process.communicate()
        if process.returncode == 0 and os.path.exists(output_file):
            await msg.edit_text("✅ Conversion done. Uploading...")
            try:
                await bot.send_video(user_id, open(output_file, "rb"), supports_streaming=True)
            except Exception as e:
                await msg.edit_text(f"❌ Failed to send video: {e}")
                await bot.send_document(user_id, open(output_file, "rb"))
            os.remove(output_file)
            await msg.edit_text("🎬 Done!")
        else:
            await msg.edit_text(f"❌ Conversion failed: {stderr.decode()}")
    else:
        # YouTube or other handled by yt-dlp
        ydl_opts = {"quiet": True, "listformats": True, "skip_download": True}
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = info.get("formats", [])
                video_formats = [f for f in formats if f.get("vcodec") != "none" and f.get("acodec") != "none"]
        except Exception as e:
            await message.reply(f"❌ Failed to fetch video info: {e}")
            return
        if not video_formats:
            await message.reply("❌ No video formats found for this link.")
            return
        kb = InlineKeyboardMarkup(row_width=2)
        for f in video_formats:
            label = f"{f.get('format_note', '')} {f.get('height', '')}p ({f.get('ext','')})"
            kb.insert(InlineKeyboardButton(label.strip(), callback_data=f"dl|{url}|{f['format_id']}"))
        await message.reply("Select the video quality:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("dl|"))
async def handle_quality_selection(callback_query: types.CallbackQuery):
    _, url, format_id = callback_query.data.split("|")
    user_id = callback_query.from_user.id
    msg = await bot.send_message(user_id, "⬇️ Downloading...")

    output_filename = f"video_{user_id}.%(ext)s"

    def progress_hook(d):
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', '0%')
            eta = d.get('eta', '...')
            txt = f"⬇️ Downloading: {percent} ETA: {eta}s"
            asyncio.create_task(msg.edit_text(txt))
        elif d['status'] == 'finished':
            asyncio.create_task(msg.edit_text("✅ Download finished. Uploading to Telegram..."))

    ydl_opts = {
        'format': format_id,
        'outtmpl': output_filename,
        'progress_hooks': [progress_hook],
        'quiet': True,
        'merge_output_format': 'mp4'
    }

    filepath = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)
    except Exception as e:
        await msg.edit_text(f"❌ Download error: {e}")
        return

    if filepath and filepath.endswith('.mp4'):
        try:
            await bot.send_video(user_id, open(filepath, 'rb'), supports_streaming=True)
        except Exception as e:
            await msg.edit_text(f"❌ Failed to send video: {e}")
            await bot.send_document(user_id, open(filepath, 'rb'))
    else:
        await bot.send_document(user_id, open(filepath, 'rb'))

    await msg.edit_text("🎬 Done!")
    try:
        os.remove(filepath)
    except Exception:
        pass

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
