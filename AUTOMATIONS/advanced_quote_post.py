import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
import textwrap
import logging
import os
from io import BytesIO

# Helper function for text wrapping
def wrap_text(text, width, font, draw):
    lines = textwrap.wrap(text, width=width)
    return lines

# Function to fetch random motivational quote
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

# Function to fetch random cat image
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
            img.save("cat_image.jpg")
            return "cat_image.jpg"
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching cat image: {e}")
    return None

# Function to calculate the brightness of an image
def calculate_brightness(image):
    grayscale_image = ImageOps.grayscale(image)  # Convert to grayscale to calculate brightness
    histogram = grayscale_image.histogram()
    pixels = sum(histogram)
    brightness = sum(i * histogram[i] for i in range(256)) / pixels  # Calculate average brightness
    return brightness

# Function to determine the best background color based on image brightness
def get_overlay_color(brightness, opacity=128):
    # Choose overlay color based on brightness
    if brightness < 128:  # Dark image, use light overlay
        return (255, 255, 255, opacity)  # Light background for dark images
    else:  # Light image, use dark overlay
        return (0, 0, 0, opacity)  # Dark background for light images

# Function for Minimalist Style
def minimalist_style(image_path, quote, output_path):
    image = Image.open(image_path)
    draw = ImageDraw.Draw(image)
    
    # Dynamic font size adjustment based on image height
    font_size = int(image.height * 0.05)  # 5% of the image height
    font = ImageFont.truetype("BriemHand-ExtraBold.ttf", size=font_size)
    
    lines = wrap_text(quote, 40, font, draw)

    # Calculate the image brightness
    brightness = calculate_brightness(image)

    # Get the appropriate background color based on the brightness
    overlay_color = get_overlay_color(brightness)

    # Create the overlay with the appropriate background color
    padding = 30
    text_height = len(lines) * font_size + padding * 2
    overlay = Image.new("RGBA", (image.width, text_height), overlay_color)  # Semi-transparent overlay
    image.paste(overlay, (0, image.height - text_height), overlay)  # Paste overlay at the bottom

    # Draw text on top of the overlay
    y_offset = image.height - text_height + padding
    text_fill = "black" if overlay_color == (255, 255, 255, 128) else "white"  # Adjust text color based on overlay
    for line in lines:
        text_bbox = draw.textbbox((0, 0), line, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        x_position = (image.width - text_width) // 2
        draw.text((x_position, y_offset), line, font=font, fill=text_fill)
        y_offset += font_size + 5

    image.save(output_path)
    print(f"Minimalist style saved as {output_path}")

# Function for Retro Style
def retro_style(image_path, quote, output_path):
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    
    # Dynamic font size adjustment based on image height
    font_size = int(image.height * 0.05)  # 5% of the image height
    font = ImageFont.truetype("BriemHand-Bold.ttf", size=font_size)
    
    lines = wrap_text(quote, 30, font, draw)

    # Sepia effect
    sepia_filter = [(r // 2 + 100, g // 2 + 50, b // 2) for (r, g, b) in image.getdata()]
    image.putdata(sepia_filter)

    # Calculate the image brightness
    brightness = calculate_brightness(image)

    # Get the appropriate background color based on the brightness
    overlay_color = get_overlay_color(brightness)

    # Create the overlay with the appropriate background color
    padding = 30
    text_height = len(lines) * font_size + padding * 2
    overlay = Image.new("RGBA", (image.width, text_height), overlay_color)  # Semi-transparent overlay
    image.paste(overlay, (0, image.height - text_height), overlay)  # Paste overlay at the bottom

    # Draw text on top of the overlay
    y_offset = image.height - text_height + padding
    text_fill = "black" if overlay_color == (255, 255, 255, 128) else "white"  # Adjust text color based on overlay
    for line in lines:
        text_bbox = draw.textbbox((0, 0), line, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        x_position = (image.width - text_width) // 2
        draw.text((x_position, y_offset), line, font=font, fill=text_fill)
        y_offset += font_size + 5

    image.save(output_path)
    print(f"Retro style saved as {output_path}")

# Function for Bold Style
def bold_style(image_path, quote, output_path):
    image = Image.open(image_path)
    draw = ImageDraw.Draw(image)
    
    # Dynamic font size adjustment based on image height
    font_size = int(image.height * 0.07)  # 7% of the image height
    font = ImageFont.truetype("BriemHand-Black.ttf", size=font_size)
    
    lines = wrap_text(quote, 25, font, draw)

    # Background rectangle for bold text
    padding = 40
    y_offset = image.height - padding - len(lines) * font_size
    for line in lines:
        text_bbox = draw.textbbox((0, 0), line, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        draw.rectangle(
            [(50, y_offset), (image.width - 50, y_offset + text_height + 10)],
            fill="black",
        )
        draw.text(((image.width - text_width) // 2, y_offset), line, font=font, fill="red")
        y_offset += text_height + 20

    image.save(output_path)
    print(f"Bold style saved as {output_path}")

# Function for Modern Abstract Style
def modern_abstract_style(image_path, quote, output_path):
    image = Image.open(image_path)
    draw = ImageDraw.Draw(image)
    
    # Dynamic font size adjustment (slightly smaller font size for more visibility)
    font_size = int(image.height * 0.04)  # Reduced to 4% of the image height for more space
    font = ImageFont.truetype("Allura-Regular.ttf", size=font_size)

    # Add abstract shapes: Positioning the circle at the top-right corner
    radius = 100  # Set the radius of the circle
    top_left_x = image.width - radius  # X position for the top-left corner
    top_left_y = 0  # Y position for the top-left corner (top of the image)
    
    # Draw the circle in the top-right corner
    draw.ellipse([top_left_x - radius, top_left_y, top_left_x + radius, top_left_y + radius], 
                 fill="orange", outline="white", width=5)
    
    # Draw wrapped text at the bottom with adjusted positioning
    lines = wrap_text(quote, 30, font, draw)
    padding = 40  # Padding between the text and the bottom of the image
    
    # Calculate the maximum available space for the quote
    text_height = len(lines) * font_size + (len(lines) - 1) * 5  # Total height of the text block
    max_text_area = image.height - padding - 50  # Maximum space available for the text

    # Adjust the Y offset to ensure the text stays within the available space
    if text_height < max_text_area:
        y_offset = image.height - text_height - padding
    else:
        # If the text is too large for the remaining space, move it up
        y_offset = image.height - max_text_area - padding

    # Further adjust the positioning to move the quote above
    y_offset -= 50  # This shifts the text upwards by an additional 50 pixels for more visibility

    for line in lines:
        # Correct bounding box handling to avoid unpacking errors
        text_bbox = draw.textbbox((0, 0), line, font=font)
        text_width = text_bbox[2] - text_bbox[0]  # Calculate width as the difference
        text_height = text_bbox[3] - text_bbox[1]  # Calculate height as the difference
        draw.text(((image.width - text_width) // 2, y_offset), line, font=font, fill="white")
        y_offset += text_height + 10  # Add some space between lines

    image.save(output_path)
    print(f"Modern Abstract style saved as {output_path}")

# Function to apply any style
def apply_style(image_path, quote, style_type, output_path="output.png"):
    styles = {
        "minimalist": minimalist_style,
        "retro": retro_style,
        "bold": bold_style,
        "modern": modern_abstract_style,
    }
    
    if style_type in styles:
        styles[style_type](image_path, quote, output_path)
    else:
        print(f"Style '{style_type}' not recognized!")

# Main Program
cat_api_key = os.environ.get("CAT_API_KEY")

if not cat_api_key:
    logging.error("Missing API keys. Please set them as environment variables.")
else:
    quote_data = fetch_quote()
    cat_image_path = fetch_cat_image(cat_api_key)

    if quote_data and cat_image_path:
        quote = f"\"{quote_data['quote']}\" - {quote_data['author']}"

        try:
            # Apply all styles
            apply_style(cat_image_path, quote, "minimalist", "minimalist_output.png")
            apply_style(cat_image_path, quote, "retro", "retro_output.png")
            apply_style(cat_image_path, quote, "bold", "bold_output.png")
            apply_style(cat_image_path, quote, "modern", "modern_output.png")
        except Exception as e:
            logging.error(f"Error creating designs: {e}")
    else:
        logging.error("Failed to fetch quote or cat image.")
