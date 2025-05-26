import tweepy
import requests
from PIL import Image, ImageDraw, ImageFont
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

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
    Fetches a random cat image from TheCatAPI.
    """
    url = "https://api.thecatapi.com/v1/images/search"
    headers = {"x-api-key": api_key}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        if data:
            return data[0]["url"]
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching cat image: {e}")
    return None

def create_image_with_quote(image_url, quote, author, output_path="cat_with_quote.png"):
    """
    Downloads the cat image, adds a quote, and saves the output.
    """
    try:
        # Download the image
        response = requests.get(image_url)
        response.raise_for_status()
        with open("cat_image.jpg", "wb") as file:
            file.write(response.content)
        
        # Open and resize the image for better text placement
        img = Image.open("cat_image.jpg").convert("RGBA")
        img = img.resize((1080, 1920))  # Resize for consistent output
        draw = ImageDraw.Draw(img)
        
        # Load font
        font_path = "arial.ttf"  # Update path if necessary
        try:
            font = ImageFont.truetype(font_path, size=24)
        except IOError:
            logging.error(f"Font file not found at {font_path}. Using default font.")
            font = ImageFont.load_default()

        # Text formatting
        text = f'"{quote}"\n- {author}'
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        x = (img.width - text_width) // 2
        y = img.height - text_height - 20

        # Add semi-transparent background for text
        background = Image.new("RGBA", (text_width + 20, text_height + 20), (0, 0, 0, 128))
        img.paste(background, (x - 10, y - 10), background)

        # Add the text overlay
        draw.text((x, y), text, font=font, fill="white")

        # Save the final image
        img.save(output_path)
        logging.info(f"Image saved to {output_path}")
        return output_path
    except Exception as e:
        logging.error(f"Error creating image: {e}")
        raise

def post_to_twitter(image_path, status_text, consumer_key, consumer_secret, access_token, access_token_secret):
    """
    Posts the image with a quote to Twitter using Tweepy.
    """
    try:
        # Authenticate using Tweepy
        auth = tweepy.OAuth1UserHandler(consumer_key, consumer_secret, access_token, access_token_secret)
        api = tweepy.API(auth)

        # Upload media (image)
        media = api.media_upload(image_path)

        # Post the tweet with the image
        api.update_status(status=status_text, media_ids=[media.media_id])
        logging.info("Posted to Twitter successfully!")
    except Exception as e:
        logging.error(f"Error posting to Twitter: {e}")
        raise


# Twitter API credentials
consumer_key = os.environ.get("TWITTER_API_KEY")
consumer_secret = os.environ.get("TWITTER_API_SECRET")
access_token = os.environ.get("ACCESS_TOKEN")
access_token_secret = os.environ.get("ACCESS_TOKEN_SECRET")

# Cat API key
cat_api_key = os.environ.get("CAT_API_KEY")

if not all([consumer_key, consumer_secret, access_token, access_token_secret, cat_api_key]):
    logging.error("Missing API keys. Please set them as environment variables.")
else:
    # Fetch the quote and cat image
    quote_data = fetch_quote()
    cat_image_url = fetch_cat_image(cat_api_key)

    if quote_data and cat_image_url:
        quote = quote_data["quote"]
        author = quote_data["author"]

        # Create the image with the quote
        try:
            output_image = create_image_with_quote(cat_image_url, quote, author)

            # Post to Twitter
            status_text = "Here's a motivational quote with a cute cat! #Motivation #Quotes"
            post_to_twitter(output_image, status_text, consumer_key, consumer_secret, access_token, access_token_secret)

        except Exception as e:
            logging.error(f"Error creating or posting image: {e}")
    else:
        logging.error("Failed to fetch quote or cat image.")
