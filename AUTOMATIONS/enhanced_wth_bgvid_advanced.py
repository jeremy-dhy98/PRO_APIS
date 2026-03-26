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
import tempfile
from io import BytesIO
from PIL import Image
import imageio_ffmpeg

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load API keys from environment variables
cat_api_key = os.environ.get("CAT_API_KEY")
voice_api_key = os.environ.get("VOICE_RSS_API_KEY")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")

# Directories and filenames
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BG_VIDEOS_DIR = os.environ.get("BG_VIDEOS_DIR", os.path.join(BASE_DIR, "bg_videos"))
BG_SOUNDS_DIR = os.environ.get("BG_SOUNDS_DIR", os.path.join(BASE_DIR, "bg_sounds"))
FRAMES_DIR = os.path.join(BASE_DIR, "video_frames")
EXPECTED_VIDEO = os.path.join(BASE_DIR, "219305_tiny.mp4")   # Will be overwritten by downloaded file
EXPECTED_SOUND = os.path.abspath(os.path.join(BASE_DIR, "subclip.ogg"))
CAT_IMAGE_FILENAME = "cat_image.jpg"

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

# --- Topics to choose from ---
TOPIC_CHOICES = ["nature", "birds", "art"]

# --- Globals ---
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

# ---------- New: background fetch helpers ----------
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

def fetch_pexels_video(query="nature", per_page=15):
    if not PEXELS_API_KEY:
        logging.info("PEXABLS_API_KEY not set; skipping Pexels fetch.")
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
        # Prefer small/SD links to keep size reasonable
        for vf in video_files:
            # Robust handling: quality may be None or non-string; guard against that.
            quality = vf.get("quality")
            if not isinstance(quality, str):
                # If quality is missing or not a string, treat as empty string.
                # Log at debug level to avoid noisy logs in normal runs.
                logging.debug(f"Skipping non-string quality value in Pexels file entry: {quality!r}")
                q = ""
            else:
                q = quality.lower()

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
        # ensure we always overwrite EXPECTED_VIDEO to force fresh file
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
    # Try Pexels first, then Pixabay
    path = fetch_pexels_video(query=topic)
    if path:
        logging.info("Fetched background from Pexels.")
        return path
    path = fetch_pixabay_video(query=topic)
    if path:
        logging.info("Fetched background from Pixabay.")
        return path
    logging.warning("Could not fetch background from Pexels or Pixabay for topic '%s'." % topic)
    return None

# ---------- End background fetch helpers ----------

# --- (other helpers unchanged — tts, audio, frames, display utilities) ---
def _create_silent_audio(duration_seconds, out_path="voiceover.mp3"):
    """
    Create silence in a way that does not crash when FFmpeg is missing.
    It first tries pydub export; if that fails, it writes a WAV file directly.
    """
    try:
        duration_seconds = max(0.5, float(duration_seconds))
    except Exception:
        duration_seconds = 4.0

    # If the caller asked for mp3, keep the name only if export works.
    # Otherwise, switch to a WAV fallback.
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
    """Returns the duration (in seconds) of the given audio file."""
    if not audio_file or not os.path.exists(audio_file):
        logging.warning(f"get_audio_duration: file not found: {audio_file}")
        return None

    # WAV can be read without FFmpeg/ffprobe
    if audio_file.lower().endswith(".wav"):
        try:
            with wave.open(audio_file, "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    return frames / float(rate)
        except Exception as e:
            logging.warning(f"Could not read WAV duration for {audio_file}: {e}")

    # Try FFmpeg probe (works without ffprobe)
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

    # Last fallback: pydub
    try:
        audio = AudioSegment.from_file(audio_file)
        return len(audio) / 1000.0
    except Exception as e:
        logging.warning(f"Could not get audio duration for {audio_file}: {e}")
        return None

def fetch_voiceover(quote, api_key, fallback_silent_duration=4):
    """Fetches voiceover for the given quote using VoiceRSS API (always fetch new)."""
    global voiceover_file, _voiceover_cached_quote
    if _voiceover_cached_quote == quote and voiceover_file and os.path.exists(voiceover_file):
        return voiceover_file
    try:
        if voiceover_file and os.path.exists(voiceover_file):
            os.remove(voiceover_file)
    except Exception:
        pass
    if os.path.exists("voiceover.mp3"):
        try:
            os.remove("voiceover.mp3")
        except Exception:
            pass
    if os.path.exists("voiceover.wav"):
        try:
            os.remove("voiceover.wav")
        except Exception:
            pass

    voiceover_file = None
    _voiceover_cached_quote = None
    if not api_key:
        logging.warning("VOICE_RSS_API_KEY not set; using silent fallback audio")
        out = _create_silent_audio(fallback_silent_duration, out_path="voiceover.mp3")
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
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        ct = response.headers.get("Content-Type", "")
        if "audio" not in ct.lower() and not response.content.startswith(b"ID3"):
            logging.error("TTS returned non-audio content; falling back to silent audio")
            out = _create_silent_audio(fallback_silent_duration, out_path="voiceover.mp3")
            voiceover_file = out
            _voiceover_cached_quote = quote
            return voiceover_file
        if len(response.content) < 1000:
            logging.warning("TTS returned suspiciously small payload; using silent fallback")
            out = _create_silent_audio(fallback_silent_duration, out_path="voiceover.mp3")
            voiceover_file = out
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
        out = _create_silent_audio(fallback_silent_duration, out_path="voiceover.mp3")
        voiceover_file = out
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

def pre_extract_frames(video_src, output_dir, src_fps=60, tgt_fps=60, max_frames=None):
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
    except Exception as e:
        logging.error(f"ffmpeg extraction failed: {e}")
        return False
    files = sorted([f for f in os.listdir(output_dir) if f.endswith('.png')])
    logging.info(f"pre_extract_frames: extracted {len(files)} frames")
    return True

def extract_video_frames(video_file, fps=60):
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
    frames = sorted([os.path.join(FRAMES_DIR, f) for f in os.listdir(FRAMES_DIR) if f.endswith('.png')])
    return frames

def display_fast_frame_sequence(scene, frame_paths, frame_display_time=0.02, max_frames=300, preserve_aspect=True):
    if not frame_paths:
        return None
    count = min(len(frame_paths), max_frames)
    bg = None
    for i in range(count):
        path = frame_paths[i]
        try:
            img = ImageMobject(path)
        except Exception as e:
            logging.warning(f"display_fast_frame_sequence: skipping frame {path}: {e}")
            continue
        if preserve_aspect:
            try:
                img.set_height(scene.camera.frame_height + 0.5)
            except Exception:
                img.scale(4)
        else:
            try:
                img.set_width(scene.camera.frame_width * 1.05)
                img.set_height(scene.camera.frame_height * 1.05)
            except Exception:
                img.scale(4)
        try:
            img.set_z_index(-10)
        except Exception:
            pass
        if bg is None:
            bg = img
            scene.add(bg)
        else:
            try:
                scene.remove(bg)
            except Exception:
                pass
            bg = img
            scene.add(bg)
        scene.wait(frame_display_time)
    return bg

def add_fast_pool_updater(scene, frame_paths, fast_frame_time=0.03, pool_size=120):
    if not frame_paths:
        return None
    pool_size = min(pool_size, len(frame_paths))
    bg_pool = []
    for p in frame_paths[:pool_size]:
        try:
            im = ImageMobject(p)
            try:
                im.set_height(scene.camera.frame_height + 0.5)
            except Exception:
                im.scale(4)
            try:
                im.set_z_index(-10)
            except Exception:
                pass
            bg_pool.append(im)
        except Exception as e:
            logging.warning(f"add_fast_pool_updater: skip {p}: {e}")
            continue
    if not bg_pool:
        return None
    try:
        container = bg_pool[0].copy()
    except Exception:
        container = bg_pool[0]
    container.set_z_index(-10)
    scene.add(container)

    def updater(mob, dt):
        swap_speed = max(1, int(1.0 / fast_frame_time))
        try:
            idx = int((scene.time * swap_speed) % len(bg_pool))
            mob.become(bg_pool[idx])
            try:
                mob.set_z_index(-10)
            except Exception:
                pass
        except Exception:
            pass

    container.add_updater(updater)
    return container

def fetch_quote():
    global quote_data
    url = "https://zenquotes.io/api/random"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data:
            quote_data = {"quote": data[0].get("q", "No quote found"), "author": data[0].get("a", "Unknown")}
            logging.info(f"Fetched quote: {quote_data}")
            return quote_data
    except Exception as e:
        logging.error(f"fetch_quote failed: {e}")
    quote_data = {"quote": "No quote found", "author": "Unknown"}
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
        preserve_name = os.path.basename(EXPECTED_SOUND)
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
                measured_voice_dur = get_audio_duration(audio)
                if measured_voice_dur is not None:
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
        if os.path.isfile(EXPECTED_SOUND):
            try:
                looped_effect = loop_sound(EXPECTED_SOUND, total_duration)
                if looped_effect and os.path.exists(looped_effect):
                    self.add_sound(looped_effect, gain=-5)
                else:
                    logging.info("Background sound could not be prepared; skipping background loop sound.")
            except Exception as e:
                logging.warning(f"Background sound loading failed: {e}")
        else:
            logging.info(f"Background sound file not found at {EXPECTED_SOUND}.")

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
        video_background_file = fetched_video if (fetched_video and os.path.exists(fetched_video)) else EXPECTED_VIDEO

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
                for img in video_frames[:150]  # Limit pool to manage memory
            ]

        # --- UPDATED FIX: Use set_z_index and self.add() to ensure background stays behind text ---
        if bg_pool:
            bg_container = bg_pool[0].copy()
            bg_container.set_z_index(-10)  # Force background to the bottom layer
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
                voice_len = get_audio_duration(audio)
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
        remaining_time = total_duration - time_used

        # Only call self.wait() if strictly positive to avoid Manim ValueError for zero duration
        if remaining_time > 1e-6:
            self.wait(remaining_time)
        else:
            logging.info(f"No remaining time to wait (remaining={remaining_time}); skipping self.wait().")

if __name__ == '__main__':
    # Optionally pre-extract before rendering (set env var AUTO_PREEXTRACT=1)
    if os.environ.get("AUTO_PREEXTRACT", "0") in ("1", "true", "yes"):
        if os.path.exists(EXPECTED_VIDEO):
            pre_extract_frames(EXPECTED_VIDEO, FRAMES_DIR, src_fps=30, tgt_fps=30, max_frames=600)
    pass