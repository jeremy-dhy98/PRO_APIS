# **ENHANCED** #

# configure image-magick
from moviepy.config import change_settings
change_settings({"IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe"})

import warnings
# Suppress ffmpeg warnings from MoviePy’s ffmpeg_reader
warnings.filterwarnings("ignore", category=UserWarning, module='moviepy.video.io.ffmpeg_reader')

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
import logging
import os
from io import BytesIO
import tempfile
import moviepy.editor as mpy

# -----------------------------------------------
# Helper Functions for Text Wrapping and Sizing
# -----------------------------------------------

def wrap_text(text, max_width, font, draw):
    """
    Wrap text so that each line’s width does not exceed max_width.
    Uses Pillow's textbbox to measure text.
    """
    words = text.split()
    lines = []
    current_line = words[0]
    for word in words[1:]:
        test_line = f"{current_line} {word}"
        bbox = draw.textbbox((0, 0), test_line, font=font)
        width = bbox[2] - bbox[0]
        if width <= max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word
    lines.append(current_line)
    return lines

def adjust_font_size_to_fit(image, quote, author, max_width, font_path, max_text_height_ratio=0.4):
    """
    Adjusts the font size so that the wrapped quote plus the author's name (rendered on a separate line)
    will fit within max_width and within a vertical space equal to max_text_height_ratio of the image height.
    
    Returns the font for the quote, the font for the author (slightly smaller), and the list of wrapped quote lines.
    """
    max_text_height = image.height * max_text_height_ratio
    # Start with a relatively large font size (10% of image height)
    font_size = int(image.height * 0.1)
    font = ImageFont.truetype(font_path, size=font_size)
    draw = ImageDraw.Draw(image)
    # Use a slightly smaller font for the author
    author_font = ImageFont.truetype(font_path, size=font_size - 5)
    padding = 20  # extra space around the text block

    while font_size > 10:
        quote_lines = wrap_text(quote, max_width, font, draw)
        # Measure the height of one line using a test character
        bbox = draw.textbbox((0, 0), "A", font=font)
        line_height = bbox[3] - bbox[1]
        total_quote_height = len(quote_lines) * line_height + (len(quote_lines) - 1) * 5  # include interline spacing

        bbox_author = draw.textbbox((0, 0), author, font=author_font)
        author_height = bbox_author[3] - bbox_author[1]

        total_text_height = total_quote_height + author_height + padding * 2

        # Check that each wrapped line fits within the maximum width
        max_line_width = max((draw.textbbox((0, 0), line, font=font)[2] -
                               draw.textbbox((0, 0), line, font=font)[0]) for line in quote_lines)

        if total_text_height <= max_text_height and max_line_width <= max_width:
            break

        font_size -= 1
        font = ImageFont.truetype(font_path, size=font_size)
        author_font = ImageFont.truetype(font_path, size=font_size - 5)

    return font, author_font, quote_lines

# -----------------------------------------------
# API and Image Functions
# -----------------------------------------------

def fetch_quote():
    """
    Fetches a random motivational quote from ZenQuotes API.
    """
    url = "https://zenquotes.io/api/random"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if data:
            return {"quote": data[0]["q"], "author": data[0]["a"]}
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching quote: {e}")
    return None

def fetch_cat_image(api_key):
    """
    Fetches a random cat image from TheCatAPI and saves it locally.
    """
    url = "https://api.thecatapi.com/v1/images/search"
    headers = {"x-api-key": api_key}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        if data:
            image_url = data[0]["url"]
            response = requests.get(image_url)
            response.raise_for_status()
            img = Image.open(BytesIO(response.content))
            img = img.convert("RGB")
            img.save("cat_image.jpg")
            return "cat_image.jpg"
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching cat image: {e}")
    return None

def calculate_brightness(image):
    """
    Calculates the average brightness of the image.
    """
    grayscale = ImageOps.grayscale(image)
    histogram = grayscale.histogram()
    pixels = sum(histogram)
    brightness = sum(i * histogram[i] for i in range(256)) / pixels
    return brightness

def get_overlay_color(brightness, opacity=128):
    """
    Returns a light overlay color if the image is dark,
    and a dark overlay color if the image is light.
    """
    if brightness < 128:
        return (255, 255, 255, opacity)
    else:
        return (0, 0, 0, opacity)

# -----------------------------------------------
# Style Functions (each uses the new adjust_font_size_to_fit)
# -----------------------------------------------

def minimalist_style(image_path, quote, author, output_path):
    image = Image.open(image_path)
    draw = ImageDraw.Draw(image)
    max_text_width = image.width - 40  # leave margin on sides
    font_path = "BriemHand-ExtraBold.ttf"
    font, author_font, quote_lines = adjust_font_size_to_fit(image, quote, author, max_text_width, font_path, 0.4)

    # Determine total text block height
    bbox = draw.textbbox((0, 0), "A", font=font)
    line_height = bbox[3] - bbox[1]
    total_quote_height = len(quote_lines) * line_height + (len(quote_lines) - 1) * 5
    bbox_author = draw.textbbox((0, 0), author, font=author_font)
    author_height = bbox_author[3] - bbox_author[1]
    padding = 20
    total_text_height = total_quote_height + author_height + padding * 2

    brightness = calculate_brightness(image)
    overlay_color = get_overlay_color(brightness)
    overlay = Image.new("RGBA", (image.width, total_text_height), overlay_color)
    image.paste(overlay, (0, image.height - total_text_height), overlay)

    y_offset = image.height - total_text_height + padding
    # Choose text fill so that it contrasts with the overlay
    text_fill = "black" if overlay_color[0] == 255 else "white"
    for line in quote_lines:
        bbox_line = draw.textbbox((0, 0), line, font=font)
        text_width = bbox_line[2] - bbox_line[0]
        x_position = (image.width - text_width) // 2
        draw.text((x_position, y_offset), line, font=font, fill=text_fill)
        y_offset += line_height + 5

    bbox_author = draw.textbbox((0, 0), author, font=author_font)
    author_width = bbox_author[2] - bbox_author[0]
    draw.text(((image.width - author_width) // 2, y_offset), author, font=author_font, fill=text_fill)

    image.save(output_path)
    print(f"Minimalist style saved as {output_path}")

def retro_style(image_path, quote, author, output_path):
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    max_text_width = image.width - 40
    font_path = "BriemHand-Bold.ttf"
    font, author_font, quote_lines = adjust_font_size_to_fit(image, quote, author, max_text_width, font_path, 0.4)
    
    # Apply a sepia filter manually
    width, height = image.size
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            r, g, b = image.getpixel((x, y))
            tr = int(0.393 * r + 0.769 * g + 0.189 * b)
            tg = int(0.349 * r + 0.686 * g + 0.168 * b)
            tb = int(0.272 * r + 0.534 * g + 0.131 * b)
            pixels[x, y] = (min(255, tr), min(255, tg), min(255, tb))

    brightness = calculate_brightness(image)
    overlay_color = get_overlay_color(brightness)
    bbox = draw.textbbox((0, 0), "A", font=font)
    line_height = bbox[3] - bbox[1]
    total_quote_height = len(quote_lines) * line_height + (len(quote_lines) - 1) * 5
    bbox_author = draw.textbbox((0, 0), author, font=author_font)
    author_height = bbox_author[3] - bbox_author[1]
    padding = 20
    total_text_height = total_quote_height + author_height + padding * 2

    overlay = Image.new("RGBA", (image.width, total_text_height), overlay_color)
    image.paste(overlay, (0, image.height - total_text_height), overlay)

    y_offset = image.height - total_text_height + padding
    text_fill = "black" if overlay_color[0] == 255 else "white"
    for line in quote_lines:
        bbox_line = draw.textbbox((0, 0), line, font=font)
        text_width = bbox_line[2] - bbox_line[0]
        x_position = (image.width - text_width) // 2
        draw.text((x_position, y_offset), line, font=font, fill=text_fill)
        y_offset += line_height + 5

    bbox_author = draw.textbbox((0, 0), author, font=author_font)
    author_width = bbox_author[2] - bbox_author[0]
    draw.text(((image.width - author_width) // 2, y_offset), author, font=author_font, fill=text_fill)
    image.save(output_path)
    print(f"Retro style saved as {output_path}")

def bold_style(image_path, quote, author, output_path):
    image = Image.open(image_path)
    draw = ImageDraw.Draw(image)
    max_text_width = image.width - 40
    font_path = "BriemHand-Black.ttf"
    font, author_font, quote_lines = adjust_font_size_to_fit(image, quote, author, max_text_width, font_path, 0.4)
    padding = 40
    bbox = draw.textbbox((0, 0), "A", font=font)
    line_height = bbox[3] - bbox[1]
    y_offset = image.height - padding - len(quote_lines) * line_height - (len(quote_lines) - 1) * 5

    # For Bold style, draw a background rectangle for each line before rendering text
    for line in quote_lines:
        bbox_line = draw.textbbox((0, 0), line, font=font)
        text_width = bbox_line[2] - bbox_line[0]
        text_height = bbox_line[3] - bbox_line[1]
        draw.rectangle([(50, y_offset), (image.width - 50, y_offset + text_height + 10)], fill="black")
        draw.text(((image.width - text_width) // 2, y_offset), line, font=font, fill="red")
        y_offset += text_height + 20

    bbox_author = draw.textbbox((0, 0), author, font=author_font)
    author_width = bbox_author[2] - bbox_author[0]
    draw.text(((image.width - author_width) // 2, y_offset), author, font=author_font, fill="red")
    image.save(output_path)
    print(f"Bold style saved as {output_path}")

def modern_abstract_style(image_path, quote, author, output_path):
    image = Image.open(image_path)
    draw = ImageDraw.Draw(image)
    max_text_width = image.width - 40
    font_path = "Allura-Regular.ttf"
    font, author_font, quote_lines = adjust_font_size_to_fit(image, quote, author, max_text_width, font_path, 0.4)
    # Draw an abstract shape – for example, a circle in the top-right corner:
    radius = 100
    top_left = (image.width - radius, 0)
    draw.ellipse([top_left[0] - radius, top_left[1], top_left[0] + radius, top_left[1] + radius],
                 fill="orange", outline="white", width=5)
    padding = 40
    bbox = draw.textbbox((0, 0), "A", font=font)
    line_height = bbox[3] - bbox[1]
    total_quote_height = len(quote_lines) * line_height + (len(quote_lines) - 1) * 5
    bbox_author = draw.textbbox((0, 0), author, font=author_font)
    author_height = bbox_author[3] - bbox_author[1]
    total_text_height = total_quote_height + author_height + padding * 2

    y_offset = image.height - total_text_height - 50
    for line in quote_lines:
        bbox_line = draw.textbbox((0, 0), line, font=font)
        text_width = bbox_line[2] - bbox_line[0]
        x_position = (image.width - text_width) // 2
        draw.text((x_position, y_offset), line, font=font, fill="white")
        y_offset += line_height + 10

    bbox_author = draw.textbbox((0, 0), author, font=author_font)
    author_width = bbox_author[2] - bbox_author[0]
    draw.text(((image.width - author_width) // 2, y_offset), author, font=author_font, fill="white")
    image.save(output_path)
    print(f"Modern abstract style saved as {output_path}")

# -----------------------------------------------
# Video and Voiceover Functions
# -----------------------------------------------

def create_video_with_audio(image_path, audio_content, output_video='output_video.mp4'):
    """
    Creates a video from an image and a provided audio clip.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_audio_file:
        temp_audio_file.write(audio_content)
        temp_audio_path = temp_audio_file.name

    audio_clip = mpy.AudioFileClip(temp_audio_path)
    image_clip = mpy.ImageClip(image_path, duration=5)
    video_clip = image_clip.set_audio(audio_clip)
    # Pass ffmpeg_params to suppress warnings
    video_clip.write_videofile(output_video, codec='libx264', fps=24, ffmpeg_params=['-loglevel', 'error'])
    print(f"Video created: {output_video}")
    os.unlink(temp_audio_path)

def fetch_voiceover(quote, api_key):
    """
    Fetches a voiceover (text-to-speech) from VoiceRSS API using a male voice.
    """
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
        return response.content
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching voiceover: {e}")
    return None

def apply_style(image_path, quote, author, style_type, audio_content, output_path="output.png", video_output_path="output_video.mp4"):
    styles = {
        "minimalist": minimalist_style,
        "retro": retro_style,
        "bold": bold_style,
        "modern": modern_abstract_style,
    }
    if style_type in styles:
        styles[style_type](image_path, quote, author, output_path)
        create_video_with_audio(output_path, audio_content, video_output_path)
    else:
        print(f"Style '{style_type}' not recognized!")

# -----------------------------------------------
# Main Program
# -----------------------------------------------

cat_api_key = os.environ.get("CAT_API_KEY")
voice_api_key = os.environ.get("VOICE_RSS_API_KEY")

if not cat_api_key or not voice_api_key:
    logging.error("Missing API keys. Please set them as environment variables.")
else:
    quote_data = fetch_quote()
    cat_image_path = fetch_cat_image(cat_api_key)
    if quote_data and cat_image_path:
        # Construct the text for voiceover and for overlay (with author)
        quote_voice = f"\"{quote_data['quote']}\""
        # Fetch the quote and author with a fallback in case the key is missing
        quote_text = quote_data.get("quote", "No quote found")
        quote_author = quote_data.get("a", quote_data.get("author", "Unknown"))
        # Format the quote text properly
        quote_full = f"\"{quote_text}\" - {quote_author}"
        try:
            audio_content = fetch_voiceover(quote_voice, voice_api_key)
            if audio_content:
                for style in ["minimalist", "retro", "bold", "modern"]:
                    output_image_path = f"{style}_output.png"
                    video_output_path = f"{style}_output_video.mp4"
                    # Pass the full quote (with author) to be drawn and separately pass the author text if needed.
                    apply_style(cat_image_path, quote_text, quote_data["author"], style, audio_content, output_image_path, video_output_path)
        except Exception as e:
            logging.error(f"Error creating designs or video: {e}")
    else:
        logging.error("Failed to fetch quote or cat image.")

# -----------------------------------------------
# Post-Processing: Resize and Re-Encode Videos
# -----------------------------------------------

video_paths = [
    "minimalist_output_video.mp4",
    "retro_output_video.mp4",
    "bold_output_video.mp4",
    "modern_output_video.mp4"
]

video_width, video_height, fps = 1280, 720, 24
codec = "libx264"

def process_video(input_video_path, output_video_path):
    video = mpy.VideoFileClip(input_video_path)
    video = video.resize(newsize=(video_width, video_height)).volumex(5.5)
    video.write_videofile(output_video_path, codec=codec, fps=fps, preset="slow", ffmpeg_params=['-loglevel', 'error'])
    video.close()
    if os.path.exists(input_video_path):
        os.remove(input_video_path)
        print(f"Original video {input_video_path} has been deleted.")
    else:
        print(f"Original video {input_video_path} does not exist.")

for video_path in video_paths:
    output_video_path = video_path.replace(".mp4", "_compatible.mp4")
    process_video(video_path, output_video_path)

    