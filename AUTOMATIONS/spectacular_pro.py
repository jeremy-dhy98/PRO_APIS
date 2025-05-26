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
    return len(AudioSegment.from_file(audio_file, format="mp3")) / 1000.0

def loop_sound(audio_file, target_duration):
    """Loops and trims an audio file to match the target duration."""
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
    audio = AudioSegment.from_file(audio_file)
    trimmed_audio = audio[:max_duration * 1000]  # Trim to max_duration seconds
    trimmed_path = "trimmed_" + os.path.basename(audio_file)
    trimmed_audio.export(trimmed_path, format="mp3")
    return trimmed_path


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
            total_duration = voiceover_duration
            # Immediately add the voiceover sound so it starts with the animation
            self.add_sound(audio_file, gain=+20)
        else:
            total_duration = 7  # fallback duration
            voiceover_duration = total_duration
        
        # 2. Immediately start the background sound effect for the full duration
        looped_effect = loop_sound(cool_effect_file, target_duration=total_duration)
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


# ADVANCED SYNCHING #

# class AnimatedQuoteWithBackground(BaseQuoteScene):
#     """Scene with a cat background, continuous sound effects, and a voiceover synchronized with the quote animation."""
    
#     def construct(self):
#         # 1. Apply background visual effects.
#         self.apply_background_effects()
        
#         # 2. Fetch and display the cat image as background.
#         image_path = fetch_cat_image(cat_api_key)
#         if image_path:
#             bg_image = ImageMobject(image_path).scale_to_fit_width(self.camera.frame_width)
#             self.add(bg_image)
        
#         # 3. Fetch the quote and create text mobjects.
#         quote_data = fetch_quote()
#         quote_text = f"\"{quote_data['quote']}\""
#         quote_author = f"- {quote_data['author']}"
#         quote_mobject, author_mobject = create_quote_mobjects(
#             quote_text, quote_author, self.camera.frame_width, self.camera.frame_height
#         )
#         quote_mobject.move_to(UP * 0.5)
#         author_mobject.next_to(quote_mobject, DOWN, buff=0.5)
        
#         # 4. Fetch the voiceover audio for the quote.
#         #    Do NOT trim the audio; use its full duration.
#         audio_file = fetch_voiceover(quote_text, voice_api_key)
#         if audio_file:
#             voiceover_duration = get_audio_duration(audio_file)
#             # Set the scene's total duration to the voiceover's length.
#             total_duration = voiceover_duration
#             # Add the voiceover audio to play in sync.
#             self.add_sound(audio_file, gain=+20)
#         else:
#             # Fallback duration in case of failure.
#             total_duration = 10
#             voiceover_duration = total_duration
        
#         # 5. Loop the background effect sound for the full duration of the voiceover.
#         self.apply_audio_effects(total_duration)
        
#         # 6. Animate the text, distributing the animations over the voiceover's duration.
#         self.apply_text_effects(quote_mobject, author_mobject, sync_duration=voiceover_duration)
        
#         # 7. No extra waiting is necessary, as the scene's duration exactly matches the voiceover.
#         self.wait(total_duration)

