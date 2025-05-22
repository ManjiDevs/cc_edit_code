import json
import os
import asyncio
import time
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
DEFAULT_CHANNEL = "-1002418844773"

FOOTER_HTML = """
</b>━━━━━━━━━━━━━━━━━━━━━━
➥ ʙʏ : [@Anime_Community_India] </b>
"""

settings = {
    "channel_id": DEFAULT_CHANNEL,
    "insert_line": 2
}

# Rate limiting queue
edit_queue = asyncio.Queue()


def save_settings():
    with open("settings.json", "w") as f:
        json.dump(settings, f)


async def set_line(update: Update, context: CallbackContext):
    try:
        if not context.args or not context.args[0].isdigit():
            await update.message.reply_text(
                "Usage: /line <number>\nExample: /line 2",
                parse_mode="HTML"
            )
            return

        line_num = int(context.args[0])
        if line_num < 1:
            await update.message.reply_text(
                "Line number must be 1 or greater",
                parse_mode="HTML"
            )
            return

        settings["insert_line"] = line_num
        save_settings()
        await update.message.reply_text(
            f"✅ Footer will now be inserted after line {line_num}",
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(
            f"Error: {str(e)}",
            parse_mode="HTML"
        )


async def set_channel(update: Update, context: CallbackContext):
    message = update.message
    if message.forward_origin and hasattr(message.forward_origin, 'chat'):
        channel_id = message.forward_origin.chat.id
        settings["channel_id"] = str(channel_id)
        save_settings()

        confirmation = (
            f"✅ <b>New Channel Set Successfully!</b>\n"
            f"📢 <code>Channel ID: {channel_id}</code>\n\n"
            f"The bot will now edit messages in this channel."
        )

        await update.message.reply_text(confirmation, parse_mode="HTML")
        try:
            await context.bot.send_message(
                chat_id=channel_id,
                text=confirmation,
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Couldn't send confirmation to channel: {e}")
    else:
        await update.message.reply_text(
            "⚠️ Please forward a message from your channel to set it up.",
            parse_mode="HTML"
        )


def process_content(content):
    if not content:
        return ""

    lines = [
        line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        for line in content.split('\n')
        if "http://" not in line and "https://" not in line
    ]

    insert_at = min(settings["insert_line"], len(lines))
    kept_lines = lines[:insert_at]

    return '\n'.join(kept_lines) + FOOTER_HTML


async def auto_edit(update: Update, context: CallbackContext):
    if not update.channel_post:
        return
    await edit_queue.put((update.channel_post, context.bot))

async def edit_worker(app: Application):
    while True:
        message, bot = await edit_queue.get()

        try:
            original_content = message.text or message.caption or ""
            new_content = process_content(original_content)

            if message.text:
                await bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    text=new_content,
                    parse_mode="HTML"
                )
            elif message.caption:
                await bot.edit_message_caption(
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    caption=new_content,
                    parse_mode="HTML"
                )

            await asyncio.sleep(1)  # Minimum delay between edits

        except Exception as e:
            if "Flood control exceeded" in str(e):
                # Extract retry seconds from error message
                import re
                match = re.search(r"Retry in (\d+) seconds", str(e))
                if match:
                    wait_time = int(match.group(1)) + 1
                    print(f"⏳ Flood control hit. Sleeping for {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                    # Requeue the failed message
                    await edit_queue.put((message, bot))
                else:
                    print(f"❗ Flood error but retry time unknown: {e}")
                    await asyncio.sleep(10)
            elif "Timed out" in str(e):
                print(f"❗ Timeout. Requeuing message {message.message_id}")
                await asyncio.sleep(5)
                await edit_queue.put((message, bot))
            else:
                print(f"❌ Error editing message {message.message_id}: {e}")
                await asyncio.sleep(2)


def main():
    try:
        with open("settings.json", "r") as f:
            settings.update(json.load(f))
    except FileNotFoundError:
        pass

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("line", set_line))
    app.add_handler(MessageHandler(filters.FORWARDED, set_channel))
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POSTS, auto_edit))

    # Schedule edit_worker to run in the background after startup
    app.job_queue.run_once(lambda ctx: asyncio.create_task(edit_worker(app)), 1)

    print("✅ Bot is running with rate limiting and HTML formatting...")
    app.run_polling()


if __name__ == "__main__":
    main()
