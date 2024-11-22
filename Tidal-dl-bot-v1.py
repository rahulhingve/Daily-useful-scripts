from typing import Optional
import os
from pathlib import Path
import asyncio
import logging
from datetime import datetime
import shutil
import subprocess
from collections import deque

# Modern Python Telegram Bot imports
from telegram import Update
from telegram.ext import (
    Application, 
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from telegram.constants import ParseMode

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
API_ID = Paste here you telegram API_ID
API_HASH = 'Paste here you telegram API_HASH'
BOT_TOKEN = 'Paste here you telegram Bot token'

# Modern Path handling
DOWNLOAD_DIR = Path.home() / 'download' / 'Tracks'
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Queue management with modern typing
class DownloadQueue:
    def __init__(self):
        self.queue: deque = deque()
        self.is_processing: bool = False
        self.current_task: Optional[dict] = None

    def add_task(self, task: dict) -> int:
        self.queue.append(task)
        return len(self.queue)

    def get_next_task(self) -> Optional[dict]:
        return self.queue.popleft() if self.queue else None

    def get_position(self, user_id: int) -> Optional[int]:
        for i, task in enumerate(self.queue):
            if task['user_id'] == user_id:
                return i + 1
        return None

    @property
    def length(self) -> int:
        return len(self.queue)

# Create queue instance
download_queue = DownloadQueue()

class TidalDownloadBot:
    def __init__(self):
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()

    def setup_handlers(self):
        """Setup command handlers with error handling"""
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("status", self.status))
        self.application.add_handler(CommandHandler("dl", self.dl))
        self.application.add_error_handler(self.error_handler)
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Modern start command handler"""
        await update.message.reply_text(
            "*Welcome to Tidal Download Bot*\n\n"
            "Available commands:\n"
            "🎵 `/dl <Tidal URL>` - Download a track\n"
            "📊 `/status` - Check queue status\n\n"
            "_Send me a Tidal track URL to get started!_",
            parse_mode=ParseMode.MARKDOWN
        )

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Modern status command handler"""
        status_message = [
            "*🤖 Bot Status Report*",
            f"🌟 Status: {'Busy' if download_queue.is_processing else 'Idle'}",
        ]

        if download_queue.current_task:
            status_message.append(
                f"📥 Currently downloading for: "
                f"@{download_queue.current_task.get('username', 'Unknown')}"
            )

        if download_queue.length > 0:
            status_message.extend([
                f"📋 Queue length: {download_queue.length}",
                f"🔜 Your position: {download_queue.get_position(update.effective_user.id) or 'Not in queue'}"
            ])
        else:
            status_message.append("✅ No pending downloads")

        await update.message.reply_text(
            "\n".join(status_message),
            parse_mode=ParseMode.MARKDOWN
        )

    @staticmethod
    def is_valid_tidal_url(url: str) -> bool:
        """Validate Tidal URL with modern string handling"""
        return url.startswith('https://tidal.com/browse/track/')

    async def process_download(self, task: dict) -> tuple[bool, str]:
        """Process download with modern async subprocess"""
        try:
            process = await asyncio.create_subprocess_exec(
                'tidal-dl-ng', 'dl', task['url'],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                return False, f"Download failed with error: {stderr.decode()}"

            # Check for downloaded file
            files = list(DOWNLOAD_DIR.glob('*'))
            if not files:
                return False, "No files found after download"

            return True, str(files[0])
        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            return False, f"Download error: {str(e)}"

    async def dl(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Modern download command handler"""
        if not context.args:
            await update.message.reply_text(
                "❌ Please provide a Tidal URL.\n"
                "Example: `/dl https://tidal.com/browse/track/12345`",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        url = context.args[0]
        if not self.is_valid_tidal_url(url):
            await update.message.reply_text(
                "❌ Invalid Tidal URL. Please provide a valid Tidal track URL."
            )
            return

        task = {
            'url': url,
            'user_id': update.effective_user.id,
            'username': update.effective_user.username,
            'context': context,
            'timestamp': datetime.now(),
            'message': update.message
        }

        position = download_queue.add_task(task)
        
        if position == 1 and not download_queue.is_processing:
            await update.message.reply_text("✅ Download starting immediately!")
            asyncio.create_task(self.process_queue())
        else:
            await update.message.reply_text(
                f"📝 Added to queue. Position: {position}\n"
                f"Use /status to check queue status."
            )

    async def process_queue(self):
        """Modern queue processor with async file handling"""
        while True:
            if not download_queue.is_processing and download_queue.length > 0:
                download_queue.is_processing = True
                task = download_queue.get_next_task()
                download_queue.current_task = task

                try:
                    status_message = await task['message'].reply_text(
                        "🎵 Starting download...",
                        parse_mode=ParseMode.MARKDOWN
                    )

                    success, result = await self.process_download(task)

                    if success:
                        file_path = Path(result)
                        await task['context'].bot.send_document(
                            task['user_id'],
                            document=file_path.open('rb'),
                            caption="✅ Here's your track!",
                            filename=file_path.name
                        )
                        
                        # Cleanup
                        file_path.unlink(missing_ok=True)
                        await status_message.edit_text("✅ Download completed!")
                    else:
                        await status_message.edit_text(f"❌ {result}")

                except Exception as e:
                    logger.error(f"Queue processing error: {str(e)}")
                    await task['message'].reply_text(f"❌ An error occurred: {str(e)}")

                finally:
                    download_queue.current_task = None
                    download_queue.is_processing = False
                    # Clean download directory
                    if DOWNLOAD_DIR.exists():
                        shutil.rmtree(DOWNLOAD_DIR)
                        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

            await asyncio.sleep(1)

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Modern error handler with detailed logging"""
        logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)
        error_message = "❌ An error occurred. Please try again later."
        if update and update.effective_message:
            await update.effective_message.reply_text(error_message)

    def run(self):
        """Run the bot with modern async handling"""
        logger.info("Starting bot...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    try:
        # Check for ffmpeg
        subprocess.run(['ffmpeg', '-version'], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        logger.error("FFmpeg is not installed. Please install it first.")
        exit(1)
    except FileNotFoundError:
        logger.error("FFmpeg not found. Please install it first.")
        exit(1)

    # Start bot
    bot = TidalDownloadBot()
    bot.run()
