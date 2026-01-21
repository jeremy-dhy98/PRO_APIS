from manim import *
import requests
import logging
import os
import textwrap
import subprocess
from pydub import AudioSegment
import random
import shutil
import tempfile
from io import BytesIO
from PIL import Image

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
EXPECTED_SOUND = os.path.join(BASE_DIR, "subclip.ogg")
CAT_IMAGE_FILENAME = "cat_image.jpg"

os.makedirs(BG_VIDEOS_DIR, exist_ok=True)
os.makedirs(BG_SOUNDS_DIR, exist_ok=True)
os.makedirs(FRAMES_DIR, exist_ok=True)

# --- Topics to choose from ---
TOPIC_CHOICES = ["nature", "birds", "art"]

# --- Globals ---
quote_data = None
voiceover_file = None
_voiceover_cached_quote = None

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
    ms = int(duration_seconds * 1000)
    silent = AudioSegment.silent(duration=ms)
    silent.export(out_path, format="mp3")
    return out_path

def fetch_voiceover(quote, api_key, fallback_silent_duration=4):
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
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        ct = resp.headers.get("Content-Type", "")
        if "audio" not in ct.lower() and not resp.content.startswith(b"ID3"):
            logging.error("TTS returned non-audio content; falling back to silent audio")
            return _create_silent_audio(fallback_silent_duration, out_path="voiceover.mp3")
        if len(resp.content) < 1000:
            logging.warning("TTS returned suspiciously small payload; using silent fallback")
            return _create_silent_audio(fallback_silent_duration, out_path="voiceover.mp3")
        with open("voiceover.mp3", "wb") as f:
            f.write(resp.content)
        voiceover_file = "voiceover.mp3"
        _voiceover_cached_quote = quote
        logging.info("Downloaded voiceover.mp3")
        return voiceover_file
    except Exception as e:
        logging.error(f"Error fetching voiceover: {e}; using silent fallback")
        return _create_silent_audio(fallback_silent_duration, out_path="voiceover.mp3")

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
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    pattern = os.path.join(output_dir, "frame%05d.png")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", video_src]
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
    existing = sorted([os.path.join(FRAMES_DIR, f) for f in os.listdir(FRAMES_DIR) if f.endswith('.png')])
    if existing:
        logging.info(f"Using pre-extracted {len(existing)} frames from {FRAMES_DIR}")
        return existing
    pattern = os.path.join(FRAMES_DIR, "frame%05d.png")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", video_file, "-vf", f"fps={fps}", pattern]
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

# ---------------------
# Randomized text animation styles (NEW)
# ---------------------
def _glowify(mobj, layers=3, scale_step=1.04, opacity_step=0.12):
    """
    Create a subtle glow by stacking slightly larger, low-opacity copies behind.
    Returns a VGroup (glow layers + original).
    """
    layers_list = []
    for i in range(layers, 0, -1):
        try:
            copy = mobj.copy()
            copy.set_opacity(opacity_step * i)
            copy.scale(scale_step * (1 + (i * 0.01)))
            layers_list.append(copy)
        except Exception:
            # if copy fails, skip gracefully
            continue
    try:
        layers_list.append(mobj)
        return VGroup(*layers_list)
    except Exception:
        return mobj

def style_handwriting(scene, q_mobj, a_mobj, total_duration, raw_text=None):
    # Classic handwriting: Manim's Write for a natural reveal
    scene.add(q_mobj)
    run = min(total_duration * 0.6, 4.0)
    try:
        scene.play(Write(q_mobj), run_time=run)
    except Exception:
        # fallback: fadeIn
        scene.play(FadeIn(q_mobj), run_time=min(1.2, run))
    scene.play(FadeIn(a_mobj), run_time=0.8)

def style_wordbyword(scene, q_mobj, a_mobj, sync_duration=None, raw_text=None, **kwargs):
    """
    Word-by-word reveal with wrapping (robust signature: sync_duration).
    - Wrap words into multiple lines constrained by max_width (based on q_mobj or camera).
    - Animate words left->right, top->bottom with LaggedStart.
    - Scale very long single words to fit.
    """
    # Use sync_duration (may be None)
    total_duration = sync_duration or 5.0

    # Get raw text to split words (prefer raw_text if available)
    text_source = None
    if raw_text:
        text_source = raw_text.strip().replace("\n", " ")
    else:
        try:
            if hasattr(q_mobj, "get_text"):
                text_source = q_mobj.get_text()
            elif hasattr(q_mobj, "text"):
                text_source = q_mobj.text
        except Exception:
            text_source = None

    if not text_source:
        # fallback: show the paragraph as-is
        scene.add(q_mobj)
        scene.play(FadeIn(q_mobj), run_time=min(1.0, total_duration * 0.2))
        scene.play(FadeIn(a_mobj), run_time=0.7)
        return

    # Prepare words
    words = [w for w in text_source.split(" ") if w.strip()]
    if not words:
        scene.add(q_mobj)
        scene.play(FadeIn(q_mobj), run_time=min(1.0, total_duration * 0.2))
        scene.play(FadeIn(a_mobj), run_time=0.7)
        return

    # Determine layout constraints
    try:
        preferred_width = getattr(q_mobj, "width", 0) or 0
        max_width = min(preferred_width if preferred_width > 0 else scene.camera.frame_width * 0.8,
                        scene.camera.frame_width * 0.9)
    except Exception:
        max_width = scene.camera.frame_width * 0.9

    # Base font size (try to reuse q_mobj font size)
    base_font = 40
    try:
        base_font = getattr(q_mobj, "font_size", base_font) or base_font
    except Exception:
        pass

    # Create Text mobjects for each word, scaling any that are too wide
    word_mobs = []
    for w in words:
        try:
            wm = Text(w, font_size=base_font)
        except Exception:
            wm = Text(w)
        try:
            if wm.width > max_width:
                scale_factor = (max_width / wm.width) * 0.95
                wm.scale(scale_factor)
        except Exception:
            pass
        word_mobs.append(wm)

    # Pack words into lines so each line.width <= max_width
    lines = []
    current_line = VGroup()
    spacing = 0.12
    for wm in word_mobs:
        if len(current_line) == 0:
            current_line.add(wm)
            try:
                current_line.arrange(RIGHT, buff=spacing)
            except Exception:
                pass
            continue

        # Tentatively add and measure
        current_line.add(wm)
        try:
            current_line.arrange(RIGHT, buff=spacing)
            if current_line.width > max_width:
                # overflow: remove wm from current_line and start a new line
                current_line.remove(wm)
                lines.append(current_line)
                current_line = VGroup()
                current_line.add(wm)
                try:
                    current_line.arrange(RIGHT, buff=spacing)
                except Exception:
                    pass
            else:
                # still fits
                pass
        except Exception:
            # On measurement error, keep current_line as-is
            pass

    if len(current_line) > 0:
        lines.append(current_line)

    if not lines:
        # fallback: display paragraph
        scene.add(q_mobj)
        scene.play(FadeIn(q_mobj), run_time=min(1.0, total_duration * 0.2))
        scene.play(FadeIn(a_mobj), run_time=0.7)
        return

    # Arrange lines and position where the original paragraph was
    for ln in lines:
        try:
            ln.arrange(RIGHT, buff=spacing)
        except Exception:
            pass

    lines_group = VGroup(*lines)
    try:
        lines_group.arrange(DOWN, buff=0.15)
        try:
            target_center = q_mobj.get_center()
        except Exception:
            target_center = ORIGIN
        lines_group.move_to(target_center)
    except Exception:
        lines_group.center()

    # Add to scene (avoid adding original paragraph to prevent duplicates)
    scene.add(lines_group)

    # Flatten words into reading order (left->right top->bottom)
    ordered_words = []
    for ln in lines:
        for sub in ln:
            ordered_words.append(sub)

    # Animation timing
    run_words = max(1.0, min(total_duration * 0.55, 6.0))
    lag_ratio = 0.12 if len(ordered_words) < 12 else 0.06

    # Animate with staggered FadeIn, fallback to single fade
    try:
        scene.play(
            LaggedStart(*[FadeIn(w, shift=UP, scale=0.95) for w in ordered_words], lag_ratio=lag_ratio),
            run_time=run_words,
        )
    except Exception:
        scene.play(FadeIn(lines_group), run_time=min(1.2, run_words))

    # Reveal author
    try:
        scene.play(FadeIn(a_mobj, shift=UP), run_time=0.7)
    except Exception:
        scene.add(a_mobj)

def style_mask_reveal(scene, quote_mobject, author_mobject, sync_duration=None, raw_text=None):
    """
    Rotating shard reveal:
    Several vertical 'shards' cover the quote, then rotate & slide outward
    in a staggered (lagged) sequence revealing the quote underneath.
    Uses sync_duration to scale animation timing when available.
    """
    # Ensure quote is present under the shards
    try:
        scene.add(quote_mobject)
    except Exception:
        pass

    try:
        # Compute bounding box for the quote
        left_pt = quote_mobject.get_left()
        right_pt = quote_mobject.get_right()
        top_pt = quote_mobject.get_top()
        bottom_pt = quote_mobject.get_bottom()
        center_pt = quote_mobject.get_center()

        left_x = float(left_pt[0])
        right_x = float(right_pt[0])
        center_y = float(center_pt[1])
        width = max(0.01, right_x - left_x)
        height = max(0.5, float(top_pt[1] - bottom_pt[1]))
    except Exception:
        # fallback to camera-sized box
        center_pt = quote_mobject.get_center() if hasattr(quote_mobject, "get_center") else ORIGIN
        center_y = float(center_pt[1]) if hasattr(center_pt, "__len__") else 0.0
        width = scene.camera.frame_width * 0.7
        height = scene.camera.frame_height * 0.35
        left_x = -width / 2 + float(center_pt[0]) if hasattr(center_pt, "__len__") else -width / 2

    # Shard configuration
    n_shards = 8
    try:
        # scale shards by quote width so short quotes still look good
        n_shards = max(4, min(12, int(width // (scene.camera.frame_width * 0.06)) or 8))
    except Exception:
        n_shards = 8

    shard_w = width / n_shards * 1.02
    shards = []

    for i in range(n_shards):
        try:
            shard = Rectangle(width=shard_w, height=height * 1.15)
            shard.set_fill(BLACK, opacity=0.95)
            shard.set_stroke(width=0)
            # place shards across the quote bounding box
            x = left_x + shard_w * (i + 0.5)
            shard.move_to(RIGHT * x + UP * center_y)
            # ensure shards are visually on top
            try:
                shard.set_z_index(1000)
            except Exception:
                pass
            scene.add(shard)
            shards.append(shard)
        except Exception:
            continue

    # Decide timing
    total_shard_time = min(sync_duration * 0.35, 1.2) if sync_duration else 0.9
    lag_ratio = 0.08

    # Prepare animations for each shard: rotate + slide outward with some variance
    anims = []
    for idx, shard in enumerate(shards):
        try:
            # sign: left shards go left, right shards go right
            side = -1 if idx < (len(shards) / 2) else 1
            # randomize rotation and vertical drift
            angle_deg = side * (random.uniform(18, 55))
            angle = angle_deg * DEGREES
            horiz_shift = side * scene.camera.frame_width * random.uniform(0.8, 1.3)
            vert_shift = scene.camera.frame_height * random.uniform(-0.25, 0.25)
            shift_vec = RIGHT * horiz_shift + UP * vert_shift
            # create the animation (rotate then shift together)
            anim = shard.animate.rotate(angle).shift(shift_vec)
            anims.append(anim)
        except Exception:
            # fallback: simple fade out if transform cannot be created
            anims.append(FadeOut(shard))

    # Play the staggered shard animations
    try:
        # Use LaggedStart to create the staggered shard effect
        scene.play(LaggedStart(*anims, lag_ratio=lag_ratio), run_time=max(0.6, total_shard_time))
    except Exception:
        # fallback: quickly fade the shards away
        try:
            scene.play(LaggedStart(*[FadeOut(s) for s in shards], lag_ratio=lag_ratio), run_time=0.8)
        except Exception:
            pass

    # Remove shards (clean up)
    for s in shards:
        try:
            scene.remove(s)
        except Exception:
            pass

    # Finally, reveal the author
    try:
        scene.play(FadeIn(author_mobject), run_time=0.7)
    except Exception:
        try:
            scene.add(author_mobject)
        except Exception:
            pass

def style_kinetic(scene, q_mobj, a_mobj, total_duration, raw_text=None):
    # Scale + color pulse + small rotate emphasis
    scene.add(q_mobj)
    run = min(total_duration * 0.45, 3.0)
    try:
        scene.play(Write(q_mobj), run_time=run)
    except Exception:
        scene.play(FadeIn(q_mobj), run_time=min(1.0, run))
    # a quick emphasis pulse
    try:
        scene.play(q_mobj.animate.scale(1.06).set_color_by_gradient(BLUE, PURPLE), run_time=0.45)
        scene.play(q_mobj.animate.scale(1/1.06).set_color_by_gradient(WHITE, YELLOW), run_time=0.35)
    except Exception:
        pass
    scene.play(FadeIn(a_mobj), run_time=0.6)

def style_pop_and_bounce(scene, q_mobj, a_mobj, total_duration, raw_text=None):
    # Pop-in and subtle bounce
    q_copy = q_mobj.copy()
    q_copy.scale(0.85)
    scene.add(q_copy)
    try:
        scene.play(FadeIn(q_copy), run_time=0.4)
        scene.play(q_copy.animate.scale(1.12).set_color_by_gradient(YELLOW, ORANGE), run_time=0.5)
        scene.play(q_copy.animate.scale(1/1.12), run_time=0.35)
    except Exception:
        scene.play(FadeIn(q_copy), run_time=0.9)
    scene.play(FadeIn(a_mobj), run_time=0.6)
    try:
        # replace original with the copy to keep scene consistent
        scene.remove(q_mobj)
        scene.add(q_copy)
    except Exception:
        pass

def style_neon_glow(scene, q_mobj, a_mobj, total_duration, raw_text=None):
    # Create glow by stacking copies (non-destructive)
    glow = _glowify(q_mobj, layers=3)
    try:
        glow.move_to(q_mobj.get_center())
        scene.add(glow)
        scene.play(FadeIn(glow, shift=DOWN), run_time=min(total_duration * 0.6, 3.5))
    except Exception:
        scene.add(q_mobj)
        scene.play(FadeIn(q_mobj), run_time=min(1.2, total_duration * 0.4))
    scene.play(FadeIn(a_mobj), run_time=0.6)

_ANIM_STYLES = [
    style_handwriting,
    style_wordbyword,
    style_mask_reveal,
    style_kinetic,
    style_pop_and_bounce,
    style_neon_glow,
]

def play_random_text_style(scene, q_mobj, a_mobj, total_duration, raw_text=None):
    """
    Choose a random polished style and play it.
    Optionally supply raw_text (string) to help word-by-word style.
    """
    style = random.choice(_ANIM_STYLES)
    logging.info(f"Selected text animation style: {style.__name__}")
    try:
        style(scene, q_mobj, a_mobj, total_duration, raw_text=raw_text)
    except Exception as e:
        logging.warning(f"Selected style {style.__name__} failed: {e}. Falling back to simple fade.")
        scene.add(q_mobj)
        scene.play(FadeIn(q_mobj), run_time=min(1.2, total_duration * 0.2))
        scene.play(FadeIn(a_mobj), run_time=0.7)

    # Small accent occasionally
    if random.random() < 0.35:
        try:
            underline = Line(q_mobj.get_left() + DOWN * 0.22, q_mobj.get_right() + DOWN * 0.22, stroke_width=3)
            underline.set_opacity(0.0)
            scene.add(underline)
            scene.play(underline.animate.set_opacity(1.0), run_time=0.5)
            scene.play(FadeOut(underline), run_time=0.4)
        except Exception:
            pass

# === Scene using the fast background display (now picks a random topic and fetches fresh media each run) ===
class AnimatedQuoteWithBackground(Scene):
    def construct(self):
        # We'll set total_duration from the voiceover length below.
        # Default fallback:
        total_duration = 7.0

        # Step 0: choose topic at random (or use BG_QUERY env var to override)
        env_topic = os.environ.get("BG_QUERY")
        if env_topic:
            topic = env_topic
            logging.info(f"BG_QUERY provided via env: '{topic}'")
        else:
            topic = random.choice(TOPIC_CHOICES)
            logging.info(f"No BG_QUERY set — randomly selected topic: '{topic}'")

        # Fetch quote & TTS first so we can set scene duration from voice length
        qinfo = fetch_quote()
        raw = qinfo.get('quote', 'No quote found')
        display_q = f'"{raw}"'
        author = qinfo.get('author', 'Unknown')

        # Fetch voiceover (this will write voiceover.mp3 or fallback silent file)
        audio = fetch_voiceover(raw, voice_api_key)
        measured_voice_dur = None
        if audio and os.path.exists(audio):
            try:
                measured_voice_dur = AudioSegment.from_file(audio).duration_seconds
                logging.info(f"Measured voiceover duration: {measured_voice_dur:.2f}s")
            except Exception as e:
                logging.warning(f"Could not measure voiceover duration: {e}")
                measured_voice_dur = None

        # Determine total_duration from voiceover length (with small padding) if available
        if measured_voice_dur and measured_voice_dur > 0:
            # add small padding to avoid premature cut
            total_duration = float(measured_voice_dur) + 0.25
            # cap to something reasonable
            if total_duration > 120:
                total_duration = 120.0
            logging.info(f"Setting scene total_duration to voice length + padding: {total_duration:.2f}s")
        else:
            logging.info(f"Using fallback total_duration: {total_duration:.2f}s")

        # ---- CLEAR EXISTING MEDIA (but never delete a file named 'subclip.ogg') ----
        # Clear BG_VIDEOS_DIR and BG_SOUNDS_DIR so fresh downloads happen each run.
        def _clear_dir_but_keep_subclip(dirpath):
            try:
                for name in os.listdir(dirpath):
                    full = os.path.join(dirpath, name)
                    # skip if this file is named 'subclip.ogg'
                    if os.path.basename(full) == os.path.basename(EXPECTED_SOUND):
                        logging.info(f"Skipping removal of {full} (subclip.ogg protected).")
                        continue
                    try:
                        if os.path.isfile(full) or os.path.islink(full):
                            os.remove(full)
                        elif os.path.isdir(full):
                            shutil.rmtree(full)
                    except Exception:
                        pass
            except FileNotFoundError:
                pass

        logging.info("Clearing background media directories (preserving any 'subclip.ogg').")
        _clear_dir_but_keep_subclip(BG_VIDEOS_DIR)
        _clear_dir_but_keep_subclip(BG_SOUNDS_DIR)

        # Clear frames directory (safe to remove everything)
        try:
            if os.path.exists(FRAMES_DIR):
                shutil.rmtree(FRAMES_DIR)
        except Exception:
            pass
        os.makedirs(FRAMES_DIR, exist_ok=True)

        # Always attempt to fetch a fresh video for the chosen topic (overwrites EXPECTED_VIDEO)
        fetched = fetch_background_video_for_topic(topic)
        if fetched:
            logging.info(f"Using freshly downloaded background: {fetched}")
        else:
            if os.path.exists(EXPECTED_VIDEO):
                logging.info(f"No remote video fetched — falling back to local EXPECTED_VIDEO: {EXPECTED_VIDEO}")
            else:
                logging.warning("No background video available. Scene will attempt to proceed without video frames.")

        # Prepare/loop background sound (unchanged) - use total_duration now
        if os.path.exists(EXPECTED_SOUND):
            looped = loop_sound(EXPECTED_SOUND, total_duration)
            if looped and os.path.exists(looped):
                self.add_sound(looped, gain=-5)
        else:
            logging.info("No EXPECTED_SOUND found; skipping background loop sound.")

        # Pre-extract dense frames if missing
        if not any(f.endswith('.png') for f in os.listdir(FRAMES_DIR)):
            if os.path.exists(EXPECTED_VIDEO):
                pre_extract_frames(EXPECTED_VIDEO, FRAMES_DIR, src_fps=60, tgt_fps=60, max_frames=600)
            else:
                logging.warning("No EXPECTED_VIDEO to pre-extract from.")

        frames = extract_video_frames(EXPECTED_VIDEO, fps=60)

        # Display fast background (pool updater default)
        use_pool = True
        frame_display_time = 0.02
        max_fast_frames = 300
        selected = frames[:max_fast_frames]

        bg_container = None
        if selected:
            if use_pool:
                bg_container = add_fast_pool_updater(self, selected, fast_frame_time=frame_display_time, pool_size=150)
            else:
                bg_container = display_fast_frame_sequence(self, selected, frame_display_time=frame_display_time, max_frames=max_fast_frames)
        else:
            logging.warning("No frames available for fast background")

        # Prepare text mobjects
        q_mobj, a_mobj = create_quote_mobjects(display_q, author, self.camera.frame_width, self.camera.frame_height)
        q_mobj.move_to(UP * 0.5)
        a_mobj.next_to(q_mobj, DOWN, buff=0.4)

        # Add the voiceover (trim if needed to exact scene duration)
        if audio and os.path.exists(audio):
            # If voiceover is longer than total_duration (unlikely since we based total on voice length),
            # trim to total_duration; otherwise keep it.
            try:
                voice_dur = AudioSegment.from_file(audio).duration_seconds
            except Exception:
                voice_dur = None
            if voice_dur and voice_dur > total_duration + 0.001:
                trimmed = trim_audio(audio, max_duration=total_duration)
                if trimmed and os.path.exists(trimmed):
                    self.add_sound(trimmed, gain=+10)
            else:
                self.add_sound(audio, gain=+10)

        # Animate text
        t_fadein = 0.8
        t_write = 2
        t_color = 1
        t_scale = 0.8
        t_author = 0.8

        # REPLACED: static sequence -> randomized polished style chooser
        # old:
        # self.play(FadeIn(q_mobj, shift=UP, scale=1.2), run_time=t_fadein)
        # self.play(Write(q_mobj), run_time=t_write)
        # self.play(q_mobj.animate.set_color_by_gradient(BLUE, PURPLE), run_time=t_color)
        # self.play(q_mobj.animate.scale(1.1), run_time=t_scale)
        # self.play(FadeIn(a_mobj, shift=UP), run_time=t_author)
        #
        # new: pick a random style and play it (we pass raw for better word-by-word timing)
        play_random_text_style(self, q_mobj, a_mobj, total_duration, raw_text=raw)

        # Timing
        # estimate text animation consumption as up to 60% of total_duration but not more than explicit sums
        time_text = min(total_duration * 0.6, (t_fadein + t_write + t_color + t_scale + t_author))
        # compute approximate background playback time (if using fast frame swaps it can be large; clamp to total_duration)
        time_bg = min(total_duration - time_text, max(0, (min(len(selected), max_fast_frames) - 1) * frame_display_time)) if selected else 0
        time_used = time_text + max(0, time_bg)
        remaining = total_duration - time_used
        if remaining > 1e-6:
            self.wait(remaining)
        else:
            logging.info(f"No remaining time to wait (remaining={remaining}); skipping self.wait().")


if __name__ == '__main__':
    # Optionally pre-extract before rendering (set env var AUTO_PREEXTRACT=1)
    if os.environ.get("AUTO_PREEXTRACT", "0") in ("1", "true", "yes"):
        if os.path.exists(EXPECTED_VIDEO):
            pre_extract_frames(EXPECTED_VIDEO, FRAMES_DIR, src_fps=60, tgt_fps=60, max_frames=600)
    pass

# $env:BG_QUERY="birds"
# manim -pql your_script.py AnimatedQuoteWithBackground

