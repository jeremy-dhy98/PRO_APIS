import pyfiglet
from datetime import datetime

# Get the current hour
current_hour = datetime.now().hour

# Choose a message based on the time
if current_hour < 12:
    message = "Good Morning!"
elif current_hour < 18:
    message = "Good Afternoon!"
else:
    message = "Good Evening!"

# Generate the ASCII art banner using pyfiglet
ascii_banner = pyfiglet.figlet_format(message, font="slant")
print(ascii_banner)
