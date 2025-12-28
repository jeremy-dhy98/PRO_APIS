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

# Filenames your script expects (constants)
EXPECTED_VIDEO = "219305_tiny.mp4"
EXPECTED_SOUND = "subclip.ogg"
CAT_IMAGE_FILENAME = "cat_image.jpg"

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

# (functions fetch_pixabay_videos and fetch_pexels_sound are identical in behaviour to your original ones
# but slightly hardened to always clean temporary files and to use stricter ffmpeg logging.)

def fetch_pixabay_videos(query="nature", per_page=20, num_downloads=1, prefer_resolution="medium"):
    if not PIXABAY_API_KEY:
        logging.warning("PIXABAY_API_KEY not set; skipping Pixabay video fetch.")
        return []
    url = "https://pixabay.com/api/videos/"
    params = {"key": PIXABAY_API_KEY, "q": query, "per_page": per_page}
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
        if prefer_resolution in vids and vids[prefer_resolution].get("url"):
            file_url = vids[prefer_resolution]["url"]
        else:
            for size in ("large", "medium", "small", "tiny"):
                if vids.get(size, {}).get("url"):
                    file_url = vids[size]["url"]
                    break
        if not file_url:
            continue
        filename = os.path.basename(file_url.split("?")[0])
        local_path = os.path.join(BG_VIDEOS_DIR, filename)
        if os.path.exists(local_path):
            logging.info(f"Pixabay video already exists, skipping: {filename}")
            downloaded.append(local_path)
            continue
        try:
            logging.info(f"Downloading Pixabay video: {file_url}")
            with requests.get(file_url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(local_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
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
    cmd = ["ffmpeg", "-hide_banner", "-i", video_path]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=False)
        stderr = proc.stderr or ""
        if "Audio:" in stderr:
            return True
    except Exception as e:
        logging.warning(f"Error probing video for audio: {e}")
    return False


def fetch_pexels_sound(query="rain", per_page=15):
    if not PEXELS_API_KEY:
        logging.warning("PEXELS_API_KEY not set; skipping Pexels sound fetch.")
        return None

    headers = {"Authorization": PEXELS_API_KEY}
    search_url = "https://api.pexels.com/videos/search"
    params = {"query": query, "per_page": per_page, "page": 1}
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

    random.shuffle(videos)
    for choice in videos:
        video_files = choice.get("video_files", [])
        if not video_files:
            continue
        candidates = []
        sd_url = None
        for vf in video_files:
            if vf.get("quality") == "sd" and vf.get("link"):
                sd_url = vf["link"]
                break
            elif vf.get("link"):
                candidates.append(vf["link"])
        file_url = sd_url if sd_url else (random.choice(candidates) if candidates else None)
        if not file_url:
            continue

        tmp_video_path = os.path.join(tempfile.gettempdir(), f"pexels_{query.replace(' ','_')}_{random.randint(0,int(1e6))}.mp4")
        try:
            logging.info(f"Downloading Pexels video for sound '{query}': {file_url}")
            with requests.get(file_url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(tmp_video_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
        except Exception as e:
            logging.error(f"Failed to download Pexels video {file_url}: {e}")
            try:
                os.remove(tmp_video_path)
            except Exception:
                pass
            continue

        if not video_has_audio(tmp_video_path):
            logging.info(f"Downloaded Pexels clip has no audio track, skipping: {file_url}")
            try:
                os.remove(tmp_video_path)
            except Exception:
                pass
            continue

        audio_filename = f"pexels_{query.replace(' ','_')}_{choice.get('id','0')}.mp3"
        audio_path = os.path.join(BG_SOUNDS_DIR, audio_filename)
        if os.path.exists(audio_path):
            logging.info(f"Pexels-derived sound already exists, skipping extraction: {audio_filename}")
            try:
                os.remove(tmp_video_path)
            except Exception:
                pass
            return audio_path

        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", tmp_video_path,
            "-vn", "-acodec", "libmp3lame", "-q:a", "4", audio_path
        ]
        logging.info(f"Extracting audio via ffmpeg: {' '.join(cmd)}")
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except Exception as e:
            logging.error(f"ffmpeg audio extraction failed: {e}")
        finally:
            try:
                os.remove(tmp_video_path)
            except Exception:
                pass

        if os.path.exists(audio_path):
            logging.info(f"Extracted audio saved to: {audio_path}")
            return audio_path
        else:
            logging.warning(f"ffmpeg did not produce audio file for '{query}', trying next clip if any")
            continue

    logging.warning(f"No Pexels video with audio found for query '{query}'")
    return None


def populate_media_if_needed():
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
                if os.listdir(BG_VIDEOS_DIR):
                    break
            except Exception as e:
                logging.error(f"Error populating video for query '{q}': {e}")
    else:
        logging.info("Skipping video population (either folder non-empty/no FORCE_POPULATE, or no PIXABAY_API_KEY).")

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
                if os.listdir(BG_SOUNDS_DIR):
                    break
            except Exception as e:
                logging.error(f"Error populating sound for query '{q}': {e}")
    else:
        logging.info("Skipping sound population (either folder non-empty/no FORCE_POPULATE, or no PEXELS_API_KEY).")

# Optionally populate at import time if explicitly allowed
if os.environ.get("RUN_POPULATE_AT_IMPORT", "0") in ("1", "true", "yes"):
    populate_media_if_needed()


def pick_random_file(directory, exts):
    if not os.path.isdir(directory):
        logging.warning(f"Directory for random selection not found: {directory}")
        return None
    candidates = [
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if any(f.lower().endswith("." + e.lower()) for e in exts)
    ]
    if not candidates:
        logging.warning(f"No files with extensions {exts} in {directory}")
        return None
    choice = random.choice(candidates)
    logging.info(f"Randomly selected: {choice}")
    return choice


def pre_extract_frames(video_src, output_dir, src_fps=30, tgt_fps=15):
    if not os.path.exists(video_src):
        logging.warning(f"Video for pre-extraction not found: {video_src}")
        return False
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    tmp = tempfile.mkdtemp(prefix="preextract_")
    try:
        pattern = os.path.join(tmp, "frame%05d.png")
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", video_src, "-vf", f"fps={src_fps}", pattern
        ]
        logging.info(f"Pre-extracting frames: {' '.join(cmd)}")
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
        try:
            shutil.rmtree(tmp)
        except Exception:
            pass


def prepare_random_background_and_sound():
    vid = pick_random_file(BG_VIDEOS_DIR, ["mp4", "mov", "mkv", "avi"])
    if vid:
        if os.path.exists(EXPECTED_VIDEO):
            try:
                os.remove(EXPECTED_VIDEO)
            except Exception:
                pass
        try:
            os.symlink(os.path.abspath(vid), EXPECTED_VIDEO)
            logging.info(f"Symlinked {EXPECTED_VIDEO} -> {vid}")
        except Exception:
            shutil.copy(vid, EXPECTED_VIDEO)
            logging.info(f"Copied {vid} to {EXPECTED_VIDEO}")
        pre_extract_frames(EXPECTED_VIDEO, FRAMES_DIR, src_fps=30, tgt_fps=15)
    else:
        logging.warning("No background video chosen; extract_video_frames will run normally.")

    snd = pick_random_file(BG_SOUNDS_DIR, ["mp3", "ogg", "wav"])
    if snd:
        if os.path.exists(EXPECTED_SOUND):
            try:
                os.remove(EXPECTED_SOUND)
            except Exception:
                pass
        try:
            os.symlink(os.path.abspath(snd), EXPECTED_SOUND)
            logging.info(f"Symlinked {EXPECTED_SOUND} -> {snd}")
        except Exception:
            shutil.copy(snd, EXPECTED_SOUND)
            logging.info(f"Copied {snd} to {EXPECTED_SOUND}")
    else:
        logging.warning("No background sound chosen; loop_sound will create a silent fallback when needed.")

# Run preparation only if explicit env var set (safer)
if os.environ.get("RUN_PREPARE_AT_IMPORT", "0") in ("1", "true", "yes"):
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
    result = {"quote": "No quote found", "author": "Unknown"}
    quote_data = result
    return result


def _create_silent_audio(duration_seconds, out_path="voiceover.mp3"):
    """Create a silent mp3 file of duration_seconds using pydub (used as a safe fallback)."""
    ms = int(duration_seconds * 1000)
    silent = AudioSegment.silent(duration=ms)
    silent.export(out_path, format="mp3")
    return out_path


def fetch_voiceover(quote, api_key, fallback_silent_duration=5):
    """Fetches voiceover for the given quote using VoiceRSS API (and caches per-quote).
    Important: pass the raw quote text without manual extra quotes (TTS engines may treat them differently).
    """
    global voiceover_file, _voiceover_cached_quote

    # If exact same quote already fetched and file exists, reuse
    if _voiceover_cached_quote == quote and voiceover_file and os.path.exists(voiceover_file):
        logging.info(f"Reusing cached voiceover for the same quote: {voiceover_file}")
        return voiceover_file

    # Clean up previous cached file if present
    if voiceover_file and os.path.exists(voiceover_file):
        try:
            os.remove(voiceover_file)
            logging.info("Removed previous cached voiceover file")
        except Exception as e:
            logging.warning(f"Could not remove old cached voiceover: {e}")
    if os.path.exists("voiceover.mp3") and _voiceover_cached_quote != quote:
        try:
            os.remove("voiceover.mp3")
            logging.info("Removed existing voiceover.mp3 on disk since quote changed")
        except Exception:
            pass

    voiceover_file = None
    _voiceover_cached_quote = None

    # If no API key for VoiceRSS, create a silent fallback audio
    if not api_key:
        logging.warning("VOICE_RSS_API_KEY not set; creating a silent fallback voiceover.")
        out = _create_silent_audio(fallback_silent_duration, out_path="voiceover.mp3")
        voiceover_file = out
        _voiceover_cached_quote = quote
        return voiceover_file

    # Use VoiceRSS API
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
        response = requests.get(url, params=params, timeout=15)
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
        # Fallback to a short silent audio to avoid failures downstream
        out = _create_silent_audio(fallback_silent_duration, out_path="voiceover.mp3")
        voiceover_file = out
        _voiceover_cached_quote = quote
        return voiceover_file


def fetch_cat_image(api_key, target_width=1280, target_height=720):
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    CAT_IMAGE_PATH = os.path.join(BASE_DIR, CAT_IMAGE_FILENAME)

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
                img = img.convert("RGB")
                # Optionally resize preserving aspect ratio
                img.thumbnail((target_width, target_height), Image.LANCZOS)
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
    # Wrap the quote text for proper line breaks.
    wrapped_quote = "\n".join(textwrap.wrap(quote_text, width=40))

    quote_mobject = Paragraph(wrapped_quote, alignment="center", line_spacing=0.6)
    quote_mobject.set_color_by_gradient(WHITE, YELLOW)
    max_width = frame_width * 0.8
    max_height = frame_height * 0.5
    try:
        quote_mobject.set_width(min(quote_mobject.width, max_width))
        quote_mobject.set_height(min(quote_mobject.height, max_height))
    except Exception:
        # Some Manim builds may not expose .width/.height at creation time; ignore safely
        pass

    author_mobject = Text(f"- {quote_author}", font_size=24)
    author_mobject.set_color(YELLOW)

    return quote_mobject, author_mobject


def get_audio_duration(audio_file):
    """Returns the duration (in seconds) of the given audio file using pydub."""
    audio = AudioSegment.from_file(audio_file)
    duration_seconds = len(audio) / 1000.0
    return duration_seconds


def loop_sound(audio_file, target_duration):
    """
    Loops the given audio file until the target_duration (in seconds)
    is reached, then trims it to exactly target_duration.
    If the audio_file is missing, creates a silent filler instead.
    Returns the path to the resulting audio file.
    """
    if not audio_file or not os.path.exists(audio_file):
        logging.warning(f"loop_sound: audio_file missing ({audio_file}); creating silent filler")
        return _create_silent_audio(target_duration, out_path="looped_silent.mp3")
    try:
        audio = AudioSegment.from_file(audio_file)
    except Exception as e:
        logging.warning(f"Could not open audio '{audio_file}': {e}; creating silent filler")
        return _create_silent_audio(target_duration, out_path="looped_silent.mp3")

    original_duration = len(audio) / 1000.0
    if original_duration <= 0:
        logging.warning(f"Original audio has zero length: {audio_file}")
        return _create_silent_audio(target_duration, out_path="looped_silent.mp3")
    loops_needed = int(target_duration / original_duration) + 1
    full_audio = audio * loops_needed
    trimmed_audio = full_audio[: int(target_duration * 1000)]
    basename = os.path.basename(audio_file).split('.')[0]
    looped_path = "looped_" + basename + ".mp3"
    try:
        trimmed_audio.export(looped_path, format="mp3")
    except Exception as e:
        logging.error(f"Failed to export looped audio {looped_path}: {e}")
        return _create_silent_audio(target_duration, out_path="looped_silent.mp3")
    return looped_path


def trim_audio(audio_file, max_duration=30):
    try:
        audio = AudioSegment.from_file(audio_file)
    except Exception as e:
        logging.warning(f"trim_audio: failed to open '{audio_file}': {e}; creating silent placeholder")
        return _create_silent_audio(min(max_duration, 5), out_path="trimmed_silent.mp3")
    trimmed_audio = audio[: max_duration * 1000]
    trimmed_path = "trimmed_" + os.path.basename(audio_file)
    try:
        trimmed_audio.export(trimmed_path, format="mp3")
    except Exception as e:
        logging.error(f"Failed to export trimmed audio {trimmed_path}: {e}")
        return _create_silent_audio(min(max_duration, 5), out_path="trimmed_silent.mp3")
    return trimmed_path


def extract_video_frames(video_file, fps=30):
    output_dir = FRAMES_DIR
    os.makedirs(output_dir, exist_ok=True)

    existing = [f for f in os.listdir(output_dir) if f.endswith(".png")]
    if existing:
        frame_files = [os.path.join(output_dir, f) for f in sorted(existing)]
        logging.info(f"Using pre-extracted {len(frame_files)} frames from {output_dir}")
        return frame_files

    if not os.path.exists(video_file):
        logging.warning(f"extract_video_frames: video file not found: {video_file}")
        return []

    frame_pattern = os.path.join(output_dir, "frame%03d.png")
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", video_file, "-vf", f"fps={fps}", frame_pattern]
    proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        logging.error(f"ffmpeg failed to extract frames: {proc.stderr}")
        return []
    frame_files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.endswith(".png")]
    return sorted(frame_files)


class AnimatedQuoteWithBackground(Scene):
    def construct(self):
        # Set total duration of the scene (in seconds)
        total_duration = 7

        # Ensure a background sound exists or create a silent fallback.
        cool_effect_file = EXPECTED_SOUND if os.path.exists(EXPECTED_SOUND) else None
        looped_effect = loop_sound(cool_effect_file, total_duration)
        self.add_sound(looped_effect, gain=-5)

        # Extract video frames from background video
        video_background_file = EXPECTED_VIDEO if os.path.exists(EXPECTED_VIDEO) else None
        video_frames = extract_video_frames(video_background_file, fps=30) if video_background_file else []

        # Choose a subset of frames for a few transitions
        desired_transitions = int(total_duration // 2)
        frame_interval = max(1, len(video_frames) // max(1, desired_transitions)) if video_frames else 1
        selected_frames = video_frames[::frame_interval] if video_frames else []

        # Create initial background image from the first selected frame.
        bg_image = None
        if selected_frames:
            bg_image = ImageMobject(selected_frames[0])
            # Fit background to camera frame while preserving aspect
            try:
                bg_image.set_height(self.camera.frame_height + 0.5)
            except Exception:
                bg_image.scale(4)
            self.add(bg_image)

        # Fetch quote
        quote_info = fetch_quote()
        # For TTS use the raw quote text (avoid adding extra quotation marks which may be removed or cause issues)
        raw_quote_text = quote_info['quote']
        display_quote_text = f"\"{raw_quote_text}\""
        quote_author = f"{quote_info['author']}"

        # Create quote text objects
        quote_mobject, author_mobject = create_quote_mobjects(
            display_quote_text, quote_author, self.camera.frame_width, self.camera.frame_height
        )
        quote_mobject.move_to(UP * 0.5)
        author_mobject.next_to(quote_mobject, DOWN, buff=0.4)

        # Fetch and trim voiceover BEFORE animating text, so both play concurrently.
        # Pass raw_quote_text (without the surrounding quotes) to TTS.
        audio_file = fetch_voiceover(raw_quote_text, voice_api_key)
        if audio_file:
            audio_file = trim_audio(audio_file, max_duration=total_duration)
            try:
                voiceover_duration = get_audio_duration(audio_file)
            except Exception:
                voiceover_duration = 0
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
            new_bg = ImageMobject(frame)
            try:
                new_bg.set_height(self.camera.frame_height + 0.5)
            except Exception:
                new_bg.scale(4)
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


if __name__ == '__main__':
    # Quick local sanity run: prepare assets only if explicitly requested by env var
    if os.environ.get("RUN_PREPARE_AT_IMPORT", "0") in ("1", "true", "yes"):
        prepare_random_background_and_sound()
    # Note: Run manim via CLI to render this scene, e.g.:
    # manim -pql AnimatedQuoteWithBackground_fixed.py AnimatedQuoteWithBackground
    pass
