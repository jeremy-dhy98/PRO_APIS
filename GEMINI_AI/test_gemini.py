import os
import google.generativeai as genai
import IPython.display as ipd

# configure gemini
api_key = os.environ.get("GOOGLE_API_KEY")
genai.configure(api_key=api_key)

# Define model to use
model = genai.GenerativeModel("gemini-1.5-flash")

# Upload file
file_path = ipd.Image(r"GEMINI_AI/schl_logo.jpeg")

def upload():
    """Än attempt to upload a file"""
    print("Uploading file...")
    try:
        file = genai.upload_file(file_path)
        print(f"Uploaded file: {file.name}")
        print("File uploaded sucessfully...")
    except:
        pass
    else:
         return file

# Save generated contents
def response_in_text(path):
    """Än attempt to save a file with response from model"""
    print(f"Saving file to: {path}")
    try:
      with open(path, "w", encoding="utf-8") as fl_obj:
          fl_obj.write(response.text)
          print("File saved sucessfully...")
    except:
        pass
   
    
# Define prompt--> text. image, video, audio
# file = upload()

prompt2 = "What are some of the characteristics of a programmer programming?"
response = model.generate_content(prompt2)

# Call method to save the response
response_in_text("Programmer_xtics.txt")
print(response.text) # print output as text

