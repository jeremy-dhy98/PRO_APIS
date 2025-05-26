from manim import *
import requests
import logging
import os
import textwrap
import subprocess
import json
from pydub import AudioSegment

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load API keys from environment variables
cat_api_key = os.environ.get("CAT_API_KEY")
voice_api_key = os.environ.get("VOICE_RSS_API_KEY")

# Global variables to store fetched data (avoiding redundant calls)
quote_data = None
voiceover_file = None

def fetch_quote():
    """Fetches a random motivational quote from ZenQuotes API."""
    global quote_data
    if quote_data is not None:
        return quote_data

    url = "https://zenquotes.io/api/random"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        logging.info(f"Fetched data: {data}")
        if isinstance(data, list) and data:
            quote_data = {"quote": data[0].get("q", "No quote found"),
                          "author": data[0].get("a", "Unknown")}
            return quote_data
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching quote: {e}")
    
    quote_data = {"quote": "No quote found", "author": "Unknown"}
    return quote_data

def fetch_voiceover(quote, api_key):
    """Fetches voiceover for the given quote using VoiceRSS API (and caches result)."""
    global voiceover_file
    if voiceover_file is not None and os.path.exists(voiceover_file):
        return voiceover_file

    url = "https://api.voicerss.org/"
    params = {
        "key": api_key,
        "hl": "en-us",
        "src": quote,
        "r": "0",
        "c": "mp3",
        "f": "44khz_16bit_stereo",
        "b64": "false",
        "v": "John"
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        file_path = "voiceover.mp3"
        with open(file_path, "wb") as f:
            f.write(response.content)
        voiceover_file = file_path
        return file_path
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching voiceover: {e}")
    return None

def create_quote_mobjects(quote_text, quote_author, frame_width, frame_height):
    """
    Creates two formatted text objects:
      - A main quote mobject with proper wrapping and scaling.
      - An author mobject.
    """
    # Wrap the quote text for proper line breaks.
    wrapped_quote = "\n".join(textwrap.wrap(quote_text, width=40))
    
    # Create the quote mobject.
    quote_mobject = Paragraph(wrapped_quote, alignment="center", line_spacing=0.6)
    quote_mobject.set_color_by_gradient(WHITE, YELLOW)
    max_width = frame_width * 0.8  # 80% of screen width
    max_height = frame_height * 0.5  # 50% of screen height
    quote_mobject.set_width(min(quote_mobject.width, max_width))
    quote_mobject.set_height(min(quote_mobject.height, max_height))
    
    # Create a separate author mobject.
    author_mobject = Text(f"- {quote_author}", font_size=24)
    author_mobject.set_color(YELLOW)
    
    return quote_mobject, author_mobject

def get_audio_duration(audio_file):
    """Returns the duration (in seconds) of the given audio file using pydub."""
    audio = AudioSegment.from_file(audio_file, format="mp3")
    duration_seconds = len(audio) / 1000.0
    return duration_seconds

def loop_sound(audio_file, target_duration):
    """
    Loops the given audio file (mp3 or ogg) until the target_duration (in seconds)
    is reached, then trims it to exactly target_duration.
    Returns the path to the resulting audio file.
    """
    audio = AudioSegment.from_file(audio_file)  # pydub infers the format
    original_duration = len(audio) / 1000.0
    loops_needed = int(target_duration / original_duration) + 1
    full_audio = audio * loops_needed  # Repeat the audio
    trimmed_audio = full_audio[:int(target_duration * 1000)]
    looped_path = "looped_" + os.path.basename(audio_file).split('.')[0] + ".mp3"
    trimmed_audio.export(looped_path, format="mp3")
    return looped_path

def trim_audio(audio_file, max_duration=30):
    """
    Trims the given audio file to a maximum duration (in seconds).
    Returns the path to the trimmed audio file.
    """
    audio = AudioSegment.from_file(audio_file)
    trimmed_audio = audio[:max_duration * 1000]  # Trim to max_duration seconds
    trimmed_path = "trimmed_" + os.path.basename(audio_file)
    trimmed_audio.export(trimmed_path, format="mp3")
    return trimmed_path

def extract_video_frames(video_file, fps=30):
    """
    Extracts frames from the given video file using FFmpeg with subprocess.
    Returns a list of frame file paths.
    """
    output_dir = "video_frames"
    os.makedirs(output_dir, exist_ok=True)
    
    frame_pattern = os.path.join(output_dir, "frame%03d.png")
    command = ["ffmpeg", "-i", video_file, "-vf", f"fps={fps}", frame_pattern]
    subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    frame_files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.endswith(".png")]
    return sorted(frame_files)

class AnimatedQuoteWithBackground(Scene):
    def construct(self):
        # Set total duration of the scene (in seconds)
        total_duration = 7

        # Add looping background sound (trimmed to total_duration)
        cool_effect_file = "subclip.ogg"
        looped_effect = loop_sound(cool_effect_file, total_duration)
        self.add_sound(looped_effect, gain=-5)

        # Extract video frames from background video
        video_background_file = "219305_tiny.mp4"
        video_frames = extract_video_frames(video_background_file, fps=30)
        
        # Instead of animating every frame, select a subset.
        # Aim for one frame transition every ~2 seconds.
        desired_transitions = int(total_duration // 2)
        frame_interval = max(1, len(video_frames) // desired_transitions)
        selected_frames = video_frames[::frame_interval]
        
        # Create initial background image from the first selected frame.
        bg_image = ImageMobject(selected_frames[0]).scale(4)
        self.add(bg_image)
        
        # Fetch quote
        quote_info = fetch_quote()
        quote_text = f"\"{quote_info['quote']}\""
        quote_author = f"{quote_info['author']}"
        
        # Create quote text objects
        quote_mobject, author_mobject = create_quote_mobjects(
            quote_text, quote_author, self.camera.frame_width, self.camera.frame_height
        )
        quote_mobject.move_to(UP * 0.5)
        author_mobject.next_to(quote_mobject, DOWN, buff=0.4)

        # Fetch and trim voiceover BEFORE animating text, so both play concurrently.
        audio_file = fetch_voiceover(quote_text, voice_api_key)
        if audio_file:
            audio_file = trim_audio(audio_file, max_duration=total_duration)
            voiceover_duration = get_audio_duration(audio_file)
            self.add_sound(audio_file, gain=+10)
        else:
            voiceover_duration = 0

        # Animate text appearance with reduced run times.
        time_fadein = 0.8
        time_write = 2
        time_color = 1
        time_scale = 0.8
        time_author = 0.8

        self.play(FadeIn(quote_mobject, shift=UP, scale=1.2), run_time=time_fadein)
        self.play(Write(quote_mobject), run_time=time_write)
        self.play(quote_mobject.animate.set_color_by_gradient(BLUE, PURPLE), run_time=time_color)
        self.play(quote_mobject.animate.scale(1.1), run_time=time_scale)
        self.play(FadeIn(author_mobject, shift=UP), run_time=time_author)

        # Animate background transitions over the selected frames.
        bg_transition_time = 0.5
        for frame in selected_frames[1:]:
            new_bg = ImageMobject(frame).scale(4)
            self.play(Transform(bg_image, new_bg), run_time=bg_transition_time)

        # Calculate total animation time spent.
        time_text = time_fadein + time_write + time_color + time_scale + time_author
        time_bg = (len(selected_frames) - 1) * bg_transition_time
        time_used = time_text + time_bg

        # Wait the remaining time so that the full scene lasts exactly total_duration.
        remaining_time = max(0, total_duration - time_used)
        self.wait(remaining_time)


