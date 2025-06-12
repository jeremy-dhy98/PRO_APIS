# configure image-magick
from moviepy.config import change_settings
change_settings({"IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe"})


import os
import moviepy.editor as mpy
from moviepy.video.VideoClip import TextClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.VideoClip import ColorClip
from IPython.display import Video as ipdVideo

# Video Specifications
target_width = 1280
target_height = 720
target_fps = 24

# Paths
vid_path = r"reencoded_video.mp4"
audio_path = r"Logos.mp3"
text_path = r"Logos.txt"

# Check if files exist
if not all([os.path.exists(vid_path), os.path.exists(audio_path), os.path.exists(text_path)]):
    raise FileNotFoundError("Ensure video, audio, and text files exist in the specified paths.")

# Load the video
video = mpy.VideoFileClip(vid_path).without_audio()

# Load the audio
audio = mpy.AudioFileClip(audio_path)

# Read and process text lines
with open(text_path, "r") as file:
    lines = [line.strip() for line in file.readlines()]

# Define start times and durations for each line in seconds
start_times = [
    0, 1, 3, 5, 8, 10, 11, 14, 16, 18, 20, 22, 25, 27, 29, 31,
    33, 35, 38, 40, 43, 45, 47, 48, 51, 52, 56
]
durations = [
    1, 2, 2, 3, 2, 1, 3, 2, 2, 2, 2, 3, 2, 2, 2, 2, 2, 3, 2, 3, 2,
    2, 1, 3, 1, 4
]

# Error handling for mismatch between lines and timings
if len(lines) != len(durations):
    raise ValueError("The number of lines, start times, and durations must match.")

# Create and position text clips with fade-in/out effects
clips = []
for line, start, duration in zip(lines, start_times, durations):
    # Dynamic font size adjustment
    fontsize = 50
    while True:
        text_clip = TextClip(str(line), fontsize=fontsize, color='black', 
        bg_color="white")
        if text_clip.w <= target_width * 0.9:  # Ensure text fits within 90% of video width
            break
        fontsize -= 2  # Decrease font size if too wide

    # Add fade-in/out effects
    text_clip = (
        text_clip.set_position("center")
        .set_start(start)
        .set_duration(duration)
        .crossfadein(0.5)
        .crossfadeout(0.5)
    )
    clips.append(text_clip)

# Combine video, overlay, and text clips
final_video = CompositeVideoClip([video] + clips).set_audio(audio).volumex(2.5)

# Export the final video
final_video.write_videofile(
    "logos_final_2.mp4",
    fps=target_fps,
    codec="libx264",
    audio_codec="aac",
    preset="slow"
)

# Release resources
video.close()
audio.close()
final_video.close()

# Display the final video
# ipd.Video("logos_final_2.mp4", width=650, height=350, embed=True)




