# Configure ImageMagick
from moviepy.config import change_settings
change_settings({"IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe"})

import requests
from PIL import Image
import logging
from pathlib import Path
import os
from io import BytesIO
import moviepy.editor as mpy
import argparse

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- API Fetch Functions () ---

# Function to fetch a cat image
def fetch_cat_image(api_key):
    """Fetches a random cat image from TheCatAPI."""
    url = "https://api.thecatapi.com/v1/images/search"
    headers = {"x-api-key": api_key}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, list) and data:
            image_url = data[0].get("url")
            if image_url:
                response = requests.get(image_url)
                response.raise_for_status()
                img = Image.open(BytesIO(response.content))
                img = img.convert("RGB")
                img.save("cat_image.jpg")
                return "cat_image.jpg"
            else:
                logging.error("No 'url' key found in the response data.")
        else:
            logging.error("API response is not a valid list or is empty.")

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching cat image: {e}")
    return None


# Function to fetch a motivational quote
def fetch_quote():
    """
    Fetches a random motivational quote from ZenQuotes API.
    """
    url = "https://zenquotes.io/api/random"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # Log the entire data to inspect its structure
        logging.info(f"Fetched data: {data}")

        if isinstance(data, list) and data:
            # Check if the list has expected structure
            quote = data[0].get("q", "No quote found")
            author = data[0].get("a", "Unknown author")
            return {"quote": quote, "author": author}
        else:
            logging.error("API response is not in expected format.")
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching quote: {e}")
    return None


# Function to fetch voiceover
def fetch_voiceover(text, api_key, language='en-us'):
    """Fetches voiceover audio from VoiceRSS API."""
    url = "https://api.voicerss.org/"
    params = {
        'key': api_key,
        'hl': language,
        'src': text,
         "r": "0",       # Speed of speech (0-100)
        "c": "mp3",     # Audio format
        "f": "44khz_16bit_stereo",  # Audio quality
        "b64": "false", # Return raw audio (not base64)
        "v": "John"     # Male voice
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.content
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching voiceover: {e}")
    return None

# --- Text Animation Functions ---
def typewriter_effect(text, font_path, font_size, duration, color="white", bg_color=None):
    """Create a typewriter text animation."""
    letters = [text[:i + 1] for i in range(len(text))]
    try:
        text_clips = [
            mpy.TextClip(txt, font=font_path, fontsize=font_size, color=color, bg_color=bg_color)
            for txt in letters
        ]
    except Exception as e:
        logging.error(f"Error creating text clip in typewriter_effect: {e}, "
                      f"text='{text}', font='{font_path}', size={font_size}, color='{color}', bg='{bg_color}'")
        return None
    return mpy.concatenate_videoclips(text_clips, method="compose").set_duration(duration)
    

def fade_in_text(text, font_path, font_size, duration, color="white", bg_color=None):
    """Create a fade-in text animation."""
    try:
        txt_clip = mpy.TextClip(text, font=font_path, fontsize=font_size, color=color, bg_color=bg_color)
    except Exception as e:
        logging.error(f"Error creating text clip: {e}")
        return None

    return txt_clip.set_duration(duration).crossfadein(duration / 2)

# --- Video Creation Functions ---
def animate_text_with_background(cat_image_path, quote, author, output_video, audio_path=r"quote_voice.mp3", font_path=r"BriemHand-ExtraBold.ttf", audio_volume=5.5):
    try:
        # Validate file paths
        if not cat_image_path or not os.path.exists(cat_image_path):
            raise ValueError(f"Invalid or missing cat image path: {cat_image_path}")
        
        if audio_path and not os.path.exists(audio_path):
            raise ValueError(f"Invalid or missing audio path: {audio_path}")
        
        if not font_path or not os.path.exists(font_path):
            raise ValueError(f"Invalid or missing font path: {font_path}")
        
        if not output_video:
            raise ValueError(f"Invalid output video path: {output_video}")

        # Background clip
        bg_clip = mpy.ImageClip(cat_image_path).set_duration(5).resize((1280, 720))

        # Quote animation
        quote_clip = typewriter_effect(
            quote, font_path=font_path, font_size=50, duration=4, color="white", bg_color="black")
        if quote_clip is None:
            raise Exception("Error creating quote animation.")

        # Author animation
        author_clip = fade_in_text(
            author, font_path=font_path, font_size=40, duration=2, color="yellow", bg_color="black")
        if author_clip is None:
            raise Exception("Error creating author animation.")

        # Combine clips
        final_clip = mpy.CompositeVideoClip([bg_clip, quote_clip.set_position(("center", "center")), author_clip.set_position(("center", "bottom"))])

        # Add audio if provided
        if audio_path:
            audio = mpy.AudioFileClip(audio_path)
            final_clip = final_clip.set_audio(audio).volumex(audio_volume)

        # Write the video file
        final_clip.write_videofile(output_video, codec="libx264", fps=24)
        logging.info(f"Video created successfully: {output_video}")
        return True

    except Exception as e:
        logging.error(f"Error creating video: {e}")
        return False

def clean_up_temp_files(temp_files):
    """Cleans up temporary files."""
    for file_path in temp_files:
        if os.path.exists(file_path):
            os.remove(file_path)
            logging.info(f"Temporary file deleted: {file_path}")

# --- Main Program ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create an animated video with a cat image, motivational quote, and voiceover.")
    parser.add_argument("--font-path", type=str, default="BriemHand-ExtraBold.ttf", help="Path to the font file.")
    parser.add_argument("--output-video", type=str, default="animated_typography_video.mp4", help="Path to output video.")
    parser.add_argument("--audio-path", type=str, default="voiceover.mp3", help="Path to save temp audio.")
    parser.add_argument("--audio-volume", type=float, default=5.5, help="Volume adjustment for audio")
    args = parser.parse_args()
    
    temp_files_to_delete = []
    try:
        # Fetch API keys from environment variables
        cat_api_key = os.getenv("CAT_API_KEY")
        voice_api_key = os.getenv("VOICE_RSS_API_KEY")

        if not cat_api_key or not voice_api_key:
            logging.error("Missing API keys. Please set 'CAT_API_KEY' and 'VOICE_RSS_API_KEY' as environment variables.")
            exit(1)

        # Fetch a motivational quote
        logging.info("Fetching a motivational quote...")
        quote_data = fetch_quote()
        if not quote_data:
            logging.error("Failed to fetch a quote. Exiting.")
            exit(1)

        quote = f"\"{quote_data['quote']}\"" 
        author = f"\"{quote_data['author']}\"" 
        logging.info(f"Quote fetched: '{quote}' by {author}")

        # Fetch a random cat image
        logging.info("Fetching a cat image...")
        cat_image_path = fetch_cat_image(cat_api_key)
        if not cat_image_path:
            logging.error("Failed to fetch a cat image. Exiting.")
            exit(1)
        temp_files_to_delete.append(cat_image_path)

        # Generate voiceover
        logging.info("Generating voiceover...")
        audio_content = fetch_voiceover(quote, voice_api_key)
        if not audio_content:
            logging.error("Failed to generate voiceover. Exiting.")
            exit(1)

        audio_path = r"quote_voice.mp3"
        with open(audio_path, "wb") as audio_file:
            audio_file.write(audio_content)
        temp_files_to_delete.append(audio_path)
        
        # Create the animated video
        logging.info("Creating the video...")
        video_created = animate_text_with_background(cat_image_path, quote, author, 
        r"animated_typography_video.mp4", audio_path, args.font_path, args.audio_volume)
        if not video_created:
            logging.error("Video creation failed.")

    except (ValueError, FileNotFoundError, requests.exceptions.RequestException) as e:
      logging.error(f"Error: {e}")
    except Exception as e:
      logging.error(f"An unexpected error occurred: {e}")
    finally:
      clean_up_temp_files(temp_files_to_delete)