from manim import *
from manim import config
import requests
import logging
import os
from io import BytesIO
from PIL import Image
import textwrap
from pydub import AudioSegment

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load API keys from environment variables
cat_api_key = os.environ.get("CAT_API_KEY")
voice_api_key = os.environ.get("VOICE_RSS_API_KEY")

# === BEGIN: Performance enhancements ===

# Base directory: directory where this script resides
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Default filenames
COOL_EFFECT_FILENAME = "subclip.ogg"
VOICEOVER_FILENAME = "voiceover.mp3"
CAT_IMAGE_FILENAME = "cat_image.jpg"

# Paths resolved relative to script
SOUND_PATH = os.path.join(BASE_DIR, COOL_EFFECT_FILENAME)
VOICEOVER_PATH = os.path.join(BASE_DIR, VOICEOVER_FILENAME)
CAT_IMAGE_PATH = os.path.join(BASE_DIR, CAT_IMAGE_FILENAME)

# Cache for voiceover to avoid repeated downloads
_voiceover_cached = None
# Cache the quote text for which voiceover was last fetched
_voiceover_cached_quote = None

def fetch_voiceover(quote, api_key):
    """Fetches voiceover for the given quote using VoiceRSS API, with caching tied to quote text."""
    global _voiceover_cached, _voiceover_cached_quote

    # If we have cached quote and it matches current quote, and file exists, reuse
    if _voiceover_cached_quote == quote and _voiceover_cached and os.path.exists(_voiceover_cached):
        logging.info("Reusing cached voiceover for the same quote")
        return _voiceover_cached

    # Otherwise: need to fetch a new voiceover
    # Remove old cached file if it exists
    if _voiceover_cached and os.path.exists(_voiceover_cached):
        try:
            os.remove(_voiceover_cached)
            logging.info("Removed previous cached voiceover file")
        except Exception as e:
            logging.warning(f"Could not remove old cached voiceover: {e}")
    # Also if VOICEOVER_PATH exists but was for a different quote, remove it
    if os.path.exists(VOICEOVER_PATH) and _voiceover_cached_quote != quote:
        try:
            os.remove(VOICEOVER_PATH)
            logging.info("Removed existing voiceover file on disk since quote changed")
        except Exception:
            pass

    _voiceover_cached = None
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
        # Save to VOICEOVER_PATH (overwrite if exists)
        with open(VOICEOVER_PATH, "wb") as f:
            f.write(response.content)
        logging.info(f"Downloaded new voiceover to {VOICEOVER_PATH}")
        _voiceover_cached = VOICEOVER_PATH
        _voiceover_cached_quote = quote
        return _voiceover_cached
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching voiceover: {e}")
    return None

# Cache for cat image so repeated runs reuse the image, but tied to quote
_cat_cached_quote = None

def fetch_cat_image(api_key, target_width=1280, target_height=720):
    """
    Fetches a random cat image from TheCatAPI and saves it locally.
    Caches as 'cat_image.jpg' in script directory if the quote hasn't changed;
    if the quote has changed since last fetch, removes old image and fetches new.
    """
    global _cat_cached_quote

    # Determine current quote text from global quote_data, if available
    current_quote = None
    try:
        # if quote_data has been set by fetch_quote earlier
        from __main__ import quote_data
        if isinstance(quote_data, dict):
            current_quote = quote_data.get("quote")
    except Exception:
        current_quote = None

    # If we have a cached image and quote hasn't changed, reuse
    if current_quote is not None and _cat_cached_quote == current_quote and os.path.exists(CAT_IMAGE_PATH):
        logging.info(f"Reusing existing cat image for same quote: {CAT_IMAGE_PATH}")
        return CAT_IMAGE_PATH

    # Otherwise: if an old image exists, remove it
    if os.path.exists(CAT_IMAGE_PATH) and (_cat_cached_quote is not None and _cat_cached_quote != current_quote):
        try:
            os.remove(CAT_IMAGE_PATH)
            logging.info("Removed previous cached cat image because quote changed")
        except Exception as e:
            logging.warning(f"Could not remove old cat image: {e}")

    # Fetch new cat image for the current quote (or first time)
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
                logging.info(f"Fetched and saved cat image to {CAT_IMAGE_PATH}")
                # Update cache key
                _cat_cached_quote = current_quote
                return CAT_IMAGE_PATH
            else:
                logging.error("No 'url' key found in the CatAPI response data.")
        else:
            logging.error("CatAPI response is not a valid list or is empty.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching cat image: {e}")
    return None

def get_audio_duration(audio_file):
    """Returns the duration (in seconds) of the given audio file, with error handling."""
    try:
        dur = len(AudioSegment.from_file(audio_file, format="mp3")) / 1000.0
        return dur
    except Exception as e:
        logging.warning(f"Could not get audio duration for {audio_file}: {e}")
        return None

def loop_sound(audio_file, target_duration):
    """
    Loops and trims an audio file to match the target duration, caching result.
    Returns path to looped file.
    """
    # Name for cached looped file
    base, _ = os.path.splitext(os.path.basename(audio_file))
    looped_name = f"looped_{base}_{int(target_duration)}s.mp3"
    looped_path = os.path.join(BASE_DIR, looped_name)

    # If exists and duration matches, reuse
    if os.path.exists(looped_path):
        dur = get_audio_duration(looped_path)
        if dur is not None and abs(dur - target_duration) < 0.1:
            logging.info(f"Reusing cached looped audio: {looped_name}")
            return looped_path
        else:
            try:
                os.remove(looped_path)
            except Exception:
                pass

    # Perform looping
    try:
        audio = AudioSegment.from_file(audio_file)
    except Exception as e:
        logging.error(f"Error loading audio file {audio_file}: {e}")
        return audio_file

    original_duration = len(audio) / 1000.0
    if original_duration <= 0:
        logging.warning(f"Original audio has zero length: {audio_file}")
        return audio_file
    loops_needed = int(target_duration / original_duration) + 1
    full_audio = audio * loops_needed
    trimmed_audio = full_audio[:int(target_duration * 1000)]
    try:
        trimmed_audio.export(looped_path, format="mp3")
        logging.info(f"Created cached looped audio: {looped_name}")
        return looped_path
    except Exception as e:
        logging.error(f"Failed exporting looped audio: {e}")
        return audio_file

def trim_audio(audio_file, max_duration=30):
    """
    Trims the given audio file to a maximum duration (in seconds).
    Caches the trimmed file.
    """
    base, _ = os.path.splitext(os.path.basename(audio_file))
    trimmed_name = f"trimmed_{base}_{int(max_duration)}s.mp3"
    trimmed_path = os.path.join(BASE_DIR, trimmed_name)

    # If exists and duration <= max_duration, reuse
    if os.path.exists(trimmed_path):
        dur = get_audio_duration(trimmed_path)
        if dur is not None and dur <= max_duration + 0.1:
            logging.info(f"Reusing cached trimmed audio: {trimmed_name}")
            return trimmed_path
        else:
            try:
                os.remove(trimmed_path)
            except Exception:
                pass

    # Perform trimming
    try:
        audio = AudioSegment.from_file(audio_file)
    except Exception as e:
        logging.error(f"Error loading audio file {audio_file}: {e}")
        return audio_file
    trimmed_audio = audio[:max_duration * 1000]
    try:
        trimmed_audio.export(trimmed_path, format="mp3")
        logging.info(f"Created cached trimmed audio: {trimmed_name}")
        return trimmed_path
    except Exception as e:
        logging.error(f"Failed exporting trimmed audio: {e}")
        return audio_file

# === END: Performance enhancements ===


def fetch_quote():
    """Fetches a random motivational quote from ZenQuotes API."""
    url = "https://zenquotes.io/api/random"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list) and data:
            return {"quote": data[0].get("q", "No quote found"), 
                    "author": data[0].get("a", "Unknown")}
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching quote: {e}")
    return {"quote": "No quote found", "author": "Unknown"}

def create_quote_mobjects(quote_text, quote_author, frame_width, frame_height):
    """Creates properly formatted text objects for the quote and author."""
    wrapped_quote = "\n".join(textwrap.wrap(quote_text, width=40))
    quote_mobject = Paragraph(wrapped_quote, alignment="center", line_spacing=0.6)
    quote_mobject.set_color_by_gradient(WHITE, YELLOW)
    quote_mobject.set_width(min(quote_mobject.width, frame_width * 0.8))
    quote_mobject.set_height(min(quote_mobject.height, frame_height * 0.5))
    author_mobject = Text(f"{quote_author}", font_size=24, color=YELLOW)
    return quote_mobject, author_mobject

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
        looped_effect = loop_sound(SOUND_PATH, target_duration=total_duration)
        self.add_sound(looped_effect, gain=-5)

    def apply_text_effects(self, quote_mobject, author_mobject, sync_duration=None):
        """
        Applies animation effects to both quote and author.
        If sync_duration is provided, the total run time of the sequence will be scaled to match.
        """
        durations = {
            "fadein_quote": sync_duration * 0.15 if sync_duration else 1,
            "write_quote": sync_duration * 0.5 if sync_duration else 2,
            "color_quote": sync_duration * 0.2 if sync_duration else 2,
            "scale_quote": sync_duration * 0.15 if sync_duration else 1,
            "fadein_author": sync_duration * 0.15 if sync_duration else 1.5,
        }
        
        self.play(
            FadeIn(quote_mobject, shift=UP, scale=1.2),
            run_time=durations["fadein_quote"]
        )
        self.play(
            Write(quote_mobject),
            run_time=durations["write_quote"]
        )
        self.play(
            quote_mobject.animate.set_color_by_gradient(YELLOW, ORANGE),
            run_time=durations["color_quote"]
        )
        self.play(
            quote_mobject.animate.scale(1.05),
            run_time=durations["scale_quote"] 
        )
        self.play(
            FadeIn(author_mobject, shift=UP),
            run_time=durations["fadein_author"]
        )

class AnimatedQuoteWithBackground(BaseQuoteScene):
    """Scene with a cat background, continuous sound effects, and a voiceover synchronized with the quote animation."""
    
    def construct(self):
        # 1. Fetch the quote and voiceover immediately
        quote_data = fetch_quote()
        quote_text = f"\"{quote_data['quote']}\""
        quote_author = f"- {quote_data['author']}"
        
        # Fetch the voiceover and determine its duration (do not trim)
        audio_file = fetch_voiceover(quote_text, voice_api_key)
        if audio_file:
            voiceover_duration = get_audio_duration(audio_file)
            total_duration = voiceover_duration or 7
            # Immediately add the voiceover sound so it starts with the animation
            self.add_sound(audio_file, gain=+20)
        else:
            total_duration = 7  # fallback duration
            voiceover_duration = total_duration
        
        # 2. Immediately start the background sound effect for the full duration
        looped_effect = loop_sound(SOUND_PATH, target_duration=total_duration)
        self.add_sound(looped_effect, gain=+5)
        
        # 3. Set up background visuals immediately (avoid waiting with long animations)
        # Instead of a long background animation, add a static background or use a very short transition.
        background = Rectangle(width=config.frame_width, height=config.frame_height)
        background.set_color_by_gradient(BLUE, PURPLE, RED)
        self.add(background)
        
        # (Optional) If you want a subtle background color change concurrently, you can animate it with a short run_time:
        self.play(background.animate.set_color_by_gradient(GREEN, BLUE), run_time=0.5)
        
        # 4. Fetch and add the cat image as a background element
        image_path = fetch_cat_image(cat_api_key)
        if image_path:
            bg_image = ImageMobject(image_path).scale_to_fit_width(self.camera.frame_width)
            self.add(bg_image)
        
        # 5. Create and position the text mobjects immediately
        quote_mobject, author_mobject = create_quote_mobjects(
            quote_text, quote_author, self.camera.frame_width, self.camera.frame_height
        )
        quote_mobject.move_to(UP * 0.5)
        author_mobject.next_to(quote_mobject, DOWN, buff=0.5)
        
        # 6. Start the text animation immediately, synchronizing its segments with the voiceover duration
        self.apply_text_effects(quote_mobject, author_mobject, sync_duration=voiceover_duration)
        
        # 7. Wait for the full duration of the scene so the voiceover and all animations can play completely.
        self.wait(total_duration)
