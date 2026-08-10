from manim import *
from manim import config 
import requests
import logging
import random
import os
from io import BytesIO
from PIL import Image
import textwrap
from pydub import AudioSegment
import imageio_ffmpeg

# ==========================================
# FOLDER PATH CONFIGURATIONS
# ==========================================
# Default base directory for the original media output
DEFAULT_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Target directory for the new enhancement media output
ENHANCEMENT_DIR = r"C:\Users\Jeremy\Desktop\StellarViewsDaily"
os.makedirs(ENHANCEMENT_DIR, exist_ok=True)

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Resolve default paths relative to the script location
BASE_DIR = DEFAULT_BASE_DIR

# Load API keys from environment variables and safely strip hidden whitespace characters
cat_api_key = os.environ.get("CAT_API_KEY", "").strip() or None
voice_api_key = os.environ.get("VOICE_RSS_API_KEY", "").strip() or None

# Define effect sound file (ensure this file exists)
cool_effect_file = os.path.join(BASE_DIR, "subclip.ogg")
VOICEOVER_FILE = os.path.join(BASE_DIR, "voiceover.mp3")
CAT_IMAGE_FILE = os.path.join(BASE_DIR, "cat_image.jpg")
LOOPED_EFFECT_FILE = os.path.join(BASE_DIR, "looped_effect.mp3")
TRIMMED_EFFECT_FILE = os.path.join(BASE_DIR, "trimmed_voiceover.mp3")
SILENT_FALLBACK_FILE = os.path.join(BASE_DIR, "silent_fallback.mp3")

# ==========================================
# ROBUST WINDOWS FFmpeg & FFPROBE CONFIGURATION
# ==========================================
try:
    # Extract the exact binary path provided by imageio_ffmpeg
    FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
    FFMPEG_DIR = os.path.dirname(FFMPEG_EXE)
    
    # Push this directory to the front of the local execution PATH environment 
    # This ensures Windows 'where' commands and pydub sub-processes catch both ffmpeg and ffprobe
    os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")
    os.environ["IMAGEIO_FFMPEG_EXE"] = FFMPEG_EXE
    
    # Explicitly wire paths directly into pydub configurations
    AudioSegment.converter = FFMPEG_EXE
    
    # Map out the corresponding ffprobe executable name depending on platform
    ffprobe_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    FFPROBE_EXE = os.path.join(FFMPEG_DIR, ffprobe_name)
    
    if os.path.exists(FFPROBE_EXE):
        AudioSegment.ffprobe = FFPROBE_EXE
        logging.info(f"Successfully pinned FFmpeg & FFprobe via imageio: {FFMPEG_DIR}")
    else:
        logging.warning("FFmpeg binary found, but ffprobe was missing in imageio binaries directory.")
        
except Exception as e:
    logging.warning(f"Failed to dynamically configure FFmpeg path variables: {e}")

def _create_silent_audio(duration_seconds, out_path=SILENT_FALLBACK_FILE):
    """Create a silent mp3 file for fallback use."""
    duration_seconds = max(0.5, float(duration_seconds))
    ms = int(duration_seconds * 1000)
    silent = AudioSegment.silent(duration=ms)
    silent.export(out_path, format="mp3")
    return out_path

def fetch_quote():
    """Fetches a random motivational quote from ZenQuotes API with explicit user-agent header."""
    url = "https://zenquotes.io/api/random"
    # Added a standard browser user-agent header to reduce risk of connection dropouts/blocks
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # Premium local fallbacks in case network connection fails or times out completely
    local_fallbacks = [
        {"quote": "The only way to do great work is to love what you do.", "author": "Steve Jobs"},
        {"quote": "Code is like humor. When you have to explain it, it’s bad.", "author": "Cory House"},
        {"quote": "Simplicity is the soul of efficiency.", "author": "Austin Freeman"},
        {"quote": "Before software can be reusable it first has to be usable.", "author": "Ralph Johnson"},
        {"quote": "Make it work, make it right, make it fast.", "author": "Kent Beck"}
    ]
    
    try:
        response = requests.get(url, headers=headers, timeout=8)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list) and data:
            return {"quote": data[0].get("q", "No quote found"),
                    "author": data[0].get("a", "Unknown")}
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching quote via API: {e}. Utilizing premium local backup context.")
        
    return random.choice(local_fallbacks)

def fetch_education_quote():
    """Fetches a curated quote specifically about education and related categories."""
    url = "https://zenquotes.io/api/quotes"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    education_keywords = ["education", "learn", "knowledge", "teach", "mind", "wisdom", "study", "growth", "book", "school"]
    education_fallbacks = [
        {"quote": "Education is the most powerful weapon which you can use to change the world.", "author": "Nelson Mandela"},
        {"quote": "An investment in knowledge pays the best interest.", "author": "Benjamin Franklin"},
        {"quote": "Live as if you were to die tomorrow. Learn as if you were to live forever.", "author": "Mahatma Gandhi"}
    ]
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list) and data:
            matching_quotes = []
            for item in data:
                q_text = item.get("q", "").lower()
                if any(kw in q_text for kw in education_keywords):
                    matching_quotes.append({"quote": item.get("q"), "author": item.get("a", "Unknown")})
            if matching_quotes:
                return random.choice(matching_quotes)
    except Exception as e:
        logging.error(f"Error fetching education quote: {e}")
    return random.choice(education_fallbacks)

def fetch_cat_image(api_key, target_width=1280, target_height=720):
    """
    Fetches a random cat image from TheCatAPI and saves it locally.
    """
    if not api_key:
        logging.warning("CAT_API_KEY is missing or invalid. Skipping background image.")
        return None

    url = "https://api.thecatapi.com/v1/images/search"
    headers = {"x-api-key": api_key}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list) and data:
            if "url" in data[0]:
                image_url = data[0]["url"]
                response = requests.get(image_url, timeout=20)
                response.raise_for_status()
                img = Image.open(BytesIO(response.content))
                img = img.convert("RGB")
                img.save(CAT_IMAGE_FILE)
                return CAT_IMAGE_FILE
            else:
                logging.error("No 'url' key found in the response data.")
        else:
            logging.error("API response is not a valid list or is empty.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching cat image: {e}")
    except Exception as e:
        logging.error(f"Error processing cat image: {e}")
    return None

def fetch_voiceover(quote, api_key):
    """Fetches voiceover for the given quote using VoiceRSS API."""
    if not api_key:
        logging.warning("VOICE_RSS_API_KEY is not set; using silent fallback voiceover.")
        return _create_silent_audio(4, out_path=VOICEOVER_FILE)

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
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()

        ct = response.headers.get("Content-Type", "")
        if "audio" not in ct.lower() and not response.content.startswith(b"ID3"):
            logging.error(f"VoiceRSS returned non-audio content ({ct}); using silent fallback. Payload: {response.text[:100]}")
            return _create_silent_audio(4, out_path=VOICEOVER_FILE)

        if len(response.content) < 1000:
            logging.warning("Voiceover payload is suspiciously small; using silent fallback.")
            return _create_silent_audio(4, out_path=VOICEOVER_FILE)

        with open(VOICEOVER_FILE, "wb") as f:
            f.write(response.content)
        return VOICEOVER_FILE
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching voiceover: {e}")
    except Exception as e:
        logging.error(f"Error saving voiceover: {e}")

    return _create_silent_audio(4, out_path=VOICEOVER_FILE)

def create_quote_mobjects(quote_text, quote_author, frame_width, frame_height):
    """Creates properly formatted text objects for the quote and author."""
    wrapped_quote = "\n".join(textwrap.wrap(quote_text, width=40))
    quote_mobject = Paragraph(wrapped_quote, alignment="center", line_spacing=0.6)
    quote_mobject.set_color_by_gradient(WHITE, YELLOW)
    quote_mobject.set_width(min(quote_mobject.width, frame_width * 0.8))
    quote_mobject.set_height(min(quote_mobject.height, frame_height * 0.5))
    author_mobject = Text(f"{quote_author}", font_size=24, color=YELLOW)
    return quote_mobject, author_mobject

def get_audio_duration(audio_file):
    """Returns the duration (in seconds) of the given audio file."""
    if not audio_file or not os.path.exists(audio_file):
        return 0.0
    try:
        audio = AudioSegment.from_file(audio_file)
        return len(audio) / 1000.0
    except Exception as e:
        logging.warning(f"Could not measure audio duration for {audio_file}: {e}")
        return 0.0

def loop_sound(audio_file, target_duration):
    """Loops and trims an audio file to match the target duration."""
    if not audio_file or not os.path.exists(audio_file):
        logging.warning(f"Audio file {audio_file} not found. Using silent fallback.")
        return _create_silent_audio(target_duration, out_path=LOOPED_EFFECT_FILE)
    try:
        audio = AudioSegment.from_file(audio_file)
        original_len = len(audio) / 1000.0
        if original_len <= 0:
            logging.warning(f"Original audio has zero length: {audio_file}. Using silent fallback.")
            return _create_silent_audio(target_duration, out_path=LOOPED_EFFECT_FILE)
        full_audio = (audio * (int(target_duration / original_len) + 1))[:int(target_duration * 1000)]
        full_audio.export(LOOPED_EFFECT_FILE, format="mp3")
        return LOOPED_EFFECT_FILE
    except Exception as e:
        logging.warning(f"loop_sound failed for {audio_file}: {e}. Using silent fallback.")
        return _create_silent_audio(target_duration, out_path=LOOPED_EFFECT_FILE)

def trim_audio(audio_file, max_duration=30):
    """
    Trims the given audio file to a maximum duration (in seconds).
    Returns the path to the trimmed audio file.
    """
    if not audio_file or not os.path.exists(audio_file):
        logging.warning(f"trim_audio: input audio file does not exist: {audio_file}")
        return _create_silent_audio(min(max_duration, 4), out_path=TRIMMED_EFFECT_FILE)
    try:
        audio = AudioSegment.from_file(audio_file)
        trimmed_audio = audio[:int(max_duration * 1000)]  # Trim to max_duration seconds
        trimmed_audio.export(TRIMMED_EFFECT_FILE, format="mp3")
        return TRIMMED_EFFECT_FILE
    except Exception as e:
        logging.warning(f"trim_audio failed for {audio_file}: {e}. Using silent fallback.")
        return _create_silent_audio(min(max_duration, 4), out_path=TRIMMED_EFFECT_FILE)

# ---------------------
# Randomized text animation styles
# ---------------------
def _glowify(mobj, layers=3, scale_step=1.04, opacity_step=0.12):
    layers_list = []
    for i in range(layers, 0, -1):
        try:
            copy = mobj.copy()
            copy.set_opacity(max(0.02, opacity_step * i))
            copy.scale(scale_step * (1 + (i * 0.01)))
            layers_list.append(copy)
        except Exception:
            continue
    try:
        layers_list.append(mobj)
        return VGroup(*layers_list)
    except Exception:
        return mobj

def style_handwriting(scene, quote_mobject, author_mobject, sync_duration=None, raw_text=None):
    scene.add(quote_mobject)
    run = min(sync_duration * 0.6, 4.0) if sync_duration else 2.0
    try:
        scene.play(Write(quote_mobject), run_time=run)
    except Exception:
        scene.play(FadeIn(quote_mobject), run_time=min(1.2, run))
    scene.play(FadeIn(author_mobject), run_time=0.8)

def style_wordbyword(scene, q_mobj, a_mobj, sync_duration=None, raw_text=None, **kwargs):
    total_duration = sync_duration or 5.0
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
        scene.add(q_mobj)
        scene.play(FadeIn(q_mobj), run_time=min(1.0, total_duration * 0.2))
        scene.play(FadeIn(a_mobj), run_time=0.7)
        return

    words = [w for w in text_source.split(" ") if w.strip()]
    if not words:
        scene.add(q_mobj)
        scene.play(FadeIn(q_mobj), run_time=min(1.0, total_duration * 0.2))
        scene.play(FadeIn(a_mobj), run_time=0.7)
        return

    try:
        preferred_width = getattr(q_mobj, "width", 0) or 0
        max_width = min(preferred_width if preferred_width > 0 else scene.camera.frame_width * 0.8,
                        scene.camera.frame_width * 0.9)
    except Exception:
        max_width = scene.camera.frame_width * 0.9

    base_font = 40
    try:
        base_font = getattr(q_mobj, "font_size", base_font) or base_font
    except Exception:
        pass

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

        current_line.add(wm)
        try:
            current_line.arrange(RIGHT, buff=spacing)
            if current_line.width > max_width:
                current_line.remove(wm)
                lines.append(current_line)
                current_line = VGroup()
                current_line.add(wm)
                try:
                    current_line.arrange(RIGHT, buff=spacing)
                except Exception:
                    pass
        except Exception:
            pass

    if len(current_line) > 0:
        lines.append(current_line)

    if not lines:
        scene.add(q_mobj)
        scene.play(FadeIn(q_mobj), run_time=min(1.0, total_duration * 0.2))
        scene.play(FadeIn(a_mobj), run_time=0.7)
        return

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

    scene.add(lines_group)

    ordered_words = []
    for ln in lines:
        for sub in ln:
            ordered_words.append(sub)

    run_words = max(1.0, min(total_duration * 0.55, 6.0))
    lag_ratio = 0.12 if len(ordered_words) < 12 else 0.06

    try:
        scene.play(
            LaggedStart(*[FadeIn(w, shift=UP, scale=0.95) for w in ordered_words], lag_ratio=lag_ratio),
            run_time=run_words,
        )
    except Exception:
        scene.play(FadeIn(lines_group), run_time=min(1.2, run_words))

    try:
        scene.play(FadeIn(a_mobj, shift=UP), run_time=0.7)
    except Exception:
        scene.add(a_mobj)

def style_mask_reveal(scene, quote_mobject, author_mobject, sync_duration=None, raw_text=None):
    try:
        scene.add(quote_mobject)
    except Exception:
        pass

    try:
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
        center_pt = quote_mobject.get_center() if hasattr(quote_mobject, "get_center") else ORIGIN
        center_y = float(center_pt[1]) if hasattr(center_pt, "__len__") else 0.0
        width = scene.camera.frame_width * 0.7
        height = scene.camera.frame_height * 0.35
        left_x = -width / 2 + float(center_pt[0]) if hasattr(center_pt, "__len__") else -width / 2

    n_shards = 8
    try:
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
            x = left_x + shard_w * (i + 0.5)
            shard.move_to(RIGHT * x + UP * center_y)
            try:
                shard.set_z_index(1000)
            except Exception:
                pass
            scene.add(shard)
            shards.append(shard)
        except Exception:
            continue

    total_shard_time = min(sync_duration * 0.35, 1.2) if sync_duration else 0.9
    lag_ratio = 0.08

    anims = []
    for idx, shard in enumerate(shards):
        try:
            side = -1 if idx < (len(shards) / 2) else 1
            angle_deg = side * (random.uniform(18, 55))
            angle = angle_deg * DEGREES
            horiz_shift = side * scene.camera.frame_width * random.uniform(0.8, 1.3)
            vert_shift = scene.camera.frame_height * random.uniform(-0.25, 0.25)
            shift_vec = RIGHT * horiz_shift + UP * vert_shift
            anim = shard.animate.rotate(angle).shift(shift_vec)
            anims.append(anim)
        except Exception:
            anims.append(FadeOut(shard))

    try:
        scene.play(LaggedStart(*anims, lag_ratio=lag_ratio), run_time=max(0.6, total_shard_time))
    except Exception:
        try:
            scene.play(LaggedStart(*[FadeOut(s) for s in shards], lag_ratio=lag_ratio), run_time=0.8)
        except Exception:
            pass

    for s in shards:
        try:
            scene.remove(s)
        except Exception:
            pass

    try:
        scene.play(FadeIn(author_mobject), run_time=0.7)
    except Exception:
        try:
            scene.add(author_mobject)
        except Exception:
            pass

def style_kinetic(scene, quote_mobject, author_mobject, sync_duration=None, raw_text=None):
    scene.add(quote_mobject)
    run = min(sync_duration * 0.45, 3.0) if sync_duration else 2.0
    try:
        scene.play(Write(quote_mobject), run_time=run)
    except Exception:
        scene.play(FadeIn(quote_mobject), run_time=min(1.0, run))
    try:
        scene.play(quote_mobject.animate.scale(1.06).set_color_by_gradient(BLUE, PURPLE), run_time=0.45)
        scene.play(quote_mobject.animate.scale(1/1.06).set_color_by_gradient(WHITE, YELLOW), run_time=0.35)
    except Exception:
        pass
    scene.play(FadeIn(author_mobject), run_time=0.6)

def style_pop_and_bounce(scene, quote_mobject, author_mobject, sync_duration=None, raw_text=None):
    q_copy = quote_mobject.copy()
    q_copy.scale(0.85)
    scene.add(q_copy)
    try:
        scene.play(FadeIn(q_copy), run_time=0.4)
        scene.play(q_copy.animate.scale(1.12).set_color_by_gradient(YELLOW, ORANGE), run_time=0.5)
        scene.play(q_copy.animate.scale(1/1.12), run_time=0.35)
    except Exception:
        scene.play(FadeIn(q_copy), run_time=0.9)
    scene.play(FadeIn(author_mobject), run_time=0.6)
    try:
        scene.remove(quote_mobject)
        scene.add(q_copy)
    except Exception:
        pass

def style_neon_glow(scene, quote_mobject, author_mobject, sync_duration=None, raw_text=None):
    glow = _glowify(quote_mobject, layers=3)
    try:
        glow.move_to(quote_mobject.get_center())
        scene.add(glow)
        scene.play(FadeIn(glow, shift=DOWN), run_time=min(sync_duration * 0.6, 3.5) if sync_duration else 1.5)
    except Exception:
        scene.add(quote_mobject)
        scene.play(FadeIn(quote_mobject), run_time=min(1.2, sync_duration * 0.4) if sync_duration else 1.0)
    scene.play(FadeIn(author_mobject), run_time=0.6)

_ANIM_STYLES = [
    style_handwriting,
    style_wordbyword,
    style_mask_reveal,
    style_kinetic,
    style_pop_and_bounce,
    style_neon_glow,
]

def play_random_text_style(scene, quote_mobject, author_mobject, sync_duration=None, raw_text=None):
    style = random.choice(_ANIM_STYLES)
    logging.info(f"Selected text animation style: {style.__name__}")
    try:
        style(scene, quote_mobject, author_mobject, sync_duration=sync_duration, raw_text=raw_text)
    except Exception as e:
        logging.warning(f"Selected style {style.__name__} failed: {e}. Falling back to simple fade.")
        scene.add(quote_mobject)
        scene.play(FadeIn(quote_mobject), run_time=min(1.2, sync_duration * 0.2) if sync_duration else 1.0)
        scene.play(FadeIn(author_mobject), run_time=0.7)

    if random.random() < 0.35:
        try:
            left = quote_mobject.get_left()
            right = quote_mobject.get_right()
            underline = Line(left + DOWN * 0.22, right + DOWN * 0.22, stroke_width=3)
            underline.set_opacity(0.0)
            scene.add(underline)
            scene.play(underline.animate.set_opacity(1.0), run_time=0.5)
            scene.play(FadeOut(underline), run_time=0.4)
        except Exception:
            pass

# ---------------------
# End randomized style integration
# ---------------------

class BaseQuoteScene(Scene):
    """Base class to apply consistent visual and audio effects to all scenes."""
    
    def apply_background_effects(self):
        """Applies a gradient background transition."""
        background = Rectangle(width=config.frame_width, height=config.frame_height)
        background.set_color_by_gradient(BLUE, PURPLE, RED)
        self.add(background)
        self.play(background.animate.set_color_by_gradient(GREEN, BLUE), run_time=3)
        return background

    def apply_audio_effects(self, total_duration):
        """Loops background audio for the entire scene duration."""
        looped_effect = loop_sound(cool_effect_file, target_duration=total_duration)
        if looped_effect:
            self.add_sound(looped_effect, gain=-5)

    def apply_text_effects(self, quote_mobject, author_mobject, sync_duration=None):
        raw_text = None
        try:
            if hasattr(quote_mobject, "get_text"):
                raw_text = quote_mobject.get_text()
            elif hasattr(quote_mobject, "text"):
                raw_text = quote_mobject.text
        except Exception:
            raw_text = None

        play_random_text_style(self, quote_mobject, author_mobject, sync_duration=sync_duration, raw_text=raw_text)

class AnimatedQuoteWithBackground(BaseQuoteScene):
    """Scene with a cat background, continuous sound effects, and a voiceover synchronized with the quote animation."""
    
    def construct(self):
        quote_data = fetch_quote()
        quote_text = f"\"{quote_data['quote']}\""
        quote_author = f"- {quote_data['author']}"
        
        audio_file = fetch_voiceover(quote_text, voice_api_key)
        if audio_file and os.path.exists(audio_file):
            voiceover_duration = get_audio_duration(audio_file)
            total_duration = voiceover_duration if voiceover_duration and voiceover_duration > 0 else 7
            self.add_sound(audio_file, gain=+20)
        else:
            total_duration = 7
            voiceover_duration = total_duration
        
        looped_effect = loop_sound(cool_effect_file, target_duration=total_duration)
        if looped_effect and os.path.exists(looped_effect):
            self.add_sound(looped_effect, gain=+5)
        else:
            logging.info("No background sound available; continuing without it.")
        
        background = Rectangle(width=config.frame_width, height=config.frame_height)
        background.set_color_by_gradient(BLUE, PURPLE, RED)
        self.add(background)
        
        self.play(background.animate.set_color_by_gradient(GREEN, BLUE), run_time=0.5)
        
        image_path = fetch_cat_image(cat_api_key)
        if image_path and os.path.exists(image_path):
            bg_image = ImageMobject(image_path).scale_to_fit_width(self.camera.frame_width)
            self.add(bg_image)
        
        quote_mobject, author_mobject = create_quote_mobjects(
            quote_text, quote_author, self.camera.frame_width, self.camera.frame_height
        )
        quote_mobject.move_to(UP * 0.5)
        author_mobject.next_to(quote_mobject, DOWN, buff=0.5)
        
        self.apply_text_effects(quote_mobject, author_mobject, sync_duration=voiceover_duration)
        
        self.wait(total_duration)

class EducationCatQuoteScene(BaseQuoteScene):
    """New enhancement scene: Curated education quote overlaying a popular cat image background."""
    
    def construct(self):
        quote_data = fetch_education_quote()
        quote_text = f"\"{quote_data['quote']}\""
        quote_author = f"- {quote_data['author']}"
        
        audio_file = fetch_voiceover(quote_text, voice_api_key)
        if audio_file and os.path.exists(audio_file):
            voiceover_duration = get_audio_duration(audio_file)
            total_duration = voiceover_duration if voiceover_duration and voiceover_duration > 0 else 7
            self.add_sound(audio_file, gain=+20)
        else:
            total_duration = 7
            voiceover_duration = total_query_duration = total_duration
        
        looped_effect = loop_sound(cool_effect_file, target_duration=total_duration)
        if looped_effect and os.path.exists(looped_effect):
            self.add_sound(looped_effect, gain=5)
        else:
            logging.info("No background sound available; continuing without it.")
        
        background = Rectangle(width=config.frame_width, height=config.frame_height)
        background.set_color_by_gradient(BLUE, PURPLE, RED)
        self.add(background)
        
        self.play(background.animate.set_color_by_gradient(GREEN, BLUE), run_time=0.5)
        
        image_path = fetch_cat_image(cat_api_key)
        if image_path and os.path.exists(image_path):
            bg_image = ImageMobject(image_path).scale_to_fit_width(self.camera.frame_width)
            self.add(bg_image)
        
        quote_mobject, author_mobject = create_quote_mobjects(
            quote_text, quote_author, self.camera.frame_width, self.camera.frame_height
        )
        quote_mobject.move_to(UP * 0.5)
        author_mobject.next_to(quote_mobject, DOWN, buff=0.5)
        
        self.apply_text_effects(quote_mobject, author_mobject, sync_duration=voiceover_duration)
        
        self.wait(total_duration)

if __name__ == '__main__':
    pass