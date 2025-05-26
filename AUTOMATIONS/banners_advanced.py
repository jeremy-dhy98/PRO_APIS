import pyfiglet
import time
from datetime import datetime

def print_banner():
    current_hour = datetime.now().hour
    if current_hour < 12:
        message = "Good Morning!"
    elif current_hour < 18:
        message = "Good Afternoon!"
    else:
        message = "Good Evening!"

    ascii_banner = pyfiglet.figlet_format(message, font="slant")
    print(ascii_banner)

if __name__ == "__main__":
    while True:
        print_banner()
        # Wait 60 seconds before printing the next banner
        time.sleep(60)
