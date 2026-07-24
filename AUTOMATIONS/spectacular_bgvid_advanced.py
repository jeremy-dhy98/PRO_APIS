from manim import *
from manim import config
import requests
import logging
import os
import time
from io import BytesIO
from PIL import Image
import textwrap
from pydub import AudioSegment
import subprocess
import json
import random  
import tempfile  
import shutil
import imageio_ffmpeg

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load API keys from environment variables safely stripping hidden characters
cat_api_key = os.environ.get("CAT_API_KEY", "").strip() or None
voice_api_key = os.environ.get("VOICE_RSS_API_KEY", "").strip() or None
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "").strip() or None
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "").strip() or None

# Global variables
quote_data = None
voiceover_file = None
_voiceover_cached_quote = None

# ==========================================================
# PATH RESOLUTIONS & PERFORMANCE ENVIRONMENT CONFIGURATION
# ==========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Target directory updated for Botanical Illustrations
NATURE_DIR = r"C:\Users\Jeremy\Desktop\Nature"
NATURE_HISTORY_FILE = os.path.join(NATURE_DIR, "downloaded_images.json")

# Default filenames
VIDEO_FILENAME = "46026-447087782_medium.mp4"
SOUND_FILENAME = "subclip.ogg"

VIDEO_PATH = os.path.join(BASE_DIR, VIDEO_FILENAME)
SOUND_PATH = os.path.join(BASE_DIR, SOUND_FILENAME)

# Frames directory and metadata file
FRAMES_DIR = os.path.join(BASE_DIR, "video_frames")
METADATA_PATH = os.path.join(FRAMES_DIR, "frames_meta.json")

# Explicit media directories
BG_VIDEOS_DIR = os.path.join(BASE_DIR, "bg_videos")
BG_SOUNDS_DIR = os.path.join(BASE_DIR, "bg_sounds")

# Ensure directories exist
os.makedirs(BG_VIDEOS_DIR, exist_ok=True)
os.makedirs(BG_SOUNDS_DIR, exist_ok=True)
os.makedirs(FRAMES_DIR, exist_ok=True)
os.makedirs(NATURE_DIR, exist_ok=True)

# ─── CRITICAL WINDOWS FFmpeg & FFPROBE PATH RESOLUTION ───
try:
    FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
    FFMPEG_DIR = os.path.dirname(FFMPEG_EXE)
    
    os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")
    os.environ["IMAGEIO_FFMPEG_EXE"] = FFMPEG_EXE
    
    AudioSegment.converter = FFMPEG_EXE
    
    ffprobe_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    FFPROBE_EXE = os.path.join(FFMPEG_DIR, ffprobe_name)
    
    if os.path.exists(FFPROBE_EXE):
        AudioSegment.ffprobe = FFPROBE_EXE
        logging.info(f"Using FFmpeg and FFprobe binaries via imageio: {FFMPEG_DIR}")
    else:
        AudioSegment.ffprobe = FFMPEG_EXE
        logging.warning("FFmpeg binary found, but specific ffprobe name was missing. Falling back to primary executable pointer.")
except Exception as e:
    FFMPEG_EXE = None
    logging.warning(f"Could not automatically configure dynamic FFmpeg variables via imageio-ffmpeg: {e}")


def _create_silent_audio(duration_seconds, out_path):
    """Create a silent mp3 file for fallback use."""
    try:
        duration_seconds = float(duration_seconds)
    except Exception:
        duration_seconds = 4.0
    duration_seconds = max(0.5, duration_seconds)
    ms = int(duration_seconds * 1000)
    silent = AudioSegment.silent(duration=ms)
    silent.export(out_path, format="mp3")
    return out_path

def load_frames_metadata():
    """CACHING DISABLED: always return None"""
    return None

def save_frames_metadata(video_path, mtime):
    """Save metadata about extracted frames."""
    data = {"video_path": video_path, "mtime": mtime}
    try:
        os.makedirs(os.path.dirname(METADATA_PATH), exist_ok=True)
        with open(METADATA_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        logging.warning(f"Could not write frames metadata: {e}")

def extract_video_frames(video_file, fps=30):
    """Extracts frames from the given video file using FFmpeg via subprocess."""
    output_dir = FRAMES_DIR
    os.makedirs(output_dir, exist_ok=True)

    if not FFMPEG_EXE:
        logging.warning("FFmpeg executable not configured; cannot extract frames.")
        return []

    try:
        video_mtime = os.path.getmtime(video_file)
    except Exception:
        video_mtime = None

    try:
        if os.path.exists(METADATA_PATH):
            os.remove(METADATA_PATH)
    except Exception:
        pass

    for fname in os.listdir(output_dir):
        if fname.endswith(".png"):
            try:
                os.remove(os.path.join(output_dir, fname))
            except Exception:
                pass
                
    frame_pattern = os.path.join(output_dir, "frame%03d.png")
    command = [FFMPEG_EXE, "-y", "-i", video_file, "-vf", f"fps={fps}", frame_pattern]
    logging.info(f"Extracting frames from video via ffmpeg: fps={fps}")
    try:
        subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    except Exception as e:
        logging.warning(f"ffmpeg extraction failed: {e}")
        return []

    frame_files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.endswith(".png")]
    frame_files = sorted(frame_files)
    if frame_files:
        if video_mtime is not None:
            save_frames_metadata(os.path.abspath(video_file), video_mtime)
        logging.info(f"Extracted and cached {len(frame_files)} frames.")
    else:
        logging.warning("No frames extracted; check video file base dimensions.")
    return frame_files

def get_audio_duration(audio_file):
    """Returns the duration (in seconds) of the given audio file using pydub."""
    if not os.path.exists(audio_file):
        logging.warning(f"get_audio_duration: file not found: {audio_file}")
        return None
    try:
        audio = AudioSegment.from_file(audio_file)
        return len(audio) / 1000.0
    except Exception as e:
        logging.warning(f"Could not read audio duration parameters for {audio_file}: {e}")
        return None

def loop_sound(audio_file, target_duration):
    """Loops the given audio file until the target_duration is reached, then trims it."""
    if not audio_file or not os.path.exists(audio_file):
        logging.warning(f"loop_sound: input audio file does not exist: {audio_file}")
        return _create_silent_audio(target_duration, out_path=os.path.join(BASE_DIR, "looped_effect.mp3"))

    base, ext = os.path.splitext(os.path.basename(audio_file))
    looped_name = f"looped_{base}_{int(target_duration)}s.mp3"
    looped_path = os.path.join(BASE_DIR, looped_name)

    if os.path.exists(looped_path):
        try:
            os.remove(looped_path)
            logging.info(f"Removed stale looped audio: {looped_name}")
        except Exception:
            pass

    try:
        audio = AudioSegment.from_file(audio_file)
    except Exception as e:
        logging.error(f"Error loading audio file {audio_file}: {e}")
        return _create_silent_audio(target_duration, out_path=looped_path)

    original_duration = len(audio) / 1000.0
    if original_duration <= 0:
        logging.warning(f"Original audio has zero length string properties: {audio_file}")
        return _create_silent_audio(target_duration, out_path=looped_path)
        
    loops_needed = int(target_duration / original_duration) + 1
    full_audio = audio * loops_needed  
    trimmed_audio = full_audio[:int(target_duration * 1000)]
    try:
        trimmed_audio.export(looped_path, format="mp3")
        logging.info(f"Created looped audio output asset: {looped_name}")
        return looped_path
    except Exception as e:
        logging.error(f"Failed exporting looped audio segment: {e}")
        return _create_silent_audio(target_duration, out_path=looped_path)

def trim_audio(audio_file, max_duration=30):
    """Trims the given audio file to a maximum duration (in seconds)."""
    if not os.path.exists(audio_file):
        logging.warning(f"trim_audio: input audio file does not exist: {audio_file}")
        return None

    base, ext = os.path.splitext(os.path.basename(audio_file))
    trimmed_name = f"trimmed_{base}_{int(max_duration)}s.mp3"
    trimmed_path = os.path.join(BASE_DIR, trimmed_name)

    if os.path.exists(trimmed_path):
        try:
            os.remove(trimmed_path)
            logging.info(f"Removed stale trimmed audio asset configuration: {trimmed_name}")
        except Exception:
            pass

    try:
        audio = AudioSegment.from_file(audio_file)
    except Exception as e:
        logging.error(f"Error loading audio file properties {audio_file}: {e}")
        return _create_silent_audio(max_duration, out_path=trimmed_path)
        
    trimmed_audio = audio[:int(max_duration * 1000)]  
    try:
        trimmed_audio.export(trimmed_path, format="mp3")
        logging.info(f"Created trimmed audio configuration: {trimmed_name}")
        return trimmed_path
    except Exception as e:
        logging.error(f"Failed exporting trimmed audio file structure: {e}")
        return _create_silent_audio(max_duration, out_path=trimmed_path)

def fetch_quote(max_attempts=3, timeout=8):
    global quote_data
    url = "https://zenquotes.io/api/random"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    local_fallbacks = [
        {"quote": "The only way to do great work is to love what you do.", "author": "Steve Jobs"},
        {"quote": "Code is like humor. When you have to explain it, it’s bad.", "author": "Cory House"},
        {"quote": "Simplicity is the soul of efficiency.", "author": "Austin Freeman"},
        {"quote": "Before software can be reusable it first has to be usable.", "author": "Ralph Johnson"},
        {"quote": "Make it work, make it right, make it fast.", "author": "Kent Beck"}
    ]

    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()

            try:
                data = resp.json()
            except ValueError as e:
                raise RuntimeError(f"Invalid JSON response sequence from target API endpoint: {e}") from e

            if isinstance(data, list) and data:
                item = data[0] or {}
                quote_data = {
                    "quote": item.get("q", "No quote found").strip(),
                    "author": item.get("a", "Unknown").strip(),
                }
                logging.info(f"Successfully fetched server side quote contents: {quote_data}")
                return quote_data

            raise RuntimeError("Quote API returned unexpected format structural type data layers.")

        except requests.HTTPError as e:
            status = getattr(e.response, "status_code", None)
            body = ""
            if e.response is not None:
                try:
                    body = e.response.text[:150]
                except Exception:
                    pass
            logging.error(f"fetch_quote HTTP error framework on attempt {attempt}/{max_attempts}: {status} {body}")
            if status == 429 or (status is not None and 500 <= status < 600):
                wait = (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                time.sleep(wait)
                continue
            break
        except (requests.Timeout, requests.ConnectionError, requests.RequestException) as e:
            logging.error(f"fetch_quote network tracking request timeout error on attempt {attempt}/{max_attempts}: {e}")
            if attempt < max_attempts:
                wait = (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                time.sleep(wait)
                continue
            break
        except Exception as e:
            logging.error(f"Unexpected system tracking exception catch inside fetch_quote loop: {e}")
            break

    result = random.choice(local_fallbacks)
    quote_data = result
    logging.info(f"Using high quality local backup quote module: {quote_data}")
    return result

def fetch_voiceover(quote, api_key):
    """Fetches voiceover for the given quote using VoiceRSS API."""
    global voiceover_file, _voiceover_cached_quote

    if voiceover_file and os.path.exists(voiceover_file):
        try:
            os.remove(voiceover_file)
        except Exception as e:
            logging.warning(f"Could not clear target location voiceover: {e}")
            
    if os.path.exists("voiceover.mp3"):
        try:
            os.remove("voiceover.mp3")
        except Exception:
            pass

    voiceover_file = None
    _voiceover_cached_quote = None

    if not api_key:
        logging.warning("VOICE_RSS_API_KEY environment lookup failed; routing silent audio matrix structure.")
        out = _create_silent_audio(4, out_path="voiceover.mp3")
        voiceover_file = out
        _voiceover_cached_quote = quote
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
        response = requests.get(url, params=params, timeout=12)
        response.raise_for_status()
        ct = response.headers.get("Content-Type", "")
        if "audio" not in ct.lower() and not response.content.startswith(b"ID3"):
            logging.error("TTS endpoint engine returned non-audio body headers; dropping payload.")
            out = _create_silent_audio(4, out_path="voiceover.mp3")
            voiceover_file = out
            _voiceover_cached_quote = quote
            return voiceover_file
            
        if len(response.content) < 1000:
            logging.warning("TTS system returned broken package length; applying safe silent container setup.")
            out = _create_silent_audio(4, out_path="voiceover.mp3")
            voiceover_file = out
            _voiceover_cached_quote = quote
            return voiceover_file
            
        file_path = "voiceover.mp3"
        with open(file_path, "wb") as f:
            f.write(response.content)
        logging.info(f"Downloaded new voiceover asset cleanly to location: {file_path}")
        voiceover_file = file_path
        _voiceover_cached_quote = quote
        return voiceover_file
    except Exception as e:
        logging.error(f"Error fetching/saving automation audio voiceover modules: {e}")
        
    out = _create_silent_audio(4, out_path="voiceover.mp3")
    voiceover_file = out
    _voiceover_cached_quote = quote
    return voiceover_file

def create_quote_mobjects(quote_text, quote_author, frame_width, frame_height):
    """Creates properly formatted text layout components for Manim render matrix configurations."""
    wrapped_quote = "\n".join(textwrap.wrap(quote_text, width=40))
    
    quote_mobject = Paragraph(wrapped_quote, alignment="center", line_spacing=0.6)
    quote_mobject.set_color_by_gradient(WHITE, YELLOW)
    
    max_width = frame_width * 0.8  
    max_height = frame_height * 0.5  
    quote_mobject.set_width(min(quote_mobject.width, max_width))
    quote_mobject.set_height(min(quote_mobject.height, max_height))
    
    author_mobject = Text(f"- {quote_author}", font_size=24)
    author_mobject.set_color(YELLOW)
    
    return quote_mobject, author_mobject

def _download_stream_to(path, url, headers=None, timeout=30):
    """Stream a URL to a temp file and atomically rename on success."""
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
        return True
    except Exception as e:
        logging.warning(f"Download stream pipeline mapping failed for target {url}: {e}")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False

# ==========================================================
# ENHANCED FEATURE: FETCH BOTANICAL ILLUSTRATIONS 
# Includes Fix for "No unique candidate" Error
# ==========================================================
def _load_downloaded_image_history():
    """Reads previously saved image IDs to guarantee unique downloads on every run."""
    if os.path.exists(NATURE_HISTORY_FILE):
        try:
            with open(NATURE_HISTORY_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            logging.warning(f"Failed loading downloaded image history log: {e}")
    return set()

def _save_downloaded_image_history(history_set):
    """Saves updated download history log."""
    try:
        with open(NATURE_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(list(history_set), f, indent=2)
    except Exception as e:
        logging.warning(f"Failed writing image history log: {e}")

def fetch_and_save_hd_images(target_count=5):
    """
    Fetches `target_count` unique Botanical Illustrations from Pexels or Pixabay.
    Includes safeguards against API history exhaustion.
    """
    logging.info(f"Initiating Botanical Image Fetcher (Target: {target_count} -> {NATURE_DIR})")
    os.makedirs(NATURE_DIR, exist_ok=True)
    
    history = _load_downloaded_image_history()
    raw_candidates = []
    
    # Extensive Botanical Queries to prevent history exhaustion
    queries = [
        "botanical vector", "flower pattern", 
        "abstract leaves", "floral background", 
        "nature background", 
        "boho floral", "watercolor background"
    ]
    query = random.choice(queries)
    random_page = random.randint(1, 10)

    # 1. Query Pexels Photos API
    if PEXELS_API_KEY:
        url = "https://api.pexels.com/v1/search"
        headers = {"Authorization": PEXELS_API_KEY}
        params = {"query": query, "per_page": 40, "page": random_page, "orientation": "landscape"}
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            if resp.status_code == 200:
                photos = resp.json().get("photos", [])
                for p in photos:
                    img_id = f"pexels_img_{p['id']}"
                    src = p.get("src", {})
                    img_url = src.get("large2x") or src.get("original")
                    if img_url:
                        raw_candidates.append((img_id, img_url))
        except Exception as e:
            logging.warning(f"Failed fetching photos from Pexels: {e}")

    # 2. Query Pixabay Images API (Set to Illustration/Vector exclusively)
    if PIXABAY_API_KEY:
        url = "https://pixabay.com/api/"
        params = {
            "key": PIXABAY_API_KEY,
            "q": query,
            "image_type": "illustration", # Explicitly request artwork instead of realistic photos
            "orientation": "horizontal",
            "min_width": 1920,
            "per_page": 40,
            "page": random_page
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                hits = resp.json().get("hits", [])
                for h in hits:
                    img_id = f"pixabay_img_{h['id']}"
                    img_url = h.get("largeImageURL") or h.get("fullHDURL") or h.get("imageURL")
                    if img_url:
                        raw_candidates.append((img_id, img_url))
        except Exception as e:
            logging.warning(f"Failed fetching photos from Pixabay: {e}")

    # FIX FOR THE WARNING: Check if API actually returned data
    if not raw_candidates:
        logging.error("APIs returned ZERO images. Your API keys may be invalid or you have hit a rate limit.")
        return 0

    # Filter candidates against history log
    candidates = [c for c in raw_candidates if c[0] not in history]

    # FIX FOR THE WARNING: If history blocked all new images, reset history rather than failing
    if not candidates and raw_candidates:
        logging.warning("All fetched images were already in history! Clearing history to prevent exhaustion.")
        history.clear()
        candidates = raw_candidates

    random.shuffle(candidates)
    saved_count = 0

    for img_id, img_url in candidates:
        if saved_count >= target_count:
            break

        timestamp = int(time.time())
        filename = f"{img_id}_{timestamp}.jpg"
        filepath = os.path.join(NATURE_DIR, filename)

        logging.info(f"Downloading Botanical Illustration ({saved_count + 1}/{target_count}): {img_url}")
        if _download_stream_to(filepath, img_url):
            history.add(img_id)
            saved_count += 1

    _save_downloaded_image_history(history)
    logging.info(f"Done! Successfully saved {saved_count} new unique illustrations to: {NATURE_DIR}")
    return saved_count

# Categories list 
NATURE_CATEGORIES = [
    "nature", "landscape", "mountains", "forest", 
    "waterfall", "ocean", "wildlife", "sunset", "sky"
]

def fetch_nature_video(
    target_dir: str = r"C:\Users\Jeremy\Desktop\Nature",
    min_duration: int = 45,
    max_duration: int = 90,
    max_attempts: int = 10
) -> str | None:
    """
    Fetches a single video matching nature categories with a duration between
    45s and 90s, saving it to the specified target media directory.
    
    Returns the file path of the downloaded video, or None if download fails.
    """
    os.makedirs(target_dir, exist_ok=True)
    logging.info(f"Searching for a video ({min_duration}s–{max_duration}s) in {target_dir}...")

    # Shuffle categories to keep downloads diverse across runs
    shuffled_queries = NATURE_CATEGORIES.copy()
    random.shuffle(shuffled_queries)

    # ------------------------------------------------------------------
    # Strategy 1: Pexels Video API Search
    # ------------------------------------------------------------------
    if PEXELS_API_KEY:
        for query in shuffled_queries[:max_attempts]:
            page_num = random.randint(1, 5)
            url = "https://api.pexels.com/videos/search"
            headers = {"Authorization": PEXELS_API_KEY}
            params = {
                "query": query,
                "per_page": 20,
                "page": page_num,
                "orientation": "portrait"  # Ideal for IG Reels/FB Stories; change or remove if landscape preferred
            }

            try:
                resp = requests.get(url, headers=headers, params=params, timeout=12)
                resp.raise_for_status()
                videos = resp.json().get("videos", [])
                random.shuffle(videos)

                for vid in videos:
                    duration = vid.get("duration", 0)
                    
                    # Strictly enforce duration window (45s to 90s)
                    if min_duration <= duration <= max_duration:
                        video_files = vid.get("video_files", [])
                        
                        # Select highest quality MP4 link (preferably HD 1080p or 720p)
                        best_file = next(
                            (vf for vf in video_files if vf.get("quality") == "hd" and vf.get("file_type") == "video/mp4"),
                            video_files[0] if video_files else None
                        )

                        if best_file and best_file.get("link"):
                            download_url = best_file["link"]
                            filename = f"pexels_{query}_{int(time.time())}_{random.randint(1000, 9999)}.mp4"
                            filepath = os.path.join(target_dir, filename)

                            logging.info(f"Found Pexels video ('{query}', {duration}s). Downloading to {filepath}...")
                            
                            if _download_stream_to(filepath, download_url, headers=headers):
                                return filepath

            except Exception as e:
                logging.warning(f"Pexels video fetch attempt for query '{query}' failed: {e}")

    # ------------------------------------------------------------------
    # Strategy 2: Pixabay Video API Fallback
    # ------------------------------------------------------------------
    if PIXABAY_API_KEY:
        for query in shuffled_queries[:max_attempts]:
            url = "https://pixabay.com/api/videos/"
            params = {
                "key": PIXABAY_API_KEY,
                "q": query,
                "per_page": 20,
                "page": random.randint(1, 3)
            }

            try:
                resp = requests.get(url, params=params, timeout=12)
                resp.raise_for_status()
                hits = resp.json().get("hits", [])
                random.shuffle(hits)

                for hit in hits:
                    duration = hit.get("duration", 0)
                    
                    # Strictly enforce duration window (45s to 90s)
                    if min_duration <= duration <= max_duration:
                        videos_data = hit.get("videos", {})
                        # Prefer large/medium MP4 URL
                        video_info = videos_data.get("large") or videos_data.get("medium") or videos_data.get("small")
                        
                        if video_info and video_info.get("url"):
                            download_url = video_info["url"]
                            filename = f"pixabay_{query}_{int(time.time())}_{random.randint(1000, 9999)}.mp4"
                            filepath = os.path.join(target_dir, filename)

                            logging.info(f"Found Pixabay video ('{query}', {duration}s). Downloading to {filepath}...")
                            
                            if _download_stream_to(filepath, download_url):
                                return filepath

            except Exception as e:
                logging.warning(f"Pixabay video fetch attempt for query '{query}' failed: {e}")

    logging.error(f"Failed to find any videos matching duration criteria ({min_duration}s–{max_duration}s).")
    return None


def fetch_pexels_video(query="nature", per_page=15):
    """Fetch a random short video from Pexels matching `query`."""
    if not PEXELS_API_KEY:
        logging.warning("PEXELS_API_KEY environment mapping missing; bypassing query configuration.")
        return None
    search_url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": PEXELS_API_KEY}
    params = {"query": query, "per_page": per_page, "page": 1}
    try:
        resp = requests.get(search_url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logging.warning(f"Pexels network query module search failed: {e}")
        return None

    videos = data.get("videos", [])
    if not videos:
        return None

    random.shuffle(videos)
    for choice in videos:
        video_files = choice.get("video_files", [])
        if not video_files:
            continue

        file_url = None
        for vf in video_files:
            q = vf.get("quality")
            if not isinstance(q, str):
                continue
            if q and "sd" in q.lower() and vf.get("link"):
                file_url = vf["link"]
                break
        if not file_url:
            candidates = [vf.get("link") for vf in video_files if vf.get("link")]
            if candidates:
                file_url = random.choice(candidates)
        if not file_url:
            continue

        local_filename = os.path.join(BASE_DIR, "pexels_bg.mp4")
        try:
            logging.info(f"Downloading background video configuration via Pexels server: {file_url}")
            success = _download_stream_to(local_filename, file_url, headers=headers)
            if success:
                return local_filename
        except Exception as e:
            logging.warning(f"Failed handling specific media data streams: {e}")
            continue
    return None

def fetch_pixabay_video(query="nature", per_page=20):
    """Fetch one video from Pixabay for `query` and save to local file."""
    if not PIXABAY_API_KEY:
        logging.info("PIXABAY_API_KEY environment target empty; passing engine setup sequence.")
        return None
    url = "https://pixabay.com/api/videos/"
    params = {"key": PIXABAY_API_KEY, "q": query, "per_page": per_page}
    try:
        resp = requests.get(url, params=params, timeout=12)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logging.warning(f"Pixabay server query modules search dropped: {e}")
        return None

    hits = data.get("hits", [])
    if not hits:
        return None

    random.shuffle(hits)
    for hit in hits:
        vids = hit.get("videos", {})
        file_url = None
        for size in ("medium", "large", "small", "tiny"):
            if vids.get(size) and vids[size].get("url"):
                file_url = vids[size]["url"]
                break
        if not file_url:
            continue
        local_filename = os.path.join(BASE_DIR, "pixabay_bg.mp4")
        logging.info(f"Pixabay download link resolved, capturing content streams: {file_url}")
        success = _download_stream_to(local_filename, file_url)
        if success and os.path.exists(local_filename):
            return local_filename
    return None

def fetch_background_video_for_topic(topic="nature"):
    logging.info(f"Attempting to fetch fresh background video for topic: '{topic}'")
    p = fetch_pexels_video(topic)
    if p:
        logging.info("Successfully fetched background source target using Pexels layer engines.")
        return p
    q = fetch_pixabay_video(topic)
    if q:
        logging.info("Successfully fetched background source target using Pixabay layer engines.")
        return q
    logging.warning("Could not gather online live video backgrounds mapping for item '%s'. Defaulting to local media assets storage." % topic)
    return None


class AnimatedQuoteWithBackground(Scene):
    def construct(self):
        total_duration = 7

        # ── Trigger 5 HD Botanical Image Download Enhancement ──
        try:
            fetch_and_save_hd_images(target_count=5)
            fetch_nature_video()
        except Exception as e:
            logging.warning(f"HD desktop image fetch step failed: {e}")

        def _remove_path_safe(path):
            try:
                if os.path.islink(path) or os.path.isfile(path):
                    os.remove(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path)
            except Exception:
                pass

        def _clear_media_dir(dirpath, preserve_names=()):
            if not os.path.isdir(dirpath):
                return
            for name in os.listdir(dirpath):
                if name in preserve_names:
                    logging.info(f"Preserving explicit module file target: {os.path.join(dirpath, name)}")
                    continue
                _remove_path_safe(os.path.join(dirpath, name))

        logging.info("Clearing previous background files & frames (inside designated media dirs only).")
        preserve_name = os.path.basename(SOUND_PATH)
        _clear_media_dir(BG_VIDEOS_DIR, preserve_names=())
        _clear_media_dir(BG_SOUNDS_DIR, preserve_names=(preserve_name,))
        _clear_media_dir(FRAMES_DIR, preserve_names=())

        for tmp_name in ("pexels_bg.mp4", "pixabay_bg.mp4"):
            tmp_path = os.path.join(BASE_DIR, tmp_name)
            if os.path.exists(tmp_path):
                _remove_path_safe(tmp_path)

        # Quote and Voiceover Logic
        quote_info = fetch_quote()
        raw = quote_info.get('quote', 'No quote found')
        display_q = f'"{raw}"'
        author = quote_info.get('author', 'Unknown')

        audio = fetch_voiceover(raw, voice_api_key)

        measured_voice_dur = None
        if audio and os.path.exists(audio):
            try:
                measured_voice_dur = AudioSegment.from_file(audio).duration_seconds
                logging.info(f"Measured voiceover duration tracking logic output: {measured_voice_dur:.2f}s")
            except Exception as e:
                logging.warning(f"Could not calculate precise tracking lengths directly from metadata: {e}")
                measured_voice_dur = None

        if measured_voice_dur and measured_voice_dur > 0:
            total_duration = float(measured_voice_dur) + 0.25
            if total_duration > 120:
                total_duration = 120.0
            logging.info(f"Scene total_duration set from voiceover file content specifications: {total_duration:.2f}s")
        else:
            logging.info(f"Using default total_duration matrix layout: {total_duration:.2f}s")

        if os.path.exists(SOUND_PATH):
            try:
                looped_effect = loop_sound(SOUND_PATH, total_duration)
                if looped_effect and os.path.exists(looped_effect):
                    self.add_sound(looped_effect, gain=-5)
            except Exception as e:
                logging.warning(f"Background sound loading pipeline failed on timeline integration step: {e}")
        else:
            logging.warning(f"Background ambient tracking sound module file not detected at pathway location: {SOUND_PATH}")

        # Fetch Background Video
        env_topic = os.environ.get("BG_QUERY", None)
        if env_topic:
            chosen_topic = env_topic.strip()
            logging.info(f"BG_QUERY parameter loaded explicitly via system env: '{chosen_topic}'")
        else:
            chosen_topic = random.choice(["nature", "birds", "art"])
            logging.info(f"No specific environment BG_QUERY parsed. Random fallback selection applied: '{chosen_topic}'")

        fetched_video = fetch_background_video_for_topic(chosen_topic)
        video_background_file = fetched_video if (fetched_video and os.path.exists(fetched_video)) else VIDEO_PATH

        # Break Media Into Constituent Images
        video_frames = extract_video_frames(video_background_file, fps=30)
        
        if not video_frames:
            logging.error("No background frames available. Scene will drop visual backdrop channels.")
            bg_pool = []
        else:
            bg_pool = [
                ImageMobject(img).scale_to_fit_width(config.frame_width) 
                for img in video_frames[:150] 
            ]

        if bg_pool:
            bg_container = bg_pool[0].copy()
            bg_container.set_z_index(-10) 
            self.add(bg_container) 

            def rapid_image_swap(mob, dt):
                swap_speed = 15  
                index = int((self.time * swap_speed) % len(bg_pool))
                mob.become(bg_pool[index])

            bg_container.add_updater(rapid_image_swap)

        # Mobjects setup
        q_mobj, a_mobj = create_quote_mobjects(display_q, author, self.camera.frame_width, self.camera.frame_height)
        q_mobj.move_to(UP * 0.5)
        a_mobj.next_to(q_mobj, DOWN, buff=0.4)

        # Render voice track layers onto processing tracks
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

        # Text Animations Timeline
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

        time_used = time_fadein + time_write + time_color + time_scale + time_author
        remaining_time = total_duration - time_used

        if remaining_time > 1e-6:
            self.wait(remaining_time)
        else:
            logging.info(f"Skipping wait layout block. Render steps fully match audio tracks (remaining={remaining_time})")

if __name__ == '__main__':
    if os.environ.get("AUTO_PREEXTRACT", "0") in ("1", "true", "yes"):
        if os.path.exists(VIDEO_PATH):
            extract_video_frames(VIDEO_PATH, fps=30)
    pass