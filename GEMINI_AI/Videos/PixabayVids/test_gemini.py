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
file = upload()
# prompt = "Generate a python script which executes the sound in this video\
#           when expressed in text format."

# prompt1 = """A study was conducted to compare gas mileage for three competing brands of gasoline. for
# different automobile models of varying sizes are randomly selected. The data in km per gallon
# are given below
# Models
# gasoline brand
# 1 2 3 Total
# I 32.4 35.6 38.7 106.7
# II 28.8 28.6 29.9 87.3
# III 36.5 37.6 39.1 113.2
# IV 34.4 36.2 37.9 108.2
# Total 132.1 138.0 145.6 415.7
# Determine if there are significant differences between the gasoline brands and the models."""

# prompt2 = """1. The mathematics department of a Meru University of Science and Technology wishes to evaluate the teaching
# capabilities of 4 professors and 4 teaching assistants. In order to eliminate any effects due to different mathematics
# courses and different times of the day, it was decided that an experiment using a Latin square design in which
# the letters A,B,C and D represent the 4 different professors and α,β, γ and δ represent the teaching assistants
# be conducted. Each professor and each teaching assistant taught one section of each of the 4 different courses
# scheduled at each of the 4 different times during the day. The data in the following table show the grades assigned
# by each professor and each teaching assistant to 16 students of approximately equal ability:
# Time Period
# Course
# Algebra Insurance Statistics Calculus
# 1 A84α79 B79β81 C63γ65 D97δ94
# 2 B91δ90 A82γ80 D80β79 C93α94
# 3 C59β62 D70α68 A77δ80 B80γ82
# 4 D75γ73 C91δ88 B75α74 A68β74
# Use a 0.05 level of significance to test the hypothesis that
# (a) There is no difference in the grades due to different time periods;
# (b) the courses are of equal difficulty;
# (c) different professors have no effect on the grades;
# (d) different teaching assistants have no effect on the grades.
# 2. Three strains of rats were studied under 2 environmental conditions for their performance in a maze test. The
# error scores for the 48 rats were recorded as follows"""
# prompt = "Help me handle the Exercise  step by step with explanations? Guede me on how to calculate the CT and STT?"
# prompt1 = "How do I get started with designing logos in python?"
prompt2 = "How do I design a logo like this using python?"
response = model.generate_content([file, "\n\n", prompt2])
# response = model.generate_content(prompt)

# [prompt2, "\n\n", prompt]

# Call method to save the response
# response_in_text("why_python.txt")
print(response.text) # print output as text

