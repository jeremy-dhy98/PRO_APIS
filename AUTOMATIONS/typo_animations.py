from moviepy.config import change_settings
from moviepy.editor import *
import logging
import os

# Set the ImageMagick path for Windows
change_settings({
    "IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe"
})

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Function to create a typewriter effect
def typewriter_effect(text, font_path, font_size, duration, color="white", bg_color=None):
    letters = [text[:i + 1] for i in range(len(text))]
    text_clips = []
    for txt in letters:
        try:
            clip = TextClip(txt, font=font_path, fontsize=font_size, color=color, bg_color=bg_color)
            text_clips.append(clip)
        except Exception as e:
            logging.error(f"Error creating TextClip for text '{txt}': {e}")
            raise
    concatenated = concatenate_videoclips(text_clips, method="compose").set_duration(duration)
    assert concatenated is not None, "typewriter_effect returned None!"
    return concatenated

# Function to create a fade-in effect for the author text
def fade_in_text(text, font_path, font_size, duration, color="white", bg_color=None):
    try:
        txt_clip = TextClip(text, font=font_path, fontsize=font_size, color=color, bg_color=bg_color)
        faded_clip = txt_clip.set_duration(duration).crossfadein(duration / 2)
        assert faded_clip is not None, "fade_in_text returned None!"
        return faded_clip
    except Exception as e:
        logging.error(f"Error creating fade-in text for '{text}': {e}")
        raise

# Function to create a video with animated text
def animate_text_with_background(cat_image_path, quote, author, output_video, audio_path=None, resolution=(1280, 720), font_path=r"C:\Windows\Fonts\arial.ttf"):
    try:
        # Validate font path
        assert os.path.exists(font_path), f"Font path does not exist: {font_path}"
        logging.info(f"Quote: {quote}")
        logging.info(f"Author: {author}")
        logging.info(f"Output video: {output_video}")
        logging.info(f"Resolution: {resolution}")
        logging.info(f"Font: {font_path}")

        # Background clip
        bg_clip = ImageClip(cat_image_path).set_duration(5).resize(resolution)
        logging.info(f"Background clip type: {type(bg_clip)}")

        # Quote animation
        quote_clip = typewriter_effect(
            quote, font_path=font_path, font_size=50, duration=4, 
            color="white", bg_color="black").set_position(("center", "center"))

        # Author animation
        author_clip = fade_in_text(
            author, font_path=font_path, font_size=40, duration=2, 
            color="yellow", bg_color="black").set_position(("center", "bottom"))

        # Dynamically adjust background duration
        quote_duration = quote_clip.duration if quote_clip else 0
        author_duration = author_clip.duration if author_clip else 0
        audio_duration = 0
        if audio_path:
            try:
                audio_duration = mpy.AudioFileClip(audio_path).duration
            except Exception as e:
                logging.error(f"Error loading audio clip: {e}")
        
        max_duration = max(quote_duration, author_duration, audio_duration)
        logging.info(f"Max duration: {max_duration}")

        bg_clip = bg_clip.set_duration(max_duration)

        # Combine clips
        final_clip = CompositeVideoClip([bg_clip, quote_clip, author_clip])

        # Add audio if provided
        if audio_path:
            audio = AudioFileClip(audio_path)
            final_clip = final_clip.set_audio(audio).volumex(5.5)

        # Write the final video
        final_clip.write_videofile(output_video, codec="libx264", fps=24)
        logging.info(f"Video created successfully: {output_video}")

    except Exception as e:
        logging.error(f"Error creating video: {e}")

# Example usage
if __name__ == "__main__":
    cat_image_path = "cat_image.jpg"  
    quote = "Fools resist. The wise embrace."
    author = "Maxime Lagace"
    output_video = "animated_quote_video.mp4"
    audio_path = None  
    resolution = (1280, 720)
    font_path = r"C:\Windows\Fonts\arial.ttf"

    animate_text_with_background(
        cat_image_path, quote, author, output_video, 
        audio_path=audio_path, resolution=resolution, font_path=font_path
    )
