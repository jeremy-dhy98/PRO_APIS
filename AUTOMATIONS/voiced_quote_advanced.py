# configure image-magick
from moviepy.config import change_settings
change_settings({"IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe"})

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
import textwrap
import logging
import os
from io import BytesIO
import tempfile
import moviepy.editor as mpy

# **ADVANCED** #

# -----------------------------
# Text wrapping and font sizing
# -----------------------------

def wrap_text(quote, max_width, font, draw):
    """Wrap text to fit within the specified width."""
    words = quote.split(' ')
    lines = []
    current_line = ""
    
    for word in words:
        test_line = current_line + " " + word if current_line else word
        bbox = draw.textbbox((0, 0), test_line, font=font)
        width = bbox[2] - bbox[0]
        if width <= max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines

def adjust_font_size(image, quote, author, max_width, font_path, max_text_height_ratio=0.4):
    """
    Adjust the font size so that the quote and author text fit both horizontally 
    (within max_width) and vertically (within a fraction of the image height defined by max_text_height_ratio).
    """
    max_text_height = image.height * max_text_height_ratio  # available vertical space for text
    
    # Start with an initial font size based on image height
    font_size = int(image.height * 0.1)
    font = ImageFont.truetype(font_path, size=font_size)
    # For the author's name, use a slightly smaller font
    author_font = ImageFont.truetype(font_path, size=font_size - 10)
    draw = ImageDraw.Draw(image)
    
    line_spacing = 5  # spacing between lines
    padding = 20      # extra padding for the text block

    # Loop to reduce font size until the entire text (quote and author) fits within the vertical constraint
    while font_size > 10:
        # Wrap the quote text
        lines = wrap_text(quote, max_width, font, draw)
        
        # Calculate the height for the quote text using textbbox on a test character
        bbox = draw.textbbox((0, 0), "A", font=font)
        line_height = bbox[3] - bbox[1]
        total_quote_height = len(lines) * line_height + (len(lines) - 1) * line_spacing
        
        # Calculate the height for the author's name using textbbox
        bbox_author = draw.textbbox((0, 0), author, font=author_font)
        author_height = bbox_author[3] - bbox_author[1]
        
        total_text_height = total_quote_height + author_height + padding * 2

        # Check horizontal: ensure the widest line fits
        max_line_width = 0
        for line in lines:
            bbox_line = draw.textbbox((0, 0), line, font=font)
            width = bbox_line[2] - bbox_line[0]
            if width > max_line_width:
                max_line_width = width

        if total_text_height <= max_text_height and max_line_width <= max_width:
            break
        
        # Reduce the font size and update fonts
        font_size -= 1
        font = ImageFont.truetype(font_path, size=font_size)
        author_font = ImageFont.truetype(font_path, size=font_size - 10)
    
    return font, author_font, lines

# -----------------------------
# API and Image Fetching
# -----------------------------

def fetch_quote():
    """
    Fetches a random motivational quote from ZenQuotes API.
    """
    url = "https://zenquotes.io/api/random"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        logging.info(f"Fetched data: {data}")
        if isinstance(data, list) and data:
            quote = data[0].get("q", "No quote found")
            author = data[0].get("a", "Unknown author")
            return {"quote": quote, "author": author}
        else:
            logging.error("API response is not in expected format.")
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

def calculate_brightness(image):
    grayscale_image = ImageOps.grayscale(image)
    histogram = grayscale_image.histogram()
    pixels = sum(histogram)
    brightness = sum(i * histogram[i] for i in range(256)) / pixels
    return brightness

def get_overlay_color(brightness, opacity=128):
    if brightness < 128:
        return (255, 255, 255, opacity)
    else:
        return (0, 0, 0, opacity)

# -----------------------------
# Image Styles
# -----------------------------

def minimalist_style(image_path, quote, author, output_path):
    image = Image.open(image_path)
    # Adjust the font so that both quote and author fit
    font, author_font, lines = adjust_font_size(
        image, quote, author, image.width - 40, "BriemHand-ExtraBold.ttf", max_text_height_ratio=0.4
    )
    draw = ImageDraw.Draw(image)
    line_spacing = 5
    padding = 30

    # Calculate total text height
    bbox = draw.textbbox((0, 0), "A", font=font)
    line_height = bbox[3] - bbox[1]
    total_quote_height = len(lines) * line_height + (len(lines) - 1) * line_spacing
    bbox_author = draw.textbbox((0, 0), author, font=author_font)
    author_height = bbox_author[3] - bbox_author[1]
    total_text_height = total_quote_height + author_height + padding * 2

    brightness = calculate_brightness(image)
    overlay_color = get_overlay_color(brightness)
    overlay = Image.new("RGBA", (image.width, total_text_height), overlay_color)
    image.paste(overlay, (0, image.height - total_text_height), overlay)

    y_offset = image.height - total_text_height + padding
    text_fill = "black" if overlay_color == (255, 255, 255, 128) else "white"
    
    for line in lines:
        bbox_line = draw.textbbox((0, 0), line, font=font)
        text_width = bbox_line[2] - bbox_line[0]
        x_position = (image.width - text_width) // 2
        draw.text((x_position, y_offset), line, font=font, fill=text_fill)
        y_offset += line_height + line_spacing

    bbox_author = draw.textbbox((0, 0), author, font=author_font)
    author_width = bbox_author[2] - bbox_author[0]
    draw.text(((image.width - author_width) // 2, y_offset), author, font=author_font, fill=text_fill)

    image.save(output_path)
    print(f"Minimalist style saved as {output_path}")

def retro_style(image_path, quote, author, output_path):
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    font, author_font, lines = adjust_font_size(
        image, quote, author, image.width - 40, "BriemHand-Bold.ttf", max_text_height_ratio=0.4
    )
    
    # Apply sepia effect
    def apply_sepia(image):
        width, height = image.size
        pixels = image.load()
        for py in range(height):
            for px in range(width):
                r, g, b = image.getpixel((px, py))
                tr = int(0.393 * r + 0.769 * g + 0.189 * b)
                tg = int(0.349 * r + 0.686 * g + 0.168 * b)
                tb = int(0.272 * r + 0.534 * g + 0.131 * b)
                pixels[px, py] = (min(255, tr), min(255, tg), min(255, tb))
        return image

    image = apply_sepia(image)
    line_spacing = 5
    padding = 30

    bbox = draw.textbbox((0, 0), "A", font=font)
    line_height = bbox[3] - bbox[1]
    total_quote_height = len(lines) * line_height + (len(lines) - 1) * line_spacing
    bbox_author = draw.textbbox((0, 0), author, font=author_font)
    author_height = bbox_author[3] - bbox_author[1]
    total_text_height = total_quote_height + author_height + padding * 2

    brightness = calculate_brightness(image)
    overlay_color = get_overlay_color(brightness)
    overlay = Image.new("RGBA", (image.width, total_text_height), overlay_color)
    image.paste(overlay, (0, image.height - total_text_height), overlay)

    y_offset = image.height - total_text_height + padding
    text_fill = "black" if overlay_color == (255, 255, 255, 128) else "white"
    
    for line in lines:
        bbox_line = draw.textbbox((0, 0), line, font=font)
        text_width = bbox_line[2] - bbox_line[0]
        x_position = (image.width - text_width) // 2
        draw.text((x_position, y_offset), line, font=font, fill=text_fill)
        y_offset += line_height + line_spacing

    bbox_author = draw.textbbox((0, 0), author, font=author_font)
    author_width = bbox_author[2] - bbox_author[0]
    draw.text(((image.width - author_width) // 2, y_offset), author, font=author_font, fill=text_fill)

    image.save(output_path)
    print(f"Retro style saved as {output_path}")

def bold_style(image_path, quote, author, output_path):
    image = Image.open(image_path)
    draw = ImageDraw.Draw(image)
    font, author_font, lines = adjust_font_size(
        image, quote, author, image.width - 40, "BriemHand-Black.ttf", max_text_height_ratio=0.4
    )
    
    padding = 40
    line_spacing = 5
    bbox = draw.textbbox((0, 0), "A", font=font)
    line_height = bbox[3] - bbox[1]
    total_quote_height = len(lines) * line_height + (len(lines) - 1) * line_spacing
    bbox_author = draw.textbbox((0, 0), author, font=author_font)
    author_height = bbox_author[3] - bbox_author[1]
    
    # Position the text block somewhere higher up on the image
    y_offset = image.height - padding - total_quote_height - author_height - 10
    for line in lines:
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
    padding = 30
    font, author_font, lines = adjust_font_size(
        image, quote, author, image.width - 40, "Allura-Regular.ttf", max_text_height_ratio=0.4
    )
    
    # Draw some abstract shapes (circles)
    radius = 100
    top_right_x = image.width - radius - 10
    top_right_y = 10
    for i in range(radius, 0, -5):
        draw.ellipse([top_right_x - i, top_right_y - i, top_right_x + i, top_right_y + i],
                     outline="orange", width=3)

    line_spacing = 5
    bbox = draw.textbbox((0, 0), "A", font=font)
    line_height = bbox[3] - bbox[1]
    total_quote_height = len(lines) * line_height + (len(lines) - 1) * line_spacing
    bbox_author = draw.textbbox((0, 0), author, font=author_font)
    author_height = bbox_author[3] - bbox_author[1]
    
    total_text_height = total_quote_height + author_height + padding * 2
    y_offset = image.height - total_text_height - 10
    
    for line in lines:
        bbox_line = draw.textbbox((0, 0), line, font=font)
        text_width = bbox_line[2] - bbox_line[0]
        x_position = (image.width - text_width) // 2
        draw.text((x_position, y_offset), line, font=font, fill="white")
        y_offset += line_height + line_spacing

    bbox_author = draw.textbbox((0, 0), author, font=author_font)
    author_width = bbox_author[2] - bbox_author[0]
    draw.text(((image.width - author_width) // 2, y_offset), author, font=author_font, fill="white")

    image.save(output_path)
    print(f"Modern abstract style saved as {output_path}")

# -----------------------------
# Video Creation Functions
# -----------------------------

def create_video_with_audio(image_path, audio_content, output_video='output_video.mp4'):
    """
    Creates a video from an image and audio content.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_audio_file:
        temp_audio_file.write(audio_content)
        temp_audio_path = temp_audio_file.name

    audio_clip = mpy.AudioFileClip(temp_audio_path)
    image_clip = mpy.ImageClip(image_path, duration=5)
    video_clip = image_clip.set_audio(audio_clip)
    video_clip.write_videofile(output_video, codec='libx264', fps=24, ffmpeg_params=['-loglevel', 'error'])
    print(f"Video created: {output_video}")
    os.unlink(temp_audio_path)

def fetch_voiceover(quote, api_key):
    """
    Fetches voiceover for the given quote using VoiceRSS API with a male voice.
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

# -----------------------------
# Main Program
# -----------------------------

cat_api_key = os.environ.get("CAT_API_KEY")
voice_api_key = os.environ.get("VOICE_RSS_API_KEY")

if not cat_api_key or not voice_api_key:
    logging.error("Missing API keys. Please set them as environment variables.")
else:
    quote_data = fetch_quote()
    cat_image_path = fetch_cat_image(cat_api_key)
    if quote_data and cat_image_path:
        # Construct quote and include the author separately
        quote_text = f"\"{quote_data['quote']}\""
        author_text = f"- {quote_data['author']}"
        try:
            audio_content = fetch_voiceover(quote_text, voice_api_key)
            if audio_content:
                for style in ["minimalist", "retro", "bold", "modern"]:
                    output_image_path = f"{style}_output.png"
                    video_output_path = f"{style}_output_video.mp4"
                    apply_style(cat_image_path, quote_text, author_text, style, audio_content,
                                output_image_path, video_output_path)
        except Exception as e:
            logging.error(f"Error creating designs or video: {e}")
    else:
        logging.error("Failed to fetch quote or cat image.")

# -----------------------------
# Post-process videos for compatibility
# -----------------------------

video_paths = [
    "minimalist_output_video.mp4",
    "retro_output_video.mp4",
    "bold_output_video.mp4",
    "modern_output_video.mp4"
]

video_width, video_height, fps = 1280, 720, 24
codec = "libx264"

def process_video(input_video_path, output_video_path):
    # Create VideoFileClip without logger parameter
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


