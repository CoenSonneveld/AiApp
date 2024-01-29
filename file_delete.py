import requests
import os
from dotenv import load_dotenv
import openai

# Load environment variables from .env file
load_dotenv()

# Set your API key here
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
openai.api_key = OPENAI_API_KEY

print(openai.api_key)

# Headers for authorization
headers = {'Authorization': f'Bearer {OPENAI_API_KEY}'}

# List all files
response = requests.get('https://api.openai.com/v1/files', headers=headers)

if response.status_code == 200:
    files = response.json()['data']
    for file in files:
        file_id = file['id']
        delete_response = requests.delete(f'https://api.openai.com/v1/files/{file_id}', headers=headers)
        if delete_response.status_code == 200:
            print(f"Deleted file {file_id}")
        else:
            print(f"Failed to delete file {file_id}")
else:
    print("Failed to list files")
