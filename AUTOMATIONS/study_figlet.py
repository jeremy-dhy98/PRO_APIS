from manim import *
from manim import config
import requests
import logging
import pyfiglet
import os
import textwrap
from pydub import AudioSegment

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Global variables to store fetched data (avoiding redundant calls)
quote_data = None
voiceover_file = None

voice_api_key = os.environ.get("VOICE_RSS_API_KEY")

def fetch_quote():
    """Fetches a random motivational quote from ZenQuotes API."""
    global quote_data
    if quote_data is not None:
        return quote_data

    url = "https://zenquotes.io/api/random"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        logging.info(f"Fetched data: {data}")
        if isinstance(data, list) and data:
            quote_data = {"quote": data[0].get("q", "No quote found"),
                          "author": data[0].get("a", "Unknown")}
            return quote_data
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching quote: {e}")
    
    quote_data = {"quote": "No quote found", "author": "Unknown"}
    return quote_data

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
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        file_path = "voiceover.mp3"
        with open(file_path, "wb") as f:
            f.write(response.content)
        return file_path
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching voiceover: {e}")
    return None

def get_audio_duration(audio_file):
    """Returns the duration (in seconds) of the given audio file."""
    return len(AudioSegment.from_file(audio_file, format="mp3")) / 1000.0

# class AnimatedQuoteWithASCII(Scene):
#     def construct(self):
#         # Fetch the quote
#         quote_info = fetch_quote()
#         quote_text = quote_info['quote']
        
#         # Generate ASCII art using pyfiglet and convert it to a string
#         ascii_art_quote = pyfiglet.figlet_format(quote_text, font="slant")
#         ascii_art_str = str(ascii_art_quote)
        
#         # Create a Manim Text mobject using a monospaced font for best results
#         ascii_text = Text(
#             ascii_art_str,
#             font="Courier New",  # monospaced font for ASCII art alignment
#             font_size=15,
#         )
        
#         # Set a color gradient for the ASCII text and position it at the top
#         ascii_text.set_color_by_gradient(BLUE, GREEN)
#         ascii_text.to_edge(UP)
        
#         # Fetch voiceover and get its duration
#         audio_file = fetch_voiceover(quote_info['quote'], voice_api_key)
#         if audio_file:
#             voice_duration = get_audio_duration(audio_file)
#             # Start the voiceover sound and simultaneously animate the ASCII text
#             self.add_sound(audio_file, gain=+15)
#             self.play(Write(ascii_text, run_time=voice_duration))
#             # No extra wait is needed if the text animation is set to match the voiceover duration
#         else:
#             # Fallback: if no audio, just animate the text with a default duration
#             self.play(Write(ascii_text, run_time=5))
#             self.wait(2)



# SCROLL DOWN #

class AnimatedQuoteWithASCII(Scene):
    def construct(self):
        # Fetch the quote and author
        quote_info = fetch_quote()
        quote_text = quote_info['quote']
        author_str = f"- {quote_info['author']}"
        
        # Wrap the quote text if it is long (adjust width as needed)
        wrapped_quote = textwrap.fill(quote_text, width=80)
        
        # Generate ASCII art for the wrapped quote
        ascii_art_quote = pyfiglet.figlet_format(wrapped_quote, font="slant")
        ascii_art_str = str(ascii_art_quote)
        
        # Create a Text mobject for the ASCII art using a monospaced font
        ascii_text = Text(
            ascii_art_str,
            font="Courier New",
            font_size=15,
        )
        ascii_text.set_color_by_gradient(BLUE, GREEN)
        
        # Create another Text mobject for the author with a contrasting color
        author_text = Text(
            author_str,
            font="Courier New",
            font_size=20,
            color=RED,  # choose a contrasting color
        )
        # Position the author text just below the ASCII art
        author_text.next_to(ascii_text, DOWN, buff=0.5)
        
        # Group both texts so they animate together
        quote_group = VGroup(ascii_text, author_text)
        
        # Position the group at the bottom center of the scene
        quote_group.to_edge(DOWN)
        self.add(quote_group)
        
        # Fetch voiceover and get its duration
        audio_file = fetch_voiceover(quote_info['quote'], voice_api_key)
        if audio_file:
            voice_duration = get_audio_duration(audio_file)
            self.add_sound(audio_file, gain=+15)
            # Write the text
            self.play(Write(quote_group, run_time=voice_duration * 0.4))
            # Calculate the distance: move the group upward so that it scrolls off the top
            scroll_distance = config.frame_height + quote_group.height
            self.play(quote_group.animate.shift(UP * scroll_distance), run_time=voice_duration * 0.6)
        else:
            self.play(Write(quote_group, run_time=3))
            scroll_distance = config.frame_height + quote_group.height
            self.play(quote_group.animate.shift(UP * scroll_distance), run_time=3)
            self.wait(2)


# APPLY SCROLL EFFECT #

# class AnimatedQuoteWithASCII(Scene):
#     def construct(self):
#         # Fetch the quote and author
#         quote_info = fetch_quote()
#         quote_text = quote_info['quote']
#         author_str = f"- {quote_info['author']}"
        
#         # Wrap the quote text if it is long (adjust width as needed)
#         wrapped_quote = textwrap.fill(quote_text, width=80)
        
#         # Generate ASCII art for the wrapped quote
#         ascii_art_quote = pyfiglet.figlet_format(wrapped_quote, font="slant")
#         ascii_art_str = str(ascii_art_quote)
        
#         # Create a Text mobject for the ASCII art using a monospaced font
#         ascii_text = Text(
#             ascii_art_str,
#             font="Courier New",
#             font_size=15,
#         )
#         ascii_text.set_color_by_gradient(BLUE, GREEN)
        
#         # Position ascii_text so its bottom edge is at the bottom...
#         ascii_text.to_edge(DOWN)
#         # ...then shift it downward by its own height so its top edge aligns with the bottom.
#         ascii_text.shift(DOWN * ascii_text.height)
        
#         # Create another Text mobject for the author with a contrasting color
#         author_text = Text(
#             author_str,
#             font="Courier New",
#             font_size=20,
#             color=RED,  # choose a contrasting color
#         )
#         # Position the author text just below the ASCII art.
#         author_text.next_to(ascii_text, DOWN, buff=0.2)
        
#         # Group both texts so they animate together.
#         quote_group = VGroup(ascii_text, author_text)
#         self.add(quote_group)
        
#         # Fetch voiceover and get its duration.
#         audio_file = fetch_voiceover(quote_info['quote'], voice_api_key)
#         if audio_file:
#             voice_duration = get_audio_duration(audio_file)
#             self.add_sound(audio_file, gain=+15)
#             # Animate the drawing of the text
#             self.play(Write(quote_group, run_time=voice_duration * 0.4))
#             # Calculate the scroll distance to move the entire group off the top of the screen.
#             scroll_distance = config.frame_height + quote_group.get_height()
#             self.play(quote_group.animate.shift(UP * scroll_distance), run_time=voice_duration * 0.6)
#         else:
#             self.play(Write(quote_group, run_time=3))
#             scroll_distance = config.frame_height + quote_group.get_height()
#             self.play(quote_group.animate.shift(UP * scroll_distance), run_time=3)
#             self.wait(2)


# TIMED SCROLL #

# class AnimatedQuoteWithASCII(Scene):
#     def construct(self):
#         # Fetch the quote and author
#         quote_info = fetch_quote()
#         quote_text = quote_info['quote']
#         author_str = f"- {quote_info['author']}"
        
#         # Wrap the quote text if it is long (adjust width as needed)
#         wrapped_quote = textwrap.fill(quote_text, width=80)
        
#         # Generate ASCII art for the wrapped quote
#         ascii_art_quote = pyfiglet.figlet_format(wrapped_quote, font="slant")
#         ascii_art_str = str(ascii_art_quote)
        
#         # Create a Text mobject for the ASCII art using a monospaced font
#         ascii_text = Text(
#             ascii_art_str,
#             font="Courier New",
#             font_size=15,
#         )
#         ascii_text.set_color_by_gradient(BLUE, GREEN)
        
#         # Position ascii_text so its bottom edge is at the bottom...
#         ascii_text.to_edge(DOWN)
#         # ...then shift it downward by its own height so its top edge aligns with the bottom.
#         ascii_text.shift(DOWN * ascii_text.height)
        
#         # Create another Text mobject for the author with a contrasting color
#         author_text = Text(
#             author_str,
#             font="Courier New",
#             font_size=20,
#             color=RED,
#         )
#         # Position the author text just below the ASCII art.
#         author_text.next_to(ascii_text, DOWN, buff=0.2)
        
#         # Group both texts so they animate together.
#         quote_group = VGroup(ascii_text, author_text)
#         self.add(quote_group)
        
#         # Set a fixed scroll duration so viewers can read the text comfortably.
#         scroll_duration = 4  # Adjust this value to slow down or speed up the scroll
        
#         # Fetch voiceover and get its duration.
#         audio_file = fetch_voiceover(quote_info['quote'], voice_api_key)
#         if audio_file:
#             voice_duration = get_audio_duration(audio_file)
#             self.add_sound(audio_file, gain=+15)
#             # Animate the drawing of the text.
#             self.play(Write(quote_group, run_time=voice_duration * 0.4))
#             # Calculate the scroll distance to move the entire group off the top.
#             scroll_distance = config.frame_height + quote_group.get_height()
#             self.play(
#                 quote_group.animate.shift(UP * scroll_distance),
#                 run_time=scroll_duration,
#                 rate_func=linear  # Ensures a constant scroll speed.
#             )
#         else:
#             self.play(Write(quote_group, run_time=3))
#             scroll_distance = config.frame_height + quote_group.get_height()
#             self.play(
#                 quote_group.animate.shift(UP * scroll_distance),
#                 run_time=scroll_duration,
#                 rate_func=linear
#             )
#             self.wait(2)


# Animation from Left--> right

# class AnimatedQuoteWithASCII(Scene):
#     def construct(self):
#         # Fetch the quote and author
#         quote_info = fetch_quote()
#         quote_text = quote_info['quote']
#         author_str = f"- {quote_info['author']}"
        
#         # Wrap the quote text if it is long (adjust width as needed)
#         wrapped_quote = textwrap.fill(quote_text, width=80)
        
#         # Generate ASCII art for the wrapped quote
#         ascii_art_quote = pyfiglet.figlet_format(wrapped_quote, font="slant")
#         ascii_art_str = str(ascii_art_quote)
        
#         # Create a Text mobject for the ASCII art using a monospaced font
#         ascii_text = Text(
#             ascii_art_str,
#             font="Courier New",
#             font_size=15,
#         )
#         ascii_text.set_color_by_gradient(BLUE, GREEN)
        
#         # Position ascii_text so that its right edge is at the left edge of the scene.
#         # First, align its left edge to the left, then shift it left by its full width.
#         ascii_text.to_edge(LEFT)
#         ascii_text.shift(LEFT * ascii_text.get_width())
        
#         # Create another Text mobject for the author with a contrasting color.
#         # We'll keep the author positioned below the ASCII art.
#         author_text = Text(
#             author_str,
#             font="Courier New",
#             font_size=20,
#             color=RED,
#         )
#         author_text.next_to(ascii_text, DOWN, buff=0.2)
        
#         # Group both texts so they animate together.
#         quote_group = VGroup(ascii_text, author_text)
#         self.add(quote_group)
        
#         # Set a fixed scroll duration (in seconds) so the text scrolls at a comfortable reading pace.
#         scroll_duration = 6
        
#         # Fetch voiceover and get its duration.
#         audio_file = fetch_voiceover(quote_info['quote'], voice_api_key)
#         if audio_file:
#             voice_duration = get_audio_duration(audio_file)
#             self.add_sound(audio_file, gain=+15)
#             # Animate the drawing of the text.
#             self.play(Write(quote_group, run_time=voice_duration * 0.4))
#             # Calculate the distance: move the group right so that it completely exits the screen.
#             scroll_distance = config.frame_width + quote_group.get_width()
#             self.play(
#                 quote_group.animate.shift(RIGHT * scroll_distance),
#                 run_time=scroll_duration,
#                 rate_func=linear  # Ensures constant horizontal scroll speed.
#             )
#         else:
#             self.play(Write(quote_group, run_time=3))
#             scroll_distance = config.frame_width + quote_group.get_width()
#             self.play(
#                 quote_group.animate.shift(RIGHT * scroll_distance),
#                 run_time=scroll_duration,
#                 rate_func=linear
#             )
#             self.wait(2)


