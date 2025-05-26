# configure image-magick
from moviepy.config import change_settings
change_settings({"IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe"})

import tempfile
import requests
import moviepy.editor as mpy
import os

# Fetch a voice cover for a text
def fetch_voiceover(text, api_key, language='en-us', gender="male"):
    """
    Fetches the voiceover audio from VoiceRSS API and returns it as binary content.
    """
    url = "https://api.voicerss.org/"
    params = {
        'key': api_key,
        'hl': language,  # Language and voice code
        'src': text,     # Text to be converted to speech
        'c': 'mp3'       # Audio format (mp3 or wav)
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.content  # Return the binary content of the audio
    except requests.exceptions.RequestException as e:
        print(f"Error fetching voiceover: {e}")
        return None


# Create a video with the voicecove and an image
def create_video_with_audio(image_path, audio_content, output_video='output_video.mp4'):
    """
    Creates a video from an image and audio content.
    """
    # Save audio content to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_audio_file:
        temp_audio_file.write(audio_content)
        temp_audio_path = temp_audio_file.name

    # Load the image and audio
    image_clip = mpy.ImageClip(image_path, duration=5)  # Duration of the image display
    audio_clip = mpy.AudioFileClip(temp_audio_path)

    # Set the audio to the video clip
    video_clip = image_clip.set_audio(audio_clip)

    # Write the video file
    video_clip.write_videofile(output_video, codec='libx264', fps=24)
    print(f"Video created: {output_video}")

    # Clean up the temporary audio file
    os.unlink(temp_audio_path)


# Example usage
api_key = os.environ.get("VOICE_RSS_API_KEY")  
text = "Your motivational quote here!"
image_path = 'cat_image.jpg'

# Fetch the voiceover content
audio_content = fetch_voiceover(text, api_key)

# Create the video if audio was fetched successfully
if audio_content:
    create_video_with_audio(image_path, audio_content, 'final_video.mp4')