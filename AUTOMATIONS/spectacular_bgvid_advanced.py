from manim import *
from manim import config
import requests
import logging
import os
from io import BytesIO
from PIL import Image
import textwrap
from pydub import AudioSegment
import subprocess
import json
import random  # for random choice in Pexels results
import tempfile  # for temporary download if desired
import shutil

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load API keys from environment variables
cat_api_key = os.environ.get("CAT_API_KEY")
voice_api_key = os.environ.get("VOICE_RSS_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY")  # <-- added PIXABAY lookup

# Global variables (no longer used for caching, but kept for structure)
quote_data = None
voiceover_file = None

# Introduce a new global to track the last quote used for voiceover caching (not used for caching here)
_voiceover_cached_quote = None

# === BEGIN: Performance enhancements ===
# 1) Resolve paths relative to script location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Default filenames (unchanged functionality)
VIDEO_FILENAME = "46026-447087782_medium.mp4"
SOUND_FILENAME = "subclip.ogg"

VIDEO_PATH = os.path.join(BASE_DIR, VIDEO_FILENAME)
SOUND_PATH = os.path.join(BASE_DIR, SOUND_FILENAME)

# Frames directory and metadata file
FRAMES_DIR = os.path.join(BASE_DIR, "video_frames")
METADATA_PATH = os.path.join(FRAMES_DIR, "frames_meta.json")

# Explicit media directories (we will only clear these)
BG_VIDEOS_DIR = os.path.join(BASE_DIR, "bg_videos")
BG_SOUNDS_DIR = os.path.join(BASE_DIR, "bg_sounds")

# Ensure directories exist
os.makedirs(BG_VIDEOS_DIR, exist_ok=True)
os.makedirs(BG_SOUNDS_DIR, exist_ok=True)
os.makedirs(FRAMES_DIR, exist_ok=True)

def load_frames_metadata():
    """Load metadata dict from METADATA_PATH if exists; else return None."""
    # CACHING DISABLED: always return None
    return None

def save_frames_metadata(video_path, mtime):
    """Save metadata about extracted frames."""
    # CACHING DISABLED: still write metadata if desired, but it won't be used
    data = {"video_path": video_path, "mtime": mtime}
    try:
        os.makedirs(os.path.dirname(METADATA_PATH), exist_ok=True)
        with open(METADATA_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        logging.warning(f"Could not write frames metadata: {e}")

def extract_video_frames(video_file, fps=30):
    """
    Extracts frames from the given video file using FFmpeg with subprocess.
    CACHING DISABLED: always re-extract frames.
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
    try:
        if os.path.exists(METADATA_PATH):
            os.remove(METADATA_PATH)
    except Exception:
        pass

    # First, clear existing frames (only .png files)
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
    # DEFENSIVE CHECK: ensure file exists
    if not os.path.exists(audio_file):
        logging.warning(f"get_audio_duration: file not found: {audio_file}")
        return None
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
    CACHING DISABLED: always recreate the looped audio.
    Returns the path to the resulting audio file, or None on failure.
    """
    # DEFENSIVE CHECK: ensure input exists
    if not os.path.exists(audio_file):
        logging.warning(f"loop_sound: input audio file does not exist: {audio_file}")
        return None

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
        return None  # fallback

    original_duration = len(audio) / 1000.0
    if original_duration <= 0:
        logging.warning(f"Original audio has zero length: {audio_file}")
        return None
    loops_needed = int(target_duration / original_duration) + 1
    full_audio = audio * loops_needed  # Repeat the audio
    trimmed_audio = full_audio[:int(target_duration * 1000)]
    try:
        trimmed_audio.export(looped_path, format="mp3")
        logging.info(f"Created looped audio: {looped_name}")
        return looped_path
    except Exception as e:
        logging.error(f"Failed exporting looped audio: {e}")
        return None  # fallback

def trim_audio(audio_file, max_duration=30):
    """
    Trims the given audio file to a maximum duration (in seconds).
    CACHING DISABLED: always recreate trimmed audio.
    Returns the path to the trimmed audio file, or None on failure.
    """
    # DEFENSIVE CHECK: ensure input exists
    if not os.path.exists(audio_file):
        logging.warning(f"trim_audio: input audio file does not exist: {audio_file}")
        return None

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
        return None
    trimmed_audio = audio[:max_duration * 1000]  # Trim to max_duration seconds
    try:
        trimmed_audio.export(trimmed_path, format="mp3")
        logging.info(f"Created trimmed audio: {trimmed_name}")
        return trimmed_path
    except Exception as e:
        logging.error(f"Failed exporting trimmed audio: {e}")
        return None

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
    """Fetches voiceover for the given quote using VoiceRSS API (always fetch new)."""
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

# --- helper to stream-download safely (added) ---
def _download_stream_to(path, url, headers=None, timeout=30):
    """Stream a URL to a temp .part file and atomically rename on success."""
    tmp = path + ".part"
    try:
        with requests.get(url, stream=True, headers=(headers or {}), timeout=timeout) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
        os.rename(tmp, path)
        logging.info(f"Saved downloaded file to {path}")
        return True
    except Exception as e:
        logging.warning(f"Download failed for {url}: {e}")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False

def fetch_pexels_video(query="nature", per_page=15):
    """
    Fetch a random short video from Pexels matching `query`. Downloads it locally
    (overwriting any previous fetch at a fixed filename), and returns the local file path.
    If PEXELS_API_KEY is not set or any error occurs, returns None.
    """
    if not PEXELS_API_KEY:
        logging.warning("PEXELS_API_KEY not set; cannot fetch background video from Pexels.")
        return None
    search_url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": PEXELS_API_KEY}
    params = {"query": query, "per_page": per_page, "page": 1}
    try:
        resp = requests.get(search_url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logging.error(f"Error searching Pexels videos for '{query}': {e}")
        return None

    videos = data.get("videos", [])
    if not videos:
        logging.warning(f"No Pexels videos found for query: {query}")
        return None

    # Pick a random video from results
    choice = random.choice(videos)
    video_files = choice.get("video_files", [])
    if not video_files:
        logging.warning(f"No video_files entries in chosen Pexels result for '{query}'")
        return None

    # Prefer medium quality if available, else pick random
    file_url = None
    # Try to pick a medium resolution
    for vf in video_files:
        if vf.get("quality") == "sd" and vf.get("link"):
            file_url = vf["link"]
            break
    if not file_url:
        # fallback to any available link
        candidates = [vf.get("link") for vf in video_files if vf.get("link")]
        if candidates:
            file_url = random.choice(candidates)
    if not file_url:
        logging.warning(f"No download URL found for Pexels video for '{query}'")
        return None

    # Download video to a fixed local path, e.g., "pexels_bg.mp4" in BASE_DIR
    local_filename = os.path.join(BASE_DIR, "pexels_bg.mp4")
    try:
        logging.info(f"Downloading Pexels video for background: {file_url}")
        success = _download_stream_to(local_filename, file_url, headers=headers)
        if success:
            logging.info(f"Saved Pexels background video to: {local_filename}")
            return local_filename
        else:
            return None
    except Exception as e:
        logging.error(f"Failed to download Pexels video {file_url}: {e}")
        try:
            if os.path.exists(local_filename + ".part"):
                os.remove(local_filename + ".part")
        except Exception:
            pass
        return None

# --- ADDED: Pixabay fallback fetch (new) ---
def fetch_pixabay_video(query="nature", per_page=20):
    """
    Fetch one video from Pixabay for `query` and save to local file.
    Returns local path on success, None on failure.
    """
    if not PIXABAY_API_KEY:
        logging.info("PIXABAY_API_KEY not set; skipping Pixabay fetch.")
        return None
    url = "https://pixabay.com/api/videos/"
    params = {"key": PIXABAY_API_KEY, "q": query, "per_page": per_page}
    try:
        resp = requests.get(url, params=params, timeout=12)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logging.warning(f"Pixabay search failed: {e}")
        return None

    hits = data.get("hits", [])
    if not hits:
        logging.info("Pixabay returned no video hits.")
        return None

    random.shuffle(hits)
    for hit in hits:
        vids = hit.get("videos", {})
        file_url = None
        # prefer medium/large
        for size in ("medium","large","small","tiny"):
            if vids.get(size) and vids[size].get("url"):
                file_url = vids[size]["url"]
                break
        if not file_url:
            continue
        local_filename = os.path.join(BASE_DIR, "pixabay_bg.mp4")
        logging.info(f"Pixabay: trying to download {file_url}")
        success = _download_stream_to(local_filename, file_url)
        if success and os.path.exists(local_filename):
            logging.info(f"Saved Pixabay background video to: {local_filename}")
            return local_filename
    return None

# --- ADDED: combined fetch that tries Pexels then Pixabay for a topic (new) ---
def fetch_background_video_for_topic(topic="nature"):
    logging.info(f"Attempting to fetch fresh background video for topic: '{topic}'")
    # Try Pexels first
    p = fetch_pexels_video(topic)
    if p:
        logging.info("Fetched background from Pexels.")
        return p
    # Fallback to Pixabay
    q = fetch_pixabay_video(topic)
    if q:
        logging.info("Fetched background from Pixabay.")
        return q
    logging.warning("Could not fetch background from Pexels or Pixabay for topic '%s'." % topic)
    return None

class AnimatedQuoteWithBackground(Scene):
    def construct(self):
        # Set total duration of the scene (in seconds) — default, may be adjusted below
        total_duration = 7

        # ---- NEW: clear prior downloaded background and frames to force fresh fetch every run ----
        # Clear only the designated media directories so we do not remove notebooks/scripts.
        def _remove_path_safe(path):
            try:
                if os.path.islink(path) or os.path.isfile(path):
                    os.remove(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path)
            except Exception:
                logging.debug(f"Failed to remove {path}; ignoring.")

        def _clear_media_dir(dirpath, preserve_names=()):
            """
            Remove all files/folders inside dirpath except names listed in preserve_names.
            Does NOT touch dirpath itself or anything outside it.
            """
            if not os.path.isdir(dirpath):
                return
            for name in os.listdir(dirpath):
                if name in preserve_names:
                    logging.info(f"Preserving {os.path.join(dirpath, name)}")
                    continue
                _remove_path_safe(os.path.join(dirpath, name))

        logging.info("Clearing previous background files & frames (inside designated media dirs only).")
        # Preserve subclip.ogg filename if present in BG_SOUNDS_DIR
        preserve_name = os.path.basename(SOUND_PATH)
        _clear_media_dir(BG_VIDEOS_DIR, preserve_names=())
        _clear_media_dir(BG_SOUNDS_DIR, preserve_names=(preserve_name,))
        # Clear frames directory fully (we will re-extract frames)
        _clear_media_dir(FRAMES_DIR, preserve_names=())

        # Also remove known temporary downloaded background files in BASE_DIR (explicit whitelist)
        for tmp_name in ("pexels_bg.mp4", "pixabay_bg.mp4"):
            tmp_path = os.path.join(BASE_DIR, tmp_name)
            if os.path.exists(tmp_path):
                _remove_path_safe(tmp_path)

        # === Fetch Background Video topic selection happens later; first fetch quote + voiceover ===

        # === Quote and Voiceover Logic ===
        quote_info = fetch_quote()
        raw = quote_info.get('quote', 'No quote found')
        display_q = f'"{raw}"'
        author = quote_info.get('author', 'Unknown')

        # Fetch voiceover (always fetch new)
        audio = fetch_voiceover(raw, voice_api_key)

        # If we got an audio file, measure its duration and set total_duration accordingly (with small padding)
        measured_voice_dur = None
        if audio and os.path.exists(audio):
            try:
                measured_voice_dur = AudioSegment.from_file(audio).duration_seconds
                logging.info(f"Measured voiceover duration: {measured_voice_dur:.2f}s")
            except Exception as e:
                logging.warning(f"Could not measure voiceover duration: {e}")
                measured_voice_dur = None

        if measured_voice_dur and measured_voice_dur > 0:
            total_duration = float(measured_voice_dur) + 0.25
            # cap to a reasonable maximum to avoid extremely long videos
            if total_duration > 120:
                total_duration = 120.0
            logging.info(f"Scene total_duration set from voiceover: {total_duration:.2f}s")
        else:
            logging.info(f"Using fallback/default total_duration: {total_duration:.2f}s")

        # Now that total_duration is known, prepare/loop background sound trimmed to total_duration (if available)
        if os.path.exists(SOUND_PATH):
            looped_effect = loop_sound(SOUND_PATH, total_duration)
            if looped_effect and os.path.exists(looped_effect):
                self.add_sound(looped_effect, gain=-5)
        else:
            logging.warning(f"Background sound file not found at {SOUND_PATH}.")

        # === Fetch Background Video ===
        # Choose a topic at random from ['nature','birds','art'] unless overridden by env var
        env_topic = os.environ.get("BG_QUERY", None)
        if env_topic:
            chosen_topic = env_topic
            logging.info(f"BG_QUERY provided via env: '{chosen_topic}'")
        else:
            chosen_topic = random.choice(["nature", "birds", "art"])
            logging.info(f"No BG_QUERY set — randomly selected topic: '{chosen_topic}'")

        # Try to fetch a fresh video for chosen topic (Pexels -> Pixabay). If not found,
        # fall back to the local VIDEO_PATH that was the original behavior.
        fetched_video = fetch_background_video_for_topic(chosen_topic)
        video_background_file = fetched_video if (fetched_video and os.path.exists(fetched_video)) else VIDEO_PATH

        # === BREAK MEDIA INTO CONSTITUENT IMAGES (RAPID DISPLAY) ===
        # Extract at high FPS (30) to get a dense pool of frames
        video_frames = extract_video_frames(video_background_file, fps=30)
        
        if not video_frames:
            logging.error("No background frames available. Scene will have no background.")
            bg_pool = []
        else:
            # Preload a pool of ImageMobjects for the rapid-flicker effect
            # We scale them to fit the frame dimensions
            bg_pool = [
                ImageMobject(img).scale_to_fit_width(config.frame_width) 
                for img in video_frames[:150] # Limit pool to manage memory
            ]

        # --- UPDATED FIX: Use set_z_index and self.add() to ensure background stays behind text ---
        if bg_pool:
            bg_container = bg_pool[0].copy()
            bg_container.set_z_index(-10) # Force background to the bottom layer
            self.add(bg_container) 

            # Define the "Very Fast Display" functionality via an Updater
            # This changes the image 15 times per second (strobe effect)
            def rapid_image_swap(mob, dt):
                swap_speed = 15  # Images per second
                index = int((self.time * swap_speed) % len(bg_pool))
                mob.become(bg_pool[index])

            bg_container.add_updater(rapid_image_swap)

        # Quote + voiceover mobjects
        q_mobj, a_mobj = create_quote_mobjects(display_q, author, self.camera.frame_width, self.camera.frame_height)
        q_mobj.move_to(UP * 0.5)
        a_mobj.next_to(q_mobj, DOWN, buff=0.4)

        # Add voiceover: if it exists, trim if longer than the scene; else add as-is
        if audio and os.path.exists(audio):
            try:
                voice_len = AudioSegment.from_file(audio).duration_seconds
            except Exception:
                voice_len = None
            if voice_len and voice_len > total_duration + 0.001:
                trimmed = trim_audio(audio, max_duration=total_duration)
                if trimmed and os.path.exists(trimmed):
                    self.add_sound(trimmed, gain=+10)
            else:
                self.add_sound(audio, gain=+10)

        # === TEXT ANIMATION (Concurrently with Background Strobe) ===
        # Ensure text has a higher z_index (default is 0) so it stays on top
        time_fadein = 0.8
        time_write = 2
        time_color = 1
        time_scale = 0.8
        time_author = 0.8

        self.play(FadeIn(q_mobj, shift=UP, scale=1.2), run_time=time_fadein)
        self.play(Write(q_mobj), run_time=time_write)
        self.play(q_mobj.animate.set_color_by_gradient(BLUE, PURPLE), run_time=time_color)
        self.play(q_mobj.animate.scale(1.1), run_time=time_scale)
        self.play(FadeIn(a_mobj, shift=UP), run_time=time_author)

        # Calculate remaining time to hit exactly total_duration
        time_used = time_fadein + time_write + time_color + time_scale + time_author
        remaining_time = max(0, total_duration - time_used)
        
        self.wait(remaining_time)

if __name__ == '__main__':
    # Optionally pre-extract before rendering (set env var AUTO_PREEXTRACT=1)
    if os.environ.get("AUTO_PREEXTRACT", "0") in ("1", "true", "yes"):
        if os.path.exists(VIDEO_PATH):
            extract_video_frames(VIDEO_PATH, fps=30)
    pass
