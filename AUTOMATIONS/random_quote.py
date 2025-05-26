import requests

# ZenQuotes API endpoint for a random quote
url = "https://zenquotes.io/api/random"

# Make the request to the ZenQuotes API
response = requests.get(url)

if response.status_code == 200:
    data = response.json()
    
    # The structure of the response may be different from what you expect
    # ZenQuotes random API responds with a list of quotes
    if data:
        quote = data[0]["q"]  # The quote
        author = data[0]["a"]  # The author
        print(f"Quote of the Day: '{quote}' — {author}")
    else:
        print("No quotes found in the response.")
else:
    print(f"Error: {response.status_code}")
