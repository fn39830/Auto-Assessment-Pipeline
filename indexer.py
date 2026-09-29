# Import the os library to handle folder scanning
import os

# Import the json library to handle our data catalog
import json

# Define the path to our 'past_papers' folder
folder_path = 'past_papers/'
files=os.listdir(folder_path)

# Create an empty list called 'catalog' to store our paper data
catalog=[]

# Start a loop to go through every file in the folder
for file in files:

    # Check if the file is a PDF
   try:
       if file.endswith('.pdf'):
           # Get the filename and remove the '.pdf' extension
           paperName = file.replace('.pdf', '')
           # Split the filename into parts based on the underscore '_'
           parts = paperName.split('_')
           # Create a dictionary with keys: 'subject', 'exam_board', 'year', 'paper_number'
           tempDict = {"subject": parts[0], "exam_board": parts[1], "year": parts[2], "paper_number": parts[3]}
           # Add this dictionary to our 'catalog' list
           catalog.append(tempDict)
   except IndexError:
        print(f"Skipping malformed filename: {file}")


# Once the loop is finished, open a new file called 'catalog.json' for writing
with open("catalog.json", "w") as catalogFile:
    # Use json.dump to save our 'catalog' list into the file with nice formatting
    json.dump(catalog ,catalogFile)
