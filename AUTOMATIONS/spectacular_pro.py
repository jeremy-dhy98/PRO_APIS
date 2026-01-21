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

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load API keys from environment variables
cat_api_key = os.environ.get("CAT_API_KEY")
voice_api_key = os.environ.get("VOICE_RSS_API_KEY")

# Define effect sound file (ensure this file exists)
cool_effect_file = "subclip.ogg"

def fetch_quote():
    """Fetches a random motivational quote from ZenQuotes API."""
    url = "https://zenquotes.io/api/random"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list) and data:
            return {"quote": data[0].get("q", "No quote found"), 
                    "author": data[0].get("a", "Unknown")}
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching quote: {e}")
    return {"quote": "No quote found", "author": "Unknown"}

def fetch_cat_image(api_key, target_width=1280, target_height=720):
    """
    Fetches a random cat image from TheCatAPI and saves it locally.
    """
    url = "https://api.thecatapi.com/v1/images/search"
    headers = {"x-api-key": api_key}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list) and data:
            if "url" in data[0]:
                image_url = data[0]["url"]
                response = requests.get(image_url)
                response.raise_for_status()
                img = Image.open(BytesIO(response.content))
                img = img.convert("RGB")
                img.save("cat_image.jpg")
                return "cat_image.jpg"
            else:
                logging.error("No 'url' key found in the response data.")
        else:
            logging.error("API response is not a valid list or is empty.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching cat image: {e}")
    return None

def fetch_voiceover(quote, api_key):
    """Fetches voiceover for the given quote using VoiceRSS API."""
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
        response = requests.get(url, params=params)
        response.raise_for_status()
        file_path = "voiceover.mp3"
        with open(file_path, "wb") as f:
            f.write(response.content)
        return file_path
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching voiceover: {e}")
    return None

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
    if not os.path.exists(audio_file):
        return 0.0
    return len(AudioSegment.from_file(audio_file, format="mp3")) / 1000.0

def loop_sound(audio_file, target_duration):
    """Loops and trims an audio file to match the target duration."""
    if not os.path.exists(audio_file):
        logging.warning(f"Audio file {audio_file} not found. Skipping background sound.")
        return None
    audio = AudioSegment.from_file(audio_file)
    full_audio = (audio * (int(target_duration / (len(audio) / 1000)) + 1))[:int(target_duration * 1000)]
    looped_path = "looped_effect.mp3"
    full_audio.export(looped_path, format="mp3")
    return looped_path

def trim_audio(audio_file, max_duration=30):
    """
    Trims the given audio file to a maximum duration (in seconds).
    Returns the path to the trimmed audio file.
    """
    if not os.path.exists(audio_file):
        return None
    audio = AudioSegment.from_file(audio_file)
    trimmed_audio = audio[:max_duration * 1000]  # Trim to max_duration seconds
    trimmed_path = "trimmed_" + os.path.basename(audio_file)
    trimmed_audio.export(trimmed_path, format="mp3")
    return trimmed_path

# ---------------------
# Randomized text animation styles (INTEGRATED)
# ---------------------
def _glowify(mobj, layers=3, scale_step=1.04, opacity_step=0.12):
    """
    Create a subtle glow by stacking slightly larger, low-opacity copies behind.
    Returns a VGroup (glow layers + original) or original on failure.
    """
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
    """Classic handwriting reveal using Write, with a safe fallback."""
    scene.add(quote_mobject)
    run = min(sync_duration * 0.6, 4.0) if sync_duration else 2.0
    try:
        scene.play(Write(quote_mobject), run_time=run)
    except Exception:
        scene.play(FadeIn(quote_mobject), run_time=min(1.2, run))
    scene.play(FadeIn(author_mobject), run_time=0.8)

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

def style_kinetic(scene, quote_mobject, author_mobject, sync_duration=None, raw_text=None):
    """Write then a quick color/scale pulse for emphasis."""
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
    """Pop-in with a quick bounce and color shift."""
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
    """Apply layered glow copies to create a neon effect and fade in."""
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
    """
    Choose a random polished style and play it.
    Optionally supply raw_text (string) to help word-by-word style.
    """
    style = random.choice(_ANIM_STYLES)
    logging.info(f"Selected text animation style: {style.__name__}")
    try:
        style(scene, quote_mobject, author_mobject, sync_duration=sync_duration, raw_text=raw_text)
    except Exception as e:
        logging.warning(f"Selected style {style.__name__} failed: {e}. Falling back to simple fade.")
        scene.add(quote_mobject)
        scene.play(FadeIn(quote_mobject), run_time=min(1.2, sync_duration * 0.2) if sync_duration else 1.0)
        scene.play(FadeIn(author_mobject), run_time=0.7)

    # Small accent occasionally
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
        """
        Applies animation effects to both quote and author.
        If sync_duration is provided, the total run time of the sequence will be scaled to match.
        """
        # Instead of a single static sequence, pick a polished randomized style that respects sync_duration.
        # We pass the raw text (if available) to help the word-by-word style perform reliably.
        raw_text = None
        try:
            # Try to extract raw text from the Paragraph/Text if possible
            if hasattr(quote_mobject, "get_text"):
                raw_text = quote_mobject.get_text()
            elif hasattr(quote_mobject, "text"):
                raw_text = quote_mobject.text
        except Exception:
            raw_text = None

        # Delegate to the randomized style player (defensive; will fallback to fades on error)
        play_random_text_style(self, quote_mobject, author_mobject, sync_duration=sync_duration, raw_text=raw_text)


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
            total_duration = voiceover_duration
            # Immediately add the voiceover sound so it starts with the animation
            self.add_sound(audio_file, gain=+20)
        else:
            total_duration = 7  # fallback duration
            voiceover_duration = total_duration
        
        # 2. Immediately start the background sound effect for the full duration
        looped_effect = loop_sound(cool_effect_file, target_duration=total_duration)
        if looped_effect:
            self.add_sound(looped_effect, gain=+5)
        
        # 3. Set up background visuals immediately (avoid waiting with long animations)
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
