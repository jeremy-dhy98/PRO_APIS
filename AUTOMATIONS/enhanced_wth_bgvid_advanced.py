import time
from manim import *
import requests
import logging
import os
import textwrap
import subprocess
import re
import wave
from pydub import AudioSegment
import random
import shutil
from PIL import Image
import imageio_ffmpeg

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load API keys from environment variables
cat_api_key = (os.environ.get("CAT_API_KEY") or "").strip()
voice_api_key = (os.environ.get("VOICE_RSS_API_KEY") or "").strip()
PIXABAY_API_KEY = (os.environ.get("PIXABAY_API_KEY") or "").strip()
PEXELS_API_KEY = (os.environ.get("PEXELS_API_KEY") or "").strip()

# Directories and filenames
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BG_VIDEOS_DIR = os.environ.get("BG_VIDEOS_DIR", os.path.join(BASE_DIR, "bg_videos"))
BG_SOUNDS_DIR = os.environ.get("BG_SOUNDS_DIR", os.path.join(BASE_DIR, "bg_sounds"))
FRAMES_DIR = os.path.join(BASE_DIR, "video_frames")
EXPECTED_VIDEO = os.path.normpath(os.path.join(BASE_DIR, "219305_tiny.mp4"))
EXPECTED_SOUND = os.path.normpath(os.path.abspath(os.path.join(BASE_DIR, "subclip.ogg")))
CAT_IMAGE_FILENAME = "cat_image.jpg"

# Target directory for the 5 new HD Nature images
NATURE_IMAGES_DIR = r"C:\Users\Jeremy\Desktop\Nature"

os.makedirs(BG_VIDEOS_DIR, exist_ok=True)
os.makedirs(BG_SOUNDS_DIR, exist_ok=True)
os.makedirs(FRAMES_DIR, exist_ok=True)

# Configure FFmpeg for pydub and subprocess use
try:
    FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
    os.environ["IMAGEIO_FFMPEG_EXE"] = FFMPEG_EXE
    os.environ["PATH"] = os.path.dirname(FFMPEG_EXE) + os.pathsep + os.environ.get("PATH", "")
    AudioSegment.converter = FFMPEG_EXE
    logging.info(f"Using FFmpeg binary: {FFMPEG_EXE}")
except Exception as e:
    FFMPEG_EXE = None
    logging.warning(f"Could not configure FFmpeg via imageio-ffmpeg: {e}")

TOPIC_CHOICES = ["nature", "birds", "art"]

quote_data = None
voiceover_file = None
_voiceover_cached_quote = None

def _write_silent_wav(duration_seconds, out_path):
    """Create a silent WAV file using only the standard library."""
    try:
        duration_seconds = max(0.5, float(duration_seconds))
    except Exception:
        duration_seconds = 0.5

    if not out_path.lower().endswith(".wav"):
        out_path = os.path.splitext(out_path)[0] + ".wav"

    sample_rate = 44100
    n_channels = 1
    sampwidth = 2  # 16-bit PCM
    n_frames = int(duration_seconds * sample_rate)
    silence = b"\x00\x00" * n_frames * n_channels

    with wave.open(out_path, "wb") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(silence)

    return out_path

def _download_stream_to(path, url, headers=None, timeout=30):
    tmp = path + ".part"
    try:
        with requests.get(url, stream=True, headers=(headers or {}), timeout=timeout) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
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

# =========================================================================
# NEW ENHANCEMENT: Fetch 5 unique HD Nature images per run
# =========================================================================
def fetch_hd_nature_images(target_dir=NATURE_IMAGES_DIR, num_images=10):
    """Fetches exactly 5 unique HD nature images from Pexels/Pixabay and saves them to the desktop."""
    os.makedirs(target_dir, exist_ok=True)
    logging.info(f"Fetching {num_images} new HD nature images into {target_dir}...")

    images_downloaded = 0
    # Mix up queries and pages to ensure total uniqueness every run
    queries = ["nature", "landscape", "mountains", "forest", "waterfall", "ocean", "wildlife", "sunset", "sky"]
    query = random.choice(queries)
    page_num = random.randint(1, 20) 

    # 1. Try Pexels Image API first
    if PEXELS_API_KEY:
        search_url = f"https://api.pexels.com/v1/search"
        headers = {"Authorization": PEXELS_API_KEY}
        params = {"query": query, "per_page": 15, "page": page_num}
        try:
            resp = requests.get(search_url, headers=headers, params=params, timeout=12)
            resp.raise_for_status()
            photos = resp.json().get("photos", [])
            random.shuffle(photos)
            
            for photo in photos:
                if images_downloaded >= num_images:
                    break
                # Prefer high-resolution images
                img_url = photo.get("src", {}).get("large2x") or photo.get("src", {}).get("original")
                if img_url:
                    unique_filename = f"pexels_nature_{int(time.time())}_{random.randint(1000,9999)}.jpg"
                    filepath = os.path.join(target_dir, unique_filename)
                    if _download_stream_to(filepath, img_url, headers=headers):
                        images_downloaded += 1
        except Exception as e:
            logging.warning(f"Pexels image search failed: {e}")

    # 2. Fallback to Pixabay if we still need more images
    if images_downloaded < num_images and PIXABAY_API_KEY:
        url = "https://pixabay.com/api/"
        params = {
            "key": PIXABAY_API_KEY,
            "q": query,
            "image_type": "photo",
            "orientation": "horizontal",
            "min_width": 1920,
            "page": random.randint(1, 10),
            "per_page": 20
        }
        try:
            resp = requests.get(url, params=params, timeout=12)
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
            random.shuffle(hits)

            for hit in hits:
                if images_downloaded >= num_images:
                    break
                img_url = hit.get("largeImageURL")
                if img_url:
                    unique_filename = f"pixabay_nature_{int(time.time())}_{random.randint(1000,9999)}.jpg"
                    filepath = os.path.join(target_dir, unique_filename)
                    if _download_stream_to(filepath, img_url):
                        images_downloaded += 1
        except Exception as e:
            logging.warning(f"Pixabay image search failed: {e}")

    if images_downloaded > 0:
        logging.info(f"Successfully saved {images_downloaded} unique HD images to {target_dir}")
    else:
        logging.warning("Could not fetch the HD nature images (Check your API keys/internet connection).")

# =========================================================================
# ENHANCEMENT: Fetch 5 unique Botanical Illustration/Vector images per run
# =========================================================================
def fetch_hd_nature_images2(target_dir=r"C:\Users\Jeremy\Desktop\Nature_Illustrations", num_images=5):
    """Fetches unique botanical/floral background illustrations and vectors from Pexels/Pixabay."""
    os.makedirs(target_dir, exist_ok=True)
    logging.info(f"Fetching {num_images} new background illustrations into {target_dir}...")

    images_downloaded = 0
    # Queries targeted specifically at floral/botanical background designs
    queries = [
        "background", "floral background", "botanical background", 
        "flower background", "nature background", "abstract background"
    ]
    query = random.choice(queries)
    page_num = random.randint(1, 10) 

    # Try Pexels Image API first
    if PEXELS_API_KEY:
        search_url = f"https://api.pexels.com/v1/search"
        headers = {"Authorization": PEXELS_API_KEY}
        params = {"query": f"{query} illustration", "per_page": 15, "page": page_num}
        try:
            resp = requests.get(search_url, headers=headers, params=params, timeout=12)
            resp.raise_for_status()
            photos = resp.json().get("photos", [])
            random.shuffle(photos)
            
            for photo in photos:
                if images_downloaded >= num_images:
                    break
                img_url = photo.get("src", {}).get("large2x") or photo.get("src", {}).get("original")
                if img_url:
                    unique_filename = f"pexels_floral_{int(time.time())}_{random.randint(1000,9999)}.jpg"
                    filepath = os.path.join(target_dir, unique_filename)
                    if _download_stream_to(filepath, img_url, headers=headers):
                        images_downloaded += 1
        except Exception as e:
            logging.warning(f"Pexels image search failed: {e}")

    # Pixabay API Search (Matches pixabay.com/illustrations/search/background/ and pixabay.com/vectors/search/background/)
    if images_downloaded < num_images and PIXABAY_API_KEY:
        # Dynamically toggle between 'illustration' and 'vector' image types
        image_type = random.choice(["illustration", "vector"])
        url = "https://pixabay.com/api/"
        params = {
            "key": PIXABAY_API_KEY,
            "q": query,
            "image_type": image_type,  # 'illustration' or 'vector'
            "orientation": "horizontal",
            "min_width": 1920,
            "page": random.randint(1, 5),
            "per_page": 20
        }
        try:
            logging.info(f"Querying Pixabay API (q='{query}', image_type='{image_type}')...")
            resp = requests.get(url, params=params, timeout=12)
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
            random.shuffle(hits)

            for hit in hits:
                if images_downloaded >= num_images:
                    break
                img_url = hit.get("largeImageURL")
                if img_url:
                    unique_filename = f"pixabay_{image_type}_{int(time.time())}_{random.randint(1000,9999)}.jpg"
                    filepath = os.path.join(target_dir, unique_filename)
                    if _download_stream_to(filepath, img_url):
                        images_downloaded += 1
        except Exception as e:
            logging.warning(f"Pixabay image search failed: {e}")

    if images_downloaded > 0:
        logging.info(f"Successfully saved {images_downloaded} unique illustrations to {target_dir}")
    else:
        logging.warning("Could not fetch the illustrations (Check your API keys/internet connection).")
        
# =========================================================================

def fetch_pexels_video(query="nature", per_page=15):
    if not PEXELS_API_KEY:
        logging.info("PEXELS_API_KEY not set; skipping Pexels fetch.")
        return None
    search_url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": PEXELS_API_KEY}
    params = {"query": query, "per_page": per_page, "page": 1}
    try:
        resp = requests.get(search_url, headers=headers, params=params, timeout=12)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logging.warning(f"Pexels search failed: {e}")
        return None

    videos = data.get("videos", [])
    if not videos:
        logging.info("Pexels search returned no videos.")
        return None

    random.shuffle(videos)
    for choice in videos:
        video_files = choice.get("video_files", [])
        if not video_files:
            continue

        file_url = None
        for vf in video_files:
            quality = vf.get("quality")
            q = quality.lower() if isinstance(quality, str) else ""

            if q in ("sd", "sd720", "sd_720", "small") and vf.get("link"):
                file_url = vf["link"]
                break
        if not file_url:
            candidates = [vf.get("link") for vf in video_files if vf.get("link")]
            if candidates:
                file_url = random.choice(candidates)

        if not file_url:
            continue

        logging.info(f"Pexels: trying to download {file_url} for query='{query}'")
        try:
            if os.path.exists(EXPECTED_VIDEO):
                os.remove(EXPECTED_VIDEO)
        except Exception:
            pass
        success = _download_stream_to(EXPECTED_VIDEO, file_url, headers=headers)
        if success and os.path.exists(EXPECTED_VIDEO):
            return EXPECTED_VIDEO
    return None

def fetch_pixabay_video(query="nature", per_page=20):
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
        for size in ("medium", "large", "small", "tiny"):
            if vids.get(size) and vids[size].get("url"):
                file_url = vids[size]["url"]
                break
        if not file_url:
            continue

        logging.info(f"Pixabay: trying to download {file_url} for query='{query}'")
        try:
            if os.path.exists(EXPECTED_VIDEO):
                os.remove(EXPECTED_VIDEO)
        except Exception:
            pass
        success = _download_stream_to(EXPECTED_VIDEO, file_url)
        if success and os.path.exists(EXPECTED_VIDEO):
            return EXPECTED_VIDEO
    return None

def fetch_background_video_for_topic(topic):
    logging.info(f"Attempting to fetch fresh background video for topic: '{topic}'")
    path = fetch_pexels_video(query=topic)
    if path:
        logging.info("Fetched background from Pexels.")
        return path
    path = fetch_pixabay_video(query=topic)
    if path:
        logging.info("Fetched background from Pixabay.")
        return path
    logging.warning(f"Could not fetch background from Pexels or Pixabay for topic '{topic}'.")
    return None

def _create_silent_audio(duration_seconds, out_path="voiceover.mp3"):
    try:
        duration_seconds = max(0.5, float(duration_seconds))
    except Exception:
        duration_seconds = 4.0

    try:
        ms = int(duration_seconds * 1000)
        silent = AudioSegment.silent(duration=ms)
        silent.export(out_path, format=os.path.splitext(out_path)[1].lstrip(".") or "mp3")
        return out_path
    except Exception as e:
        logging.warning(f"pydub silent export failed for {out_path}: {e}; falling back to WAV.")
        fallback_path = os.path.splitext(out_path)[0] + ".wav"
        try:
            return _write_silent_wav(duration_seconds, fallback_path)
        except Exception as e2:
            logging.error(f"WAV silent fallback failed for {fallback_path}: {e2}")
            return None

def get_audio_duration(audio_file):
    if not audio_file or not os.path.exists(audio_file):
        logging.warning(f"get_audio_duration: file not found: {audio_file}")
        return None

    if audio_file.lower().endswith(".wav"):
        try:
            with wave.open(audio_file, "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    return frames / float(rate)
        except Exception as e:
            logging.warning(f"Could not read WAV duration for {audio_file}: {e}")

    if FFMPEG_EXE and os.path.exists(audio_file):
        try:
            probe = subprocess.run(
                [FFMPEG_EXE, "-i", audio_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            text = probe.stderr or ""
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
            if m:
                h = int(m.group(1))
                mi = int(m.group(2))
                s = float(m.group(3))
                return h * 3600 + mi * 60 + s
        except Exception as e:
            logging.warning(f"Could not probe audio duration for {audio_file}: {e}")

    try:
        audio = AudioSegment.from_file(audio_file)
        return len(audio) / 1000.0
    except Exception as e:
        logging.warning(f"Could not get audio duration for {audio_file}: {e}")
        return None

def fetch_voiceover(quote, api_key, fallback_silent_duration=4):
    global voiceover_file, _voiceover_cached_quote
    if _voiceover_cached_quote == quote and voiceover_file and os.path.exists(voiceover_file):
        return voiceover_file
    
    for fn in ("voiceover.mp3", "voiceover.wav"):
        if os.path.exists(fn):
            try:
                os.remove(fn)
            except Exception:
                pass

    voiceover_file = None
    _voiceover_cached_quote = None
    if not api_key:
        logging.warning("VOICE_RSS_API_KEY not set; using silent fallback audio")
        voiceover_file = _create_silent_audio(fallback_silent_duration, out_path="voiceover.mp3")
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
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        ct = response.headers.get("Content-Type", "")
        if "audio" not in ct.lower() and not response.content.startswith(b"ID3"):
            logging.error("TTS returned non-audio content; falling back to silent audio")
            voiceover_file = _create_silent_audio(fallback_silent_duration, out_path="voiceover.mp3")
            _voiceover_cached_quote = quote
            return voiceover_file
        if len(response.content) < 1000:
            logging.warning("TTS returned suspiciously small payload; using silent fallback")
            voiceover_file = _create_silent_audio(fallback_silent_duration, out_path="voiceover.mp3")
            _voiceover_cached_quote = quote
            return voiceover_file
            
        with open("voiceover.mp3", "wb") as f:
            f.write(response.content)
        voiceover_file = "voiceover.mp3"
        _voiceover_cached_quote = quote
        logging.info("Downloaded voiceover.mp3")
        return voiceover_file
    except Exception as e:
        logging.error(f"Error fetching voiceover: {e}; using silent fallback")
        voiceover_file = _create_silent_audio(fallback_silent_duration, out_path="voiceover.mp3")
        _voiceover_cached_quote = quote
        return voiceover_file

def trim_audio(audio_file, max_duration=30):
    if not audio_file or not os.path.exists(audio_file):
        logging.warning(f"trim_audio: missing input: {audio_file}")
        return None
    try:
        audio = AudioSegment.from_file(audio_file)
    except Exception as e:
        logging.warning(f"trim_audio: ffmpeg decode failed for {audio_file}: {e}")
        return _create_silent_audio(min(max_duration, 4), out_path="trimmed_silent.mp3")
    trimmed = audio[: int(max_duration * 1000)]
    out = "trimmed_" + os.path.basename(audio_file)
    try:
        trimmed.export(out, format="mp3")
        return out
    except Exception as e:
        logging.error(f"trim_audio export failed: {e}")
        return _create_silent_audio(min(max_duration, 4), out_path="trimmed_silent.mp3")

def loop_sound(audio_file, target_duration):
    if not audio_file or not os.path.exists(audio_file):
        logging.warning("loop_sound: input missing, creating silent filler")
        return _create_silent_audio(target_duration, out_path="looped_silent.mp3")
    try:
        audio = AudioSegment.from_file(audio_file)
    except Exception as e:
        logging.warning(f"loop_sound: failed to open {audio_file}: {e}")
        return _create_silent_audio(target_duration, out_path="looped_silent.mp3")
    original = len(audio) / 1000.0
    if original <= 0:
        return _create_silent_audio(target_duration, out_path="looped_silent.mp3")
    loops_needed = int(target_duration / original) + 1
    full = audio * loops_needed
    trimmed = full[: int(target_duration * 1000)]
    out = "looped_" + os.path.basename(audio_file).split('.')[0] + ".mp3"
    try:
        trimmed.export(out, format="mp3")
        return out
    except Exception as e:
        logging.error(f"loop_sound export failed: {e}")
        return _create_silent_audio(target_duration, out_path="looped_silent.mp3")

def pre_extract_frames(video_src, output_dir, src_fps=30, tgt_fps=30, max_frames=None):
    if not video_src or not os.path.exists(video_src):
        logging.warning(f"pre_extract_frames: video not found: {video_src}")
        return False
    if not FFMPEG_EXE:
        logging.warning("FFmpeg executable not configured; cannot pre-extract frames.")
        return False
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    pattern = os.path.join(output_dir, "frame%05d.png")
    cmd = [FFMPEG_EXE, "-y", "-hide_banner", "-loglevel", "error", "-i", video_src]
    if max_frames:
        cmd += ["-vf", f"fps={tgt_fps}", "-frames:v", str(max_frames), pattern]
    else:
        cmd += ["-vf", f"fps={tgt_fps}", pattern]
    logging.info(f"pre_extract_frames: running ffmpeg (fps={tgt_fps})...")
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return True
    except Exception as e:
        logging.error(f"ffmpeg extraction failed: {e}")
        return False

def extract_video_frames(video_file, fps=30):
    if not video_file or not os.path.exists(video_file):
        logging.warning(f"extract_video_frames: missing video: {video_file}")
        return []
    if not FFMPEG_EXE:
        logging.warning("FFmpeg executable not configured; cannot extract frames.")
        return []
    existing = sorted([os.path.join(FRAMES_DIR, f) for f in os.listdir(FRAMES_DIR) if f.endswith('.png')])
    if existing:
        logging.info(f"Using pre-extracted {len(existing)} frames from {FRAMES_DIR}")
        return existing
    pattern = os.path.join(FRAMES_DIR, "frame%05d.png")
    cmd = [FFMPEG_EXE, "-y", "-hide_banner", "-loglevel", "error", "-i", video_file, "-vf", f"fps={fps}", pattern]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    except Exception as e:
        logging.error(f"ffmpeg extraction failed: {e}")
        return []
    return sorted([os.path.join(FRAMES_DIR, f) for f in os.listdir(FRAMES_DIR) if f.endswith('.png')])

def fetch_quote(max_attempts=3, timeout=10):
    global quote_data
    url = "https://zenquotes.io/api/random"

    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()

            try:
                data = resp.json()
            except ValueError as e:
                raise RuntimeError(f"Invalid JSON from quote API: {e}") from e

            if isinstance(data, list) and data:
                item = data[0] or {}
                quote_data = {
                    "quote": item.get("q", "No quote found"),
                    "author": item.get("a", "Unknown"),
                }
                logging.info(f"Fetched quote: {quote_data}")
                return quote_data

            raise RuntimeError("Quote API returned unexpected or empty data.")

        except requests.HTTPError as e:
            status = getattr(e.response, "status_code", None)
            body = ""
            if e.response is not None:
                try:
                    body = e.response.text[:300]
                except Exception:
                    pass

            logging.error(f"fetch_quote HTTP error on attempt {attempt}/{max_attempts}: {status} {body}")
            if status in {429} or (status is not None and 500 <= status < 600):
                if attempt < max_attempts:
                    time.sleep((2 ** (attempt - 1)) + random.uniform(0, 0.5))
                    continue
            break
        except (requests.Timeout, requests.ConnectionError, requests.RequestException) as e:
            logging.error(f"fetch_quote request error on attempt {attempt}/{max_attempts}: {e}")
            if attempt < max_attempts:
                time.sleep((2 ** (attempt - 1)) + random.uniform(0, 0.5))
                continue
            break
        except Exception as e:
            logging.error(f"fetch_quote unexpected error: {e}")
            break

    quote_data = {"quote": "No quote found", "author": "Unknown"}
    logging.info(f"Using fallback quote: {quote_data}")
    return quote_data

def create_quote_mobjects(quote_text, quote_author, frame_width, frame_height):
    wrapped = "\n".join(textwrap.wrap(quote_text, width=40))
    q = Paragraph(wrapped, alignment="center", line_spacing=0.6)
    q.set_color_by_gradient(WHITE, YELLOW)
    try:
        max_w = frame_width * 0.8
        max_h = frame_height * 0.5
        q.set_width(min(q.width, max_w))
        q.set_height(min(q.height, max_h))
    except Exception:
        pass
    a = Text(f"- {quote_author}", font_size=24)
    a.set_color(YELLOW)
    return q, a

class AnimatedQuoteWithBackground(Scene):
    def construct(self):
        
        # 1. Run the new image fetcher right at the beginning of the scene
        fetch_hd_nature_images(num_images=10)
        fetch_hd_nature_images2(num_images=5)

        total_duration = 7

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
                    continue
                _remove_path_safe(os.path.join(dirpath, name))

        logging.info("Clearing previous background files & frames.")
        preserve_name = os.path.basename(EXPECTED_SOUND)
        _clear_media_dir(BG_VIDEOS_DIR, preserve_names=())
        _clear_media_dir(BG_SOUNDS_DIR, preserve_names=(preserve_name,))
        _clear_media_dir(FRAMES_DIR, preserve_names=())

        for tmp_name in ("pexels_bg.mp4", "pixabay_bg.mp4"):
            _remove_path_safe(os.path.join(BASE_DIR, tmp_name))

        quote_info = fetch_quote()
        raw = quote_info.get('quote', 'No quote found')
        display_q = f'"{raw}"'
        author = quote_info.get('author', 'Unknown')

        audio = fetch_voiceover(raw, voice_api_key)

        measured_voice_dur = None
        if audio and os.path.exists(audio):
            try:
                measured_voice_dur = get_audio_duration(audio)
                if measured_voice_dur is not None:
                    logging.info(f"Measured voiceover duration: {measured_voice_dur:.2f}s")
            except Exception as e:
                logging.warning(f"Could not measure voiceover duration: {e}")

        if measured_voice_dur and measured_voice_dur > 0:
            total_duration = float(measured_voice_dur) + 0.25
            if total_duration > 120:
                total_duration = 120.0
            logging.info(f"Scene total_duration set from voiceover: {total_duration:.2f}s")

        if os.path.isfile(EXPECTED_SOUND):
            try:
                looped_effect = loop_sound(EXPECTED_SOUND, total_duration)
                if looped_effect and os.path.exists(looped_effect):
                    self.add_sound(looped_effect, gain=-5)
            except Exception as e:
                logging.warning(f"Background sound loading failed: {e}")

        env_topic = os.environ.get("BG_QUERY", None)
        chosen_topic = env_topic if env_topic else random.choice(TOPIC_CHOICES)
        logging.info(f"Topic finalized for video search: '{chosen_topic}'")

        fetched_video = fetch_background_video_for_topic(chosen_topic)
        video_background_file = fetched_video if (fetched_video and os.path.exists(fetched_video)) else EXPECTED_VIDEO

        video_frames = extract_video_frames(video_background_file, fps=30)
        
        # --- FIXED PERFORMANCE: Lazy array lookup instead of 150+ pre-instantiated ImageMobjects ---
        if not video_frames:
            logging.error("No background frames available. Scene will have no background.")
        else:
            # Load only the absolute first frame to start the container canvas
            bg_container = ImageMobject(video_frames[0]).scale_to_fit_width(config.frame_width)
            bg_container.set_z_index(-10)
            self.add(bg_container)

            # Limit framework pool length safely
            max_frames_pool = video_frames[:150]

            # Optimized updater function avoiding memory leakage / redundant creation arrays
            def rapid_image_swap(mob, dt):
                swap_speed = 15  
                index = int((self.time * swap_speed) % len(max_frames_pool))
                # Generate/render frame asset contextually on the fly safely
                mob.become(ImageMobject(max_frames_pool[index]).scale_to_fit_width(config.frame_width))

            bg_container.add_updater(rapid_image_swap)

        q_mobj, a_mobj = create_quote_mobjects(display_q, author, self.camera.frame_width, self.camera.frame_height)
        q_mobj.move_to(UP * 0.5)
        a_mobj.next_to(q_mobj, DOWN, buff=0.4)

        if audio and os.path.exists(audio):
            try:
                voice_len = get_audio_duration(audio)
            except Exception:
                voice_len = None
            if voice_len and voice_len > total_duration + 0.001:
                trimmed = trim_audio(audio, max_duration=total_duration)
                if trimmed and os.path.exists(trimmed):
                    self.add_sound(trimmed, gain=+10)
            else:
                self.add_sound(audio, gain=+10)

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

if __name__ == '__main__':
    if os.environ.get("AUTO_PREEXTRACT", "0") in ("1", "true", "yes"):
        if os.path.exists(EXPECTED_VIDEO):
            pre_extract_frames(EXPECTED_VIDEO, FRAMES_DIR, src_fps=30, tgt_fps=30, max_frames=600)