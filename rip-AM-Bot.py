import asyncio
import os
import subprocess
import nest_asyncio
import tempfile
import shutil
from collections import deque
from pyrogram import Client, filters

nest_asyncio.apply()

# Hardcoded API credentials and bot token
API_ID = 12345678  # Replace with your API ID
API_HASH = ''  # Replace with your API Hash
BOT_TOKEN = ''  # Replace with your Bot Token
DOWNLOAD_DIR = 'apple-music-alac-atmos-downloader/AM-DL downloads/'  # Base directory for downloads

# Initialize the Pyrogram Client with API ID, API hash, and bot token
app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Queue and processing flag
request_queue = deque()
currently_processing = False  # To keep track if the bot is busy with a download

async def stop_client():
    """Stop the existing Pyrogram client if it's running."""
    try:
        if app.is_connected:
            await app.stop()
            print("Client stopped successfully.")
    except Exception as e:
        print(f"Error stopping client: {str(e)}")


@app.on_message(filters.command("start"))
async def start_command(client, message):
    chat_id = message.chat.id
    await client.send_message(chat_id=chat_id, text="Welcome! Use /alac <url> to download music.")


@app.on_message(filters.command("alac"))
async def add_to_queue(client, message):
    """Adds a new download request to the queue."""
    global currently_processing

    chat_id = message.chat.id
    url = message.text.split(" ", 1)[1] if len(message.text.split(" ")) > 1 else None

    if not url:
        await client.send_message(chat_id=chat_id, text="Please provide a valid URL.")
        return

    # Add the new request to the queue
    request_queue.append((chat_id, url))
    queue_position = len(request_queue)

    # Notify user of their queue position if already busy
    if currently_processing:
        await client.send_message(
            chat_id=chat_id,
            text=f"Bot is currently processing another request. Your request is in the queue at position {queue_position}."
        )
    else:
        # Start processing if the bot is idle
        await process_queue(client)


async def process_queue(client):
    """Processes the next request in the queue, if any."""
    global currently_processing

    if not request_queue:
        currently_processing = False
        return

    currently_processing = True
    chat_id, url = request_queue.popleft()  # Get the next request in line

    # Notify the user that their request is now being processed
    await client.send_message(chat_id=chat_id, text="Your request is now being processed. Downloading the album...")

    try:
        # Call the existing download_album function to handle this request
        await download_album(client, chat_id, url)
    except Exception as e:
        await client.send_message(chat_id=chat_id, text=f"An error occurred: {str(e)}")

    # Process the next request in the queue
    await process_queue(client)


async def download_album(client, chat_id, url):
    """The main download function."""
    await client.send_message(chat_id=chat_id, text="Downloading the album...")

    try:
        # Run the command to download the album using Go
        subprocess.run(['go', 'run', 'main.go', url], cwd='apple-music-alac-atmos-downloader', check=True)
        await client.send_message(chat_id=chat_id, text="Download completed. Uploading files...")

        # Find the downloaded album folder dynamically
        album_folder = await find_latest_album_folder(DOWNLOAD_DIR)

        # Upload files
        await upload_album_files(client, chat_id, album_folder)

        # Check size and handle zipping if necessary
        album_size = get_folder_size(album_folder)
        if album_size > 2 * 1024 * 1024 * 1024:  # If album size > 2GB
            await client.send_message(chat_id=chat_id, text="Zipping the album into parts...")
            zip_file_paths = await zip_album_files_in_parts(album_folder)
            for zip_file_path in zip_file_paths:
                await client.send_message(chat_id=chat_id, text=f"Sending ZIP part: {os.path.basename(zip_file_path)}")
                await client.send_document(chat_id=chat_id, document=zip_file_path)
        else:
            zip_file_path = await zip_album_files(album_folder)
            await client.send_message(chat_id=chat_id, text="Zipping completed. Sending ZIP file...")
            await client.send_document(chat_id=chat_id, document=zip_file_path)

        # Clean up after sending
        shutil.rmtree(DOWNLOAD_DIR)
        await client.send_message(chat_id=chat_id, text="All files uploaded and cleaned up.")

    except Exception as e:
        await client.send_message(chat_id=chat_id, text=f"An error occurred: {str(e)}")


# Keeping existing functions as they are

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


async def upload_album_files(client, chat_id, album_folder):
    """Upload individual files (cover image and .m4a files) from the downloaded album folder."""
    await client.send_message(chat_id=chat_id, text="Uploading individual files...")

    # Check for cover.jpg and upload it first if it exists
    cover_image_path = os.path.join(album_folder, 'cover.jpg')
    if os.path.isfile(cover_image_path):
        await send_file_to_telegram(client, cover_image_path, chat_id)

    # Upload remaining audio files in numeric order (.m4a) with their default names
    audio_files = sorted([f for f in os.listdir(album_folder) if f.endswith('.m4a')])
    for file in audio_files:
        file_path = os.path.join(album_folder, file)
        await send_file_to_telegram(client, file_path, chat_id)


async def send_file_to_telegram(client, file_path, chat_id):
    """Send a file to Telegram exactly as it is, without renaming."""
    await client.send_document(chat_id=chat_id, document=file_path)
    print(f"File sent successfully: {file_path}")


def get_folder_size(folder_path):
    """Get the total size of a folder in bytes."""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(folder_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size


async def zip_album_files(album_folder):
    """Zip the album folder using shutil and store it in a temporary directory."""
    album_name = os.path.basename(album_folder)
    
    # Use a temporary directory for the zip to avoid filling up space in the main folder
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_file_path = os.path.join(temp_dir, f"{album_name}.zip")
        
        # Use shutil to create a zip archive
        shutil.make_archive(base_name=zip_file_path.replace('.zip', ''), format='zip', root_dir=album_folder)
        
        # Move the final zip file to the album folder
        final_zip_path = os.path.join(album_folder, f"{album_name}.zip")
        shutil.move(zip_file_path, final_zip_path)
        
        return final_zip_path


async def zip_album_files_in_parts(album_folder, part_size_mb=500):
    """Split the album folder into multiple parts if larger than 2GB."""
    album_name = os.path.basename(album_folder)
    zip_file_paths = []

    # First, compress the entire album folder
    zip_file_path = await zip_album_files(album_folder)

    # Calculate part size in bytes
    part_size_bytes = part_size_mb * 1024 * 1024

    # Use a temporary directory to write parts without overwriting
    with open(zip_file_path, 'rb') as f, tempfile.TemporaryDirectory() as temp_dir:
        part_number = 1
        while True:
            part_file_path = os.path.join(temp_dir, f"{album_name}_part{part_number:03}.zip")
            
            # Write the part file up to the size limit
            with open(part_file_path, 'wb') as part_file:
                part_file.write(f.read(part_size_bytes))
                if os.path.getsize(part_file_path) < part_size_bytes:
                    break

            # Move part to album folder after it’s written to avoid recursive filling
            final_part_path = os.path.join(album_folder, f"{album_name}_part{part_number:03}.zip")
            shutil.move(part_file_path, final_part_path)
            zip_file_paths.append(final_part_path)

            part_number += 1

    return zip_file_paths


# Run the bot
app.run()
