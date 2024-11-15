# before usiing this 
# apt update && apt upgrade && apt install wget python3 python3-pip python3-venv git golang gpac ffmpeg neofetch htop -y  
# git clone https://github.com/zhaarey/apple-music-alac-atmos-downloader.git  
# wget "https://github.com/itouakirai/wrapper/releases/download/linux/wrapper.linux.x86_64.tar.gz"  
  
 
# mkdir wrapper  
# tar -xzf wrapper.linux.x86_64.tar.gz -C wrapper

# cd wrapper 
#  ./wrapper -D 10020 -M 20020 -L email@gmail.com:password

# python3 -m venv .venv
# source .venv/bin/activate
# pip3 install pyrogram tgcrypto nest_asyncio gofilepy















import asyncio
import os
import subprocess
import nest_asyncio
import tempfile
import shutil
from pyrogram import Client, filters
from collections import deque
from datetime import datetime
import traceback


nest_asyncio.apply()

# Hardcoded API credentials and bot token
API_ID = telegram api id paste here 
API_HASH = 'paste telegram hash'
BOT_TOKEN = 'telegram bot token here'
DOWNLOAD_DIR = 'apple-music-alac-atmos-downloader/AM-DL downloads/'

# Task queue and status tracking
task_queue = deque()
current_task = None
processing_lock = asyncio.Lock()

class DownloadTask:
    def __init__(self, chat_id, url, message_id):
        self.chat_id = chat_id
        self.url = url
        self.message_id = message_id
        self.timestamp = datetime.now()
        self.status = "queued"
        self.progress = 0

app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def stop_client():
    try:
        if app.is_connected:
            await app.stop()
            print("Client stopped successfully.")
    except Exception as e:
        print(f"Error stopping client: {str(e)}")

@app.on_message(filters.command("start"))
async def start_command(client, message):
    chat_id = message.chat.id
    await client.send_message(
        chat_id=chat_id,
        text="Welcome! Available commands:\n"
             "/alac <url> - Download music\n"
             "/status - Check your download status\n"
             "/queue - View current queue"
    )

@app.on_message(filters.command("status"))
async def status_command(client, message):
    chat_id = message.chat.id
    
    # Check if user has any tasks in queue
    user_tasks = [task for task in task_queue if task.chat_id == chat_id]
    if current_task and current_task.chat_id == chat_id:
        await client.send_message(
            chat_id=chat_id,
            text=f"Your download is currently processing!\nStatus: {current_task.status}\nProgress: {current_task.progress}%"
        )
    elif user_tasks:
        position = next(i for i, task in enumerate(task_queue) if task.chat_id == chat_id)
        await client.send_message(
            chat_id=chat_id,
            text=f"Your download is queued at position {position + 1}"
        )
    else:
        await client.send_message(
            chat_id=chat_id,
            text="You don't have any active downloads."
        )

@app.on_message(filters.command("queue"))
async def queue_command(client, message):
    chat_id = message.chat.id
    
    queue_status = "Current queue status:\n\n"
    if current_task:
        queue_status += f"Currently processing: Task for user {current_task.chat_id}\n"
    
    if task_queue:
        queue_status += "\nQueued tasks:\n"
        for i, task in enumerate(task_queue, 1):
            queue_status += f"{i}. User {task.chat_id}\n"
    else:
        queue_status += "\nNo tasks in queue."
    
    await client.send_message(chat_id=chat_id, text=queue_status)

@app.on_message(filters.command("alac"))
async def download_album(client, message):
    chat_id = message.chat.id
    url = message.text.split(" ", 1)[1] if len(message.text.split(" ")) > 1 else None

    if not url:
        await client.send_message(chat_id=chat_id, text="Please provide a valid URL.")
        return

    # Create new task
    task = DownloadTask(chat_id, url, message.id)
    
    # Add task to queue
    task_queue.append(task)
    position = len(task_queue)
    
    if position > 1:
        await client.send_message(
            chat_id=chat_id,
            text=f"Your download has been queued. Position in queue: {position}\n"
                 f"Use /status to check your download status."
        )
    
    # Start processing if not already running
    if not processing_lock.locked():
        asyncio.create_task(process_queue(client))

async def process_queue(client):
    global current_task
    
    async with processing_lock:
        while task_queue:
            current_task = task_queue.popleft()
            try:
                await process_download(client, current_task)
            except Exception as e:
                error_msg = f"Error processing download: {str(e)}\n{traceback.format_exc()}"
                print(error_msg)
                await client.send_message(
                    chat_id=current_task.chat_id,
                    text=f"An error occurred while processing your download: {str(e)}"
                )
            finally:
                current_task = None

async def process_download(client, task):
    task.status = "downloading"
    await client.send_message(
        chat_id=task.chat_id,
        text="Starting your download..."
    )

    try:
        # Run the download command
        subprocess.run(['go', 'run', 'main.go', task.url], cwd='apple-music-alac-atmos-downloader', check=True)
        task.status = "processing"
        await client.send_message(task.chat_id, text="Download completed. Processing files...")

        # Find and process the album
        album_folder = await find_latest_album_folder(DOWNLOAD_DIR)
        
        # Create zip file
        task.status = "zipping"
        await client.send_message(task.chat_id, text="Creating zip file...")
        zip_file_path = await zip_album_files(album_folder)
        
        # Upload to Gofile
        task.status = "uploading"
        await client.send_message(task.chat_id, text="Uploading to Gofile...")
        gofile_response = await upload_to_gofile(zip_file_path)
        
        # Send download link
        if gofile_response:
            download_link = gofile_response.get('downloadPage', 'Link not available')
            await client.send_message(
                task.chat_id,
                text=f"Upload completed!\nDownload your files from: {download_link}"
            )
        
        # Cleanup
        os.remove(zip_file_path)  # Remove the zip file
        shutil.rmtree(DOWNLOAD_DIR)  # Remove the original files
        task.status = "completed"
        await client.send_message(task.chat_id, text="All files have been processed and cleaned up.")
        
    except Exception as e:
        task.status = "failed"
        raise e

async def find_latest_album_folder(download_dir):
    """Find the most recent album folder in the DOWNLOAD_DIR."""
    artist_folders = [os.path.join(download_dir, artist) for artist in os.listdir(download_dir)]
    artist_folders = [folder for folder in artist_folders if os.path.isdir(folder)]
    
    # Get the most recent album folder
    album_folder = max(
        (os.path.join(artist, album) for artist in artist_folders for album in os.listdir(artist)),
        key=os.path.getctime
    )
    return album_folder

async def zip_album_files(album_folder):
    """Create a zip file of the album folder."""
    album_name = os.path.basename(album_folder)
    zip_file_path = os.path.join(os.path.dirname(album_folder), f"{album_name}.zip")
    
    # Create zip archive
    shutil.make_archive(
        base_name=zip_file_path.replace('.zip', ''),
        format='zip',
        root_dir=os.path.dirname(album_folder),
        base_dir=os.path.basename(album_folder)
    )
    
    return zip_file_path

async def upload_to_gofile(file_path):
    """Upload file to Gofile using gofilepy CLI and return the download link."""
    try:
        # Run the gofilepy CLI command
        process = await asyncio.create_subprocess_exec(
            'gofilepy', file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise Exception(f"gofilepy upload failed with error: {stderr.decode().strip()}")

        # Extract the download link from the output
        output = stdout.decode().strip()
        for line in output.splitlines():
            if "Download page:" in line:
                download_link = line.split(": ")[1]
                return {'downloadPage': download_link}

        raise Exception("Download link not found in gofilepy output.")
        
    except Exception as e:
        print(f"Error uploading to Gofile: {str(e)}")
        return None


def get_folder_size(folder_path):
    """Get the total size of a folder in bytes."""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(folder_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size

async def main():
    try:
        await stop_client()
        await app.start()
        print("Bot started successfully.")
        await asyncio.Event().wait()
    except Exception as e:
        print(f"An error occurred while starting the bot: {str(e)}")
    finally:
        await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
