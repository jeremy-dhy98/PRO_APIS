import requests

# Define the API endpoint
url = "https://quotes.rest/qod"

try:
    # Send a GET request to fetch the Quote of the Day
    response = requests.get(url)
    
    # Raise an exception for HTTP errors (e.g., 4xx, 5xx responses)
    response.raise_for_status()

    # Check if the response is successful (status code 200)
    if response.status_code == 200:
        data = response.json()
        
        # Extract the quote and author from the JSON response
        quote = data["contents"]["quotes"][0]["quote"]
        author = data["contents"]["quotes"][0]["author"]
        
        # Print the quote of the day
        print(f"Quote of the Day: '{quote}' — {author}")
    
    else:
        print(f"Unexpected status code: {response.status_code}")

except requests.exceptions.RequestException as e:
    # Catch all network-related errors (e.g., connection issues, timeouts)
    print(f"Network error occurred: {e}")

except requests.exceptions.HTTPError as e:
    # Handle HTTP errors (4xx, 5xx responses)
    print(f"HTTP error occurred: {e}")

except requests.exceptions.Timeout:
    # Handle timeout errors
    print("The request timed out. Please try again later.")

except requests.exceptions.TooManyRedirects:
    # Handle errors from too many redirects
    print("Too many redirects. Check the URL or the server configuration.")

except Exception as e:
    # Catch any other unexpected errors
    print(f"An unexpected error occurred: {e}")
