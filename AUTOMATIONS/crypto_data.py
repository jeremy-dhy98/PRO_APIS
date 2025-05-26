import json 
import requests
import pandas as pd
import datetime

# Helper function to format and print JSON data
def jprint(obj):
    text = json.dumps(obj, sort_keys=True, indent=4)
    print(text)

currency = "btcusd"
url=f"https://www.bitstamp.net/api/v2/ohlc/{currency}/"

params = {"step": 60, "limit": 1000}

response = requests.get(url, params=params)

if response.status_code == 200:  # Check if the request was successful
    jprint(response.json())
else:
    raise Exception(f"Failed to fetch data: {response.status_code} {response.reason}")