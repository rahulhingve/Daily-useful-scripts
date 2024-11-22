import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from collections import deque
import asyncio
import re
import subprocess
from datetime import datetime
import shutil

# Configuration
API_ID = Paste here you telegram API_ID
API_HASH = 'Paste here you telegram API_HASH'
BOT_TOKEN = 'Paste here you telegram BOT_Token'

# Queue management
download_queue = deque()
is_processing = False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command"""
    await update.message.reply_text(
        "Hi! I'm a Tidal Download Bot. Use /dl <Tidal URL> to download songs and /status to check queue status."
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /status command"""
    global is_processing, download_queue
    
    status_message = "🤖 Bot Status: Online\n"
    if is_processing:
        status_message += "📥 Currently processing a download\n"
    
    if download_queue:
        status_message += f"📋 Queue length: {len(download_queue)}\n"
        user_position = None
        for i, item in enumerate(download_queue):
            if item['user_id'] == update.effective_user.id:
                user_position = i + 1
                break
        
        if user_position:
            status_message += f"🔜 Your position in queue: {user_position}"
    else:
        status_message += "✅ No pending downloads"
    
    await update.message.reply_text(status_message)

def is_valid_tidal_url(url: str) -> bool:
    """Check if the URL is a valid Tidal URL"""
    return url.startswith('https://tidal.com/browse/track/')

async def process_queue():
    """Process the download queue"""
    global is_processing, download_queue
    
    while True:
        if download_queue and not is_processing:
            is_processing = True
            current_task = download_queue.popleft()
            
            try:
                # Notify user that download is starting
                await current_task['context'].bot.send_message(
                    current_task['user_id'],
                    f"🎵 Starting download of your track..."
                )
                
                # Execute tidal-dl-ng command
                process = subprocess.Popen(
                    ['tidal-dl-ng', 'dl', current_task['url']],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                stdout, stderr = process.communicate()
                
                # Check if download directory exists and has files
                download_dir = os.path.expanduser('~/download/Tracks')
                if os.path.exists(download_dir):
                    files = os.listdir(download_dir)
                    if files:
                        # Send the first file found
                        file_path = os.path.join(download_dir, files[0])
                        await current_task['context'].bot.send_document(
                            current_task['user_id'],
                            document=open(file_path, 'rb'),
                            caption="✅ Here's your downloaded track!"
                        )
                        
                        # Clean up
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        if os.path.exists(os.path.dirname(file_path)):
                            shutil.rmtree(os.path.dirname(file_path))
                    else:
                        await current_task['context'].bot.send_message(
                            current_task['user_id'],
                            "❌ Download failed: No files found in download directory"
                        )
                else:
                    await current_task['context'].bot.send_message(
                        current_task['user_id'],
                        "❌ Download failed: Download directory not found"
                    )
                
            except Exception as e:
                await current_task['context'].bot.send_message(
                    current_task['user_id'],
                    f"❌ An error occurred: {str(e)}"
                )
            
            finally:
                is_processing = False
        
        await asyncio.sleep(1)

async def dl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /dl command"""
    if not context.args:
        await update.message.reply_text(
            "❌ Please provide a Tidal URL.\nExample: /dl https://tidal.com/browse/track/12345"
        )
        return
    
    url = context.args[0]
    
    if not is_valid_tidal_url(url):
        await update.message.reply_text(
            "❌ Invalid Tidal URL. Please provide a valid Tidal track URL."
        )
        return
    
    # Add to queue
    download_queue.append({
        'url': url,
        'user_id': update.effective_user.id,
        'context': context,
        'timestamp': datetime.now()
    })
    
    position = len(download_queue)
    if position == 1 and not is_processing:
        await update.message.reply_text("✅ Download starting immediately!")
    else:
        await update.message.reply_text(
            f"📝 Added to queue. Position: {position}\nUse /status to check queue status."
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    print(f"Error occurred: {context.error}")
    await update.message.reply_text(
        "❌ An error occurred. Please try again later."
    )

def main():
    """Start the bot"""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("dl", dl))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start queue processing
    application.job_queue.run_repeating(
        lambda ctx: asyncio.create_task(process_queue()),
        interval=1,
        first=0
    )
    
    # Start the bot
    print("Bot started...")
    application.run_polling()

if __name__ == '__main__':
    main()
