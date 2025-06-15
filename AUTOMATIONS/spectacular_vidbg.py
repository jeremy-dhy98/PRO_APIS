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

# Introduce a new global to track the last quote used for voiceover caching
_voiceover_cached_quote = None

# === BEGIN: Performance enhancements ===
# 1) Resolve paths relative to script location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Default filenames (unchanged functionality)
VIDEO_FILENAME = "219305_tiny.mp4"
SOUND_FILENAME = "subclip.ogg"

VIDEO_PATH = os.path.join(BASE_DIR, VIDEO_FILENAME)
SOUND_PATH = os.path.join(BASE_DIR, SOUND_FILENAME)

# Frames directory and metadata file
FRAMES_DIR = os.path.join(BASE_DIR, "video_frames")
METADATA_PATH = os.path.join(FRAMES_DIR, "frames_meta.json")

def load_frames_metadata():
    """Load metadata dict from METADATA_PATH if exists; else return None."""
    if os.path.exists(METADATA_PATH):
        try:
            with open(METADATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"Could not read frames metadata: {e}")
    return None

def save_frames_metadata(video_path, mtime):
    """Save metadata about extracted frames."""
    data = {"video_path": video_path, "mtime": mtime}
    try:
        with open(METADATA_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        logging.warning(f"Could not write frames metadata: {e}")

def extract_video_frames(video_file, fps=30):
    """
    Extracts frames from the given video file using FFmpeg with subprocess.
    Caches extracted frames based on the video's modification time.
    Returns a list of frame file paths (absolute).
    """
    output_dir = FRAMES_DIR
    os.makedirs(output_dir, exist_ok=True)

    # Determine video modification time
    try:
        video_mtime = os.path.getmtime(video_file)
    except Exception:
        video_mtime = None

    # --- CACHING DISABLED: always re-extract frames ---
    # Remove any cached metadata file
    # (If you wish, you can still write metadata, but it won't be used in checks below.)
    try:
        if os.path.exists(METADATA_PATH):
            os.remove(METADATA_PATH)
    except Exception:
        pass

    # First, clear existing frames
    for fname in os.listdir(output_dir):
        if fname.endswith(".png"):
            try:
                os.remove(os.path.join(output_dir, fname))
            except Exception:
                pass
    # Run ffmpeg to extract frames
    frame_pattern = os.path.join(output_dir, "frame%03d.png")
    command = ["ffmpeg", "-y", "-i", video_file, "-vf", f"fps={fps}", frame_pattern]
    logging.info(f"Extracting frames from video via ffmpeg: fps={fps}")
    try:
        subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    except Exception as e:
        logging.warning(f"ffmpeg extraction failed: {e}")

    # Collect extracted frames
    frame_files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.endswith(".png")]
    frame_files = sorted(frame_files)
    if frame_files:
        # Save metadata (though not used for skipping)
        if video_mtime is not None:
            save_frames_metadata(os.path.abspath(video_file), video_mtime)
        logging.info(f"Extracted and cached {len(frame_files)} frames.")
    else:
        logging.warning("No frames extracted; check video file.")
    return frame_files

def get_audio_duration(audio_file):
    """Returns the duration (in seconds) of the given audio file using pydub."""
    try:
        audio = AudioSegment.from_file(audio_file, format="mp3")
        duration_seconds = len(audio) / 1000.0
        return duration_seconds
    except Exception as e:
        logging.warning(f"Could not get audio duration for {audio_file}: {e}")
        return None

def loop_sound(audio_file, target_duration):
    """
    Loops the given audio file (mp3 or ogg) until the target_duration (in seconds)
    is reached, then trims it to exactly target_duration.
    Caches the result if identical looped file exists.
    Returns the path to the resulting audio file.
    """
    # Name for looped file: include target_duration in name
    base, ext = os.path.splitext(os.path.basename(audio_file))
    looped_name = f"looped_{base}_{int(target_duration)}s.mp3"
    looped_path = os.path.join(BASE_DIR, looped_name)

    # --- CACHING DISABLED: always recreate the looped audio ---
    # Remove existing if present
    if os.path.exists(looped_path):
        try:
            os.remove(looped_path)
            logging.info(f"Removed stale looped audio: {looped_name}")
        except Exception:
            pass

    # Perform looping
    try:
        audio = AudioSegment.from_file(audio_file)
    except Exception as e:
        logging.error(f"Error loading audio file {audio_file}: {e}")
        return audio_file  # fallback

    original_duration = len(audio) / 1000.0
    if original_duration <= 0:
        logging.warning(f"Original audio has zero length: {audio_file}")
        return audio_file
    loops_needed = int(target_duration / original_duration) + 1
    full_audio = audio * loops_needed  # Repeat the audio
    trimmed_audio = full_audio[:int(target_duration * 1000)]
    try:
        trimmed_audio.export(looped_path, format="mp3")
        logging.info(f"Created looped audio: {looped_name}")
        return looped_path
    except Exception as e:
        logging.error(f"Failed exporting looped audio: {e}")
        return audio_file  # fallback

def trim_audio(audio_file, max_duration=30):
    """
    Trims the given audio file to a maximum duration (in seconds).
    Caches the result if possible.
    Returns the path to the trimmed audio file.
    """
    base, ext = os.path.splitext(os.path.basename(audio_file))
    trimmed_name = f"trimmed_{base}_{int(max_duration)}s.mp3"
    trimmed_path = os.path.join(BASE_DIR, trimmed_name)

    # --- CACHING DISABLED: always recreate trimmed audio ---
    if os.path.exists(trimmed_path):
        try:
            os.remove(trimmed_path)
            logging.info(f"Removed stale trimmed audio: {trimmed_name}")
        except Exception:
            pass

    # Perform trimming
    try:
        audio = AudioSegment.from_file(audio_file)
    except Exception as e:
        logging.error(f"Error loading audio file {audio_file}: {e}")
        return audio_file
    trimmed_audio = audio[:max_duration * 1000]  # Trim to max_duration seconds
    try:
        trimmed_audio.export(trimmed_path, format="mp3")
        logging.info(f"Created trimmed audio: {trimmed_name}")
        return trimmed_path
    except Exception as e:
        logging.error(f"Failed exporting trimmed audio: {e}")
        return audio_file

# === END: Performance enhancements ===


def fetch_quote():
    """Fetches a random motivational quote from ZenQuotes API."""
    global quote_data
    # Always fetch a fresh quote; do not reuse previous quote_data
    url = "https://zenquotes.io/api/random"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        logging.info(f"Fetched data: {data}")
        if isinstance(data, list) and data:
            result = {"quote": data[0].get("q", "No quote found"),
                      "author": data[0].get("a", "Unknown")}
            quote_data = result
            return result
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching quote: {e}")
    # On error, still update global to avoid stale
    result = {"quote": "No quote found", "author": "Unknown"}
    quote_data = result
    return result

def fetch_voiceover(quote, api_key):
    """Fetches voiceover for the given quote using VoiceRSS API (and caches per-quote)."""
    global voiceover_file, _voiceover_cached_quote

    # Always fetch new voiceover for the quote
    # Remove old cached file if it exists
    if voiceover_file and os.path.exists(voiceover_file):
        try:
            os.remove(voiceover_file)
            logging.info("Removed previous voiceover file to fetch new")
        except Exception as e:
            logging.warning(f"Could not remove old voiceover: {e}")
    # Also if VOICEOVER_FILENAME exists from disk, remove it
    if os.path.exists("voiceover.mp3"):
        try:
            os.remove("voiceover.mp3")
            logging.info("Removed existing voiceover.mp3 on disk to fetch new")
        except Exception:
            pass

    voiceover_file = None
    _voiceover_cached_quote = None

    # Download new voiceover for the current quote
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
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        file_path = "voiceover.mp3"
        with open(file_path, "wb") as f:
            f.write(response.content)
        logging.info(f"Downloaded new voiceover to {file_path}")
        voiceover_file = file_path
        _voiceover_cached_quote = quote
        return voiceover_file
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

class AnimatedQuoteWithBackground(Scene):
    def construct(self):
        # Set total duration of the scene (in seconds)
        total_duration = 7

        # Add looping background sound (trimmed to total_duration)
        cool_effect_file = SOUND_FILENAME  # "subclip.ogg"
        looped_effect = loop_sound(SOUND_PATH, total_duration)
        self.add_sound(looped_effect, gain=-5)

        # Extract video frames from background video
        video_background_file = VIDEO_FILENAME  # "219305_tiny.mp4"
        video_frames = extract_video_frames(VIDEO_PATH, fps=30)

        # Instead of animating every frame, select a subset.
        # Aim for one frame transition every ~2 seconds.
        desired_transitions = int(total_duration // 2)
        if video_frames:
            frame_interval = max(1, len(video_frames) // desired_transitions)
        else:
            frame_interval = 1
        selected_frames = video_frames[::frame_interval] if video_frames else []

        # Preload ImageMobject instances for smoother playback
        bg_mobjects = []
        for frame_path in selected_frames:
            try:
                mob = ImageMobject(frame_path).scale(4)
                bg_mobjects.append(mob)
            except Exception as e:
                logging.warning(f"Failed to load frame {frame_path}: {e}")

        if bg_mobjects:
            # Add all with opacity=0, then show the first
            for mob in bg_mobjects:
                mob.set_opacity(0)
                self.add(mob)
            bg_mobjects[0].set_opacity(1)
            bg_image = bg_mobjects[0]
        else:
            bg_image = None
            logging.warning("No background frames available.")

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
        if bg_image:
            for next_mob in bg_mobjects[1:]:
                # Transition opacity: fade out current bg_image, fade in next_mob
                self.play(
                    bg_image.animate.set_opacity(0),
                    next_mob.animate.set_opacity(1),
                    run_time=bg_transition_time
                )
                bg_image = next_mob

        # Calculate total animation time spent.
        time_text = time_fadein + time_write + time_color + time_scale + time_author
        time_bg = (len(bg_mobjects) - 1) * bg_transition_time if bg_mobjects else 0
        time_used = time_text + time_bg

        # Wait the remaining time so that the full scene lasts exactly total_duration.
        remaining_time = max(0, total_duration - time_used)
        self.wait(remaining_time)
