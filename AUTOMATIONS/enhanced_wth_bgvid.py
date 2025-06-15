from manim import *
import requests
import logging
import os
import textwrap
import subprocess
import json
from pydub import AudioSegment
import random
import shutil
import tempfile
import stat
from io import BytesIO
from PIL import Image

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load API keys from environment variables
cat_api_key = os.environ.get("CAT_API_KEY")
voice_api_key = os.environ.get("VOICE_RSS_API_KEY")

# === BEGIN: Pixabay/Pexels integration & random background & pre-extraction ===

# Directories containing candidate background videos and sounds:
BG_VIDEOS_DIR = os.environ.get("BG_VIDEOS_DIR", "bg_videos")
BG_SOUNDS_DIR = os.environ.get("BG_SOUNDS_DIR", "bg_sounds")

# Create video and audio folders if missing
os.makedirs(BG_VIDEOS_DIR, exist_ok=True)
os.makedirs(BG_SOUNDS_DIR, exist_ok=True)

# Filenames your script expects:
EXPECTED_VIDEO = "219305_tiny.mp4"
EXPECTED_SOUND = "subclip.ogg"

# Frames directory used by extract_video_frames:
FRAMES_DIR = "video_frames"

# --- FORCE_POPULATE flag ---
FORCE_POPULATE = os.environ.get("FORCE_POPULATE", "").lower() in ("1", "true", "yes")
if FORCE_POPULATE:
    logging.info("FORCE_POPULATE is set: directories will be cleared and repopulated if API keys are available.")

# --- Pixabay & Pexels-based population logic ---

PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")

# Allow user to configure queries via environment, comma-separated:
VIDEO_QUERIES = os.environ.get("VIDEO_QUERIES", "nature,forest,waterfall").split(",")
SOUND_QUERIES = os.environ.get("SOUND_QUERIES", "rain,wind,forest ambiance").split(",")

def fetch_pixabay_videos(query="nature", per_page=20, num_downloads=1, prefer_resolution="medium"):
    """
    Search Pixabay for videos matching `query`, download up to `num_downloads` distinct videos
    into BG_VIDEOS_DIR. Returns list of local paths.
    """
    if not PIXABAY_API_KEY:
        logging.warning("PIXABAY_API_KEY not set; skipping Pixabay video fetch.")
        return []
    url = "https://pixabay.com/api/videos/"
    params = {
        "key": PIXABAY_API_KEY,
        "q": query,
        "per_page": per_page,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logging.error(f"Error searching Pixabay videos for '{query}': {e}")
        return []

    hits = data.get("hits", [])
    if not hits:
        logging.warning(f"No Pixabay videos found for query: {query}")
        return []

    random.shuffle(hits)
    downloaded = []
    for hit in hits[:num_downloads]:
        vids = hit.get("videos", {})
        file_url = None
        # Prefer the specified resolution
        if prefer_resolution in vids and vids[prefer_resolution].get("url"):
            file_url = vids[prefer_resolution]["url"]
        else:
            # fallback to any available
            for size in ("large","medium","small","tiny"):
                if vids.get(size,{}).get("url"):
                    file_url = vids[size]["url"]
                    break
        if not file_url:
            continue
        # Strip query params
        filename = os.path.basename(file_url.split("?")[0])
        local_path = os.path.join(BG_VIDEOS_DIR, filename)
        if os.path.exists(local_path):
            logging.info(f"Pixabay video already exists, skipping: {filename}")
            downloaded.append(local_path)
            continue
        # Download
        try:
            logging.info(f"Downloading Pixabay video: {file_url}")
            with requests.get(file_url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(local_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024*1024):
                        f.write(chunk)
            downloaded.append(local_path)
        except Exception as e:
            logging.error(f"Failed to download Pixabay video {file_url}: {e}")
    return downloaded

def video_has_audio(video_path):
    """
    Use ffmpeg to probe if the downloaded video has an audio stream.
    Returns True if audio stream is present, False otherwise.
    """
    # Run ffmpeg -i and parse stderr for "Audio:"
    cmd = ["ffmpeg", "-i", video_path]
    # We capture stderr only
    try:
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=False)
        stderr = proc.stderr or ""
        # Look for "Audio:" in the ffmpeg output
        if "Audio:" in stderr:
            return True
    except Exception as e:
        logging.warning(f"Error probing video for audio: {e}")
    return False

def fetch_pexels_sound(query="rain", per_page=15):
    """
    Search Pexels for videos matching `query`, download one short video clip that has audio,
    extract its audio track via ffmpeg into BG_SOUNDS_DIR, and return the audio path.
    If a clip has no audio, skip it and try another until exhausted.
    """
    if not PEXELS_API_KEY:
        logging.warning("PEXELS_API_KEY not set; skipping Pexels sound fetch.")
        return None

    headers = {
        "Authorization": PEXELS_API_KEY
    }
    search_url = "https://api.pexels.com/videos/search"
    params = {
        "query": query,
        "per_page": per_page,
        "page": 1
    }
    try:
        resp = requests.get(search_url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logging.error(f"Error searching Pexels videos for sound '{query}': {e}")
        return None

    videos = data.get("videos", [])
    if not videos:
        logging.warning(f"No Pexels videos found for sound query: {query}")
        return None

    # Shuffle list so we try random order
    random.shuffle(videos)
    for choice in videos:
        video_files = choice.get("video_files", [])
        if not video_files:
            continue
        # Prefer SD ("sd") if available to reduce size
        candidates = []
        sd_url = None
        for vf in video_files:
            if vf.get("quality") == "sd" and vf.get("link"):
                sd_url = vf["link"]
                break
            elif vf.get("link"):
                candidates.append(vf["link"])
        if sd_url:
            file_url = sd_url
        elif candidates:
            file_url = random.choice(candidates)
        else:
            continue

        # Download video to temporary file
        tmp_video_path = os.path.join(
            tempfile.gettempdir(),
            f"pexels_{query.replace(' ','_')}_{random.randint(0, int(1e6))}.mp4"
        )
        try:
            logging.info(f"Downloading Pexels video for sound '{query}': {file_url}")
            with requests.get(file_url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(tmp_video_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024*1024):
                        f.write(chunk)
        except Exception as e:
            logging.error(f"Failed to download Pexels video {file_url}: {e}")
            try:
                os.remove(tmp_video_path)
            except Exception:
                pass
            continue

        # Probe for audio
        if not video_has_audio(tmp_video_path):
            logging.info(f"Downloaded Pexels clip has no audio track, skipping: {file_url}")
            try:
                os.remove(tmp_video_path)
            except Exception:
                pass
            continue

        # Extract audio via ffmpeg: output MP3 in BG_SOUNDS_DIR
        audio_filename = f"pexels_{query.replace(' ','_')}_{choice.get('id', '0')}.mp3"
        audio_path = os.path.join(BG_SOUNDS_DIR, audio_filename)
        # If already exists, skip extraction
        if os.path.exists(audio_path):
            logging.info(f"Pexels-derived sound already exists, skipping extraction: {audio_filename}")
            try:
                os.remove(tmp_video_path)
            except Exception:
                pass
            return audio_path

        # Run ffmpeg to extract audio
        # ffmpeg -i input.mp4 -vn -acodec libmp3lame -q:a 4 output.mp3
        cmd = [
            "ffmpeg", "-y", "-i", tmp_video_path,
            "-vn", "-acodec", "libmp3lame", "-q:a", "4",
            audio_path
        ]
        logging.info(f"Extracting audio via ffmpeg: {' '.join(cmd)}")
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except Exception as e:
            logging.error(f"ffmpeg audio extraction failed: {e}")
        finally:
            # Always attempt to remove temp video
            try:
                os.remove(tmp_video_path)
            except Exception:
                pass

        if os.path.exists(audio_path):
            logging.info(f"Extracted audio saved to: {audio_path}")
            return audio_path
        else:
            logging.warning(f"ffmpeg did not produce audio file for '{query}', trying next clip if any")
            # continue to next clip
            continue

    # If we reach here, no clip produced audio
    logging.warning(f"No Pexels video with audio found for query '{query}'")
    return None

def populate_media_if_needed():
    """
    If FORCE_POPULATE is set, clear BG_VIDEOS_DIR / BG_SOUNDS_DIR first (if API key present).
    Then:
      - If BG_VIDEOS_DIR is empty and PIXABAY_API_KEY is set, populate with Pixabay videos.
      - If BG_SOUNDS_DIR is empty and PEXELS_API_KEY is set, populate with Pexels-derived audio.
    Uses VIDEO_QUERIES and SOUND_QUERIES for terms.
    """
    # Populate videos
    try:
        files = os.listdir(BG_VIDEOS_DIR)
    except Exception:
        files = []
    need_video_pop = False
    if FORCE_POPULATE:
        need_video_pop = True
        logging.info("FORCE_POPULATE: clearing BG_VIDEOS_DIR")
        for f in files:
            path = os.path.join(BG_VIDEOS_DIR, f)
            try:
                if os.path.isfile(path) or os.path.islink(path):
                    os.remove(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path)
            except Exception:
                pass
    elif not files:
        need_video_pop = True
        logging.info("BG_VIDEOS_DIR is empty; populating from Pixabay...")
    if need_video_pop and PIXABAY_API_KEY:
        for q in VIDEO_QUERIES:
            q = q.strip()
            if not q:
                continue
            try:
                fetched = fetch_pixabay_videos(query=q, per_page=30, num_downloads=1, prefer_resolution="medium")
                if fetched:
                    logging.info(f"Fetched {len(fetched)} video(s) for query '{q}'")
                # stop if folder has files now
                if os.listdir(BG_VIDEOS_DIR):
                    break
            except Exception as e:
                logging.error(f"Error populating video for query '{q}': {e}")
    else:
        logging.info("Skipping video population (either folder non-empty/no FORCE_POPULATE, or no PIXABAY_API_KEY).")

    # Populate sounds
    try:
        files = os.listdir(BG_SOUNDS_DIR)
    except Exception:
        files = []
    need_sound_pop = False
    if FORCE_POPULATE:
        need_sound_pop = True
        logging.info("FORCE_POPULATE: clearing BG_SOUNDS_DIR")
        for f in files:
            path = os.path.join(BG_SOUNDS_DIR, f)
            try:
                if os.path.isfile(path) or os.path.islink(path):
                    os.remove(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path)
            except Exception:
                pass
    elif not files:
        need_sound_pop = True
        logging.info("BG_SOUNDS_DIR is empty; populating from Pexels videos (extracting audio)...")
    if need_sound_pop and PEXELS_API_KEY:
        for q in SOUND_QUERIES:
            q = q.strip()
            if not q:
                continue
            try:
                path = fetch_pexels_sound(query=q)
                if path:
                    logging.info(f"Fetched sound for query '{q}' via Pexels")
                # stop if folder has files now
                if os.listdir(BG_SOUNDS_DIR):
                    break
            except Exception as e:
                logging.error(f"Error populating sound for query '{q}': {e}")
    else:
        logging.info("Skipping sound population (either folder non-empty/no FORCE_POPULATE, or no PEXELS_API_KEY).")

# Attempt to populate if needed at import time
populate_media_if_needed()

def pick_random_file(directory, exts):
    """
    Pick a random file in `directory` whose extension is in `exts`.
    Returns full path or None if none found.
    """
    if not os.path.isdir(directory):
        logging.warning(f"Directory for random selection not found: {directory}")
        return None
    candidates = [
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if any(f.lower().endswith("."+e.lower()) for e in exts)
    ]
    if not candidates:
        logging.warning(f"No files with extensions {exts} in {directory}")
        return None
    choice = random.choice(candidates)
    logging.info(f"Randomly selected: {choice}")
    return choice

def pre_extract_frames(video_src, output_dir, src_fps=30, tgt_fps=15):
    """
    Extract frames from video_src at src_fps, then sub-sample to tgt_fps,
    placing results in output_dir. Removes any existing output_dir first.
    """
    if not os.path.exists(video_src):
        logging.warning(f"Video for pre-extraction not found: {video_src}")
        return False
    # Remove old frames
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Use a temp dir for raw extraction
    tmp = tempfile.mkdtemp(prefix="preextract_")
    try:
        pattern = os.path.join(tmp, "frame%05d.png")
        cmd = [
            "ffmpeg", "-y", "-i", video_src,
            "-vf", f"fps={src_fps}",
            pattern
        ]
        logging.info(f"Pre-extracting frames: {' '.join(cmd)}")
        # Run real ffmpeg
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        files = sorted(f for f in os.listdir(tmp) if f.startswith("frame") and f.endswith(".png"))
        if not files:
            logging.warning("No frames extracted in pre-extraction.")
            return False
        step = max(1, int(src_fps // tgt_fps))
        selected = files[::step]
        for fname in selected:
            shutil.copy(os.path.join(tmp, fname), os.path.join(output_dir, fname))
        logging.info(f"Copied {len(selected)} frames into {output_dir}")
        return True
    finally:
        shutil.rmtree(tmp)

def prepare_random_background_and_sound():
    """
    Picks a random video and sound, places them as EXPECTED_VIDEO and EXPECTED_SOUND,
    and pre-extracts frames for the chosen video into FRAMES_DIR.
    """
    # 1. Video
    vid = pick_random_file(BG_VIDEOS_DIR, ["mp4","mov","mkv","avi"])
    if vid:
        # remove existing
        if os.path.exists(EXPECTED_VIDEO):
            try:
                os.remove(EXPECTED_VIDEO)
            except Exception:
                pass
        # try symlink, else copy
        try:
            os.symlink(os.path.abspath(vid), EXPECTED_VIDEO)
            logging.info(f"Symlinked {EXPECTED_VIDEO} -> {vid}")
        except Exception:
            shutil.copy(vid, EXPECTED_VIDEO)
            logging.info(f"Copied {vid} to {EXPECTED_VIDEO}")
        # Pre-extract frames for smoother background
        # You can tune src_fps and tgt_fps for smoother motion / performance trade-off
        pre_extract_frames(EXPECTED_VIDEO, FRAMES_DIR, src_fps=30, tgt_fps=15)
    else:
        logging.warning("No background video chosen; extract_video_frames will run normally.")

    # 2. Sound
    snd = pick_random_file(BG_SOUNDS_DIR, ["mp3","ogg","wav"])
    if snd:
        if os.path.exists(EXPECTED_SOUND):
            try:
                os.remove(EXPECTED_SOUND)
            except Exception:
                pass
        # Symlink or copy; note extension mismatch is usually acceptable since ffmpeg/pydub detect by content
        try:
            os.symlink(os.path.abspath(snd), EXPECTED_SOUND)
            logging.info(f"Symlinked {EXPECTED_SOUND} -> {snd}")
        except Exception:
            shutil.copy(snd, EXPECTED_SOUND)
            logging.info(f"Copied {snd} to {EXPECTED_SOUND}")
    else:
        logging.warning("No background sound chosen; loop_sound will error if expecting subclip.ogg.")

# Run preparation at import time, before any Scene or ffmpeg calls in extract_video_frames
prepare_random_background_and_sound()

# === END: Pixabay/Pexels integration & random background & pre-extraction ===


# Global variables to store fetched data (avoiding redundant calls)
quote_data = None
voiceover_file = None
# Reset cached quote text tracker
_voiceover_cached_quote = None

def fetch_quote():
    """Fetches a random motivational quote from ZenQuotes API (always fresh)."""
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

    # If we have cached quote and it matches current quote, and file exists, reuse
    if _voiceover_cached_quote == quote and voiceover_file and os.path.exists(voiceover_file):
        logging.info(f"Reusing cached voiceover for the same quote: {voiceover_file}")
        return voiceover_file

    # Otherwise: need to fetch a new voiceover
    # Remove old cached file if it exists
    if voiceover_file and os.path.exists(voiceover_file):
        try:
            os.remove(voiceover_file)
            logging.info("Removed previous cached voiceover file")
        except Exception as e:
            logging.warning(f"Could not remove old cached voiceover: {e}")
    # Also if VOICEOVER_FILENAME exists from disk but was for a different quote, remove it
    if os.path.exists("voiceover.mp3") and _voiceover_cached_quote != quote:
        try:
            os.remove("voiceover.mp3")
            logging.info("Removed existing voiceover.mp3 on disk since quote changed")
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

def fetch_cat_image(api_key, target_width=1280, target_height=720):
    """
    Fetches a random cat image from TheCatAPI and saves it locally.
    Always fetches a new image (no caching), overwriting CAT_IMAGE_FILENAME.
    """
    CAT_IMAGE_FILENAME = "cat_image.jpg"
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    CAT_IMAGE_PATH = os.path.join(BASE_DIR, CAT_IMAGE_FILENAME)

    # Always fetch a new image; remove old if exists
    if os.path.exists(CAT_IMAGE_PATH):
        try:
            os.remove(CAT_IMAGE_PATH)
            logging.info("Removed old cached cat image to fetch a fresh one")
        except Exception:
            pass

    url = "https://api.thecatapi.com/v1/images/search"
    headers = {"x-api-key": api_key} if api_key else {}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list) and data:
            if "url" in data[0]:
                image_url = data[0]["url"]
                response2 = requests.get(image_url, timeout=10)
                response2.raise_for_status()
                img = Image.open(BytesIO(response2.content))
                # Optionally resize to target dimensions while preserving aspect:
                img = img.convert("RGB")
                img.save(CAT_IMAGE_PATH)
                logging.info(f"Fetched and saved fresh cat image to {CAT_IMAGE_PATH}")
                return CAT_IMAGE_PATH
            else:
                logging.error("No 'url' key found in the CatAPI response data.")
        else:
            logging.error("CatAPI response is not a valid list or is empty.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching cat image: {e}")
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
    if original_duration <= 0:
        logging.warning(f"Original audio has zero length: {audio_file}")
        return audio_file
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
    output_dir = FRAMES_DIR
    os.makedirs(output_dir, exist_ok=True)
    
    # If frames are already pre-extracted in output_dir, skip ffmpeg call:
    existing = [f for f in os.listdir(output_dir) if f.endswith(".png")]
    if existing:
        # Return existing frames sorted
        frame_files = [os.path.join(output_dir, f) for f in sorted(existing)]
        logging.info(f"Using pre-extracted {len(frame_files)} frames from {output_dir}")
        return frame_files

    # Otherwise, run ffmpeg as before
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
        # If EXPECTED_SOUND exists (symlinked or copied from BG_SOUNDS_DIR), loop it:
        looped_effect = loop_sound(cool_effect_file, total_duration)
        self.add_sound(looped_effect, gain=-5)

        # Extract video frames from background video
        video_background_file = "219305_tiny.mp4"
        video_frames = extract_video_frames(video_background_file, fps=30)
        
        # Instead of animating every frame, select a subset.
        # Aim for one frame transition every ~2 seconds.
        desired_transitions = int(total_duration // 2)
        frame_interval = max(1, len(video_frames) // desired_transitions) if video_frames else 1
        selected_frames = video_frames[::frame_interval] if video_frames else []
        
        # Create initial background image from the first selected frame.
        if selected_frames:
            bg_image = ImageMobject(selected_frames[0]).scale(4)
            self.add(bg_image)
        else:
            bg_image = None
        
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
            if bg_image:
                self.play(Transform(bg_image, new_bg), run_time=bg_transition_time)
                bg_image = new_bg
            else:
                self.add(new_bg)
                bg_image = new_bg

        # Calculate total animation time spent.
        time_text = time_fadein + time_write + time_color + time_scale + time_author
        time_bg = (len(selected_frames) - 1) * bg_transition_time
        time_used = time_text + time_bg

        # Wait the remaining time so that the full scene lasts exactly total_duration.
        remaining_time = max(0, total_duration - time_used)
        self.wait(remaining_time)
