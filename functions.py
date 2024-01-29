import json
import hashlib
from botocore.exceptions import NoCredentialsError
from flask import current_app as application
import os
import json
import hashlib
import boto3
from botocore.exceptions import NoCredentialsError
import openai
from models import User, db
import time

def create_new_assistant(client, files, s3, bucket_name, instructions, username, botName):
    try:
        files = [obj['Key'] for obj in s3.list_objects(Bucket=bucket_name, Prefix=f"{username}/")['Contents']]
        file_ids = []
        for filename in files:
            # Check the file type and skip if it's not supported
            if not filename.endswith(('.txt', '.json', '.c', '.cpp', '.docx', '.html', '.java', '.md', '.pdf', '.php', '.pptx', '.py', '.rb', '.tex')):
                print(f"Skipping unsupported file type: {filename}")
                continue
            local_filename = os.path.basename(filename)  # Get the base name of the file
            s3.download_file(bucket_name, filename, local_filename)
            file = client.files.create(file=open(local_filename, "rb"), purpose='assistants')
            file_ids.append(file.id)
            os.remove(local_filename)  # Delete the file after uploading it to OpenAI
            print("File IDs:", file_ids)

        start_time = time.time()
        assistant = client.beta.assistants.create(
            name=botName,
            instructions=instructions,
            model="gpt-3.5-turbo-1106",
            tools=[{
                "type": "retrieval"
            }],
            file_ids=file_ids)  # Pass the entire list of file IDs
        print("Time taken to create assistant: ", time.time() - start_time)

        start_time = time.time()
        thread = client.beta.threads.create()
        print("Time taken to create thread: ", time.time() - start_time)
        print(f"New thread created with ID: {thread.id}")  # Debugging line

        # Get the user from the database
        with application.app_context():
            user = User.query.filter_by(username=username).first()

            if user is None:
                print("User not found")
                return None

            # Update the user's assistant_id and instructions
            user.assistant_id = assistant.id
            user.instructions = instructions
            user.thread_id = thread.id
            db.session.commit()

        print("Created a new assistant and saved the ID.")

        return assistant.id

    except NoCredentialsError:
        print("Credentials not available")
    except Exception as e:
        print("An error occurred: " + str(e))

from models import User  # Assuming User is your model class

def create_assistant(client, instructions, username, botName):
    s3 = boto3.client('s3',
                      aws_access_key_id=os.getenv('ACCESS_KEY'),
                      aws_secret_access_key=os.getenv('SECRET_KEY'))
    bucket_name = 'knowledgebucket123'
    hash_file_path = 'hash.txt'

    # Get the list of files in the S3 bucket
    files = [obj['Key'] for obj in s3.list_objects(Bucket=bucket_name)['Contents']]
    file_hash = hashlib.sha256(json.dumps(files).encode()).hexdigest()

    # Get the user from the database
    user = User.query.filter_by(username=username).first()

    # If a hash file exists, compare the current hash with the saved hash
    if os.path.exists(hash_file_path):
        with open(hash_file_path, 'r') as file:
            saved_hash = file.read().strip()
        if saved_hash == file_hash:
            print("Files in the S3 bucket have not changed. No need to create a new assistant.")
            # If the assistant ID is not None, try to retrieve the assistant
            if user.assistant_id is not None:
                try:
                    retrieved_assistant = client.beta.assistants.retrieve(assistant_id=user.assistant_id)
                    print(f"Successfully retrieved assistant: {retrieved_assistant.id}")
                except openai.NotFoundError:
                    print("Assistant not found, creating a new assistant.")
                except Exception as e:
                    print(f"Failed to retrieve the assistant. Error: {str(e)}")
                    return None

                # If the assistant was successfully retrieved, try to delete it
                if retrieved_assistant:
                    try:
                        client.beta.assistants.delete(assistant_id=retrieved_assistant.id)
                        print(f"Successfully deleted assistant: {retrieved_assistant.id}")
                    except Exception as e:
                        print(f"Failed to delete the assistant. Error: {str(e)}")
                        return None
            else:
                print("Assistant ID is None, creating a new assistant.")
        else:
            print("File hash does not match, creating a new assistant.")
    else:
        print("Hash file does not exist, creating a new assistant.")

    # Create a new assistant
    if instructions:  # Check if instructions are provided
        try:
            assistant_id = create_new_assistant(client, files, s3, bucket_name, instructions, username, botName)
            user.assistant_id = assistant_id  # Update the assistant ID in the database
        except Exception as e:
            print("Failed to create a new assistant. Error: ", str(e))
            return None
    else:
        print("Error: Missing instructions")
        return None

    return assistant_id

def list_files_in_bucket(username):
    s3 = boto3.client('s3',
                      aws_access_key_id=os.getenv('ACCESS_KEY'),
                      aws_secret_access_key=os.getenv('SECRET_KEY'))
    bucket_name = 'knowledgebucket123'
    files = []

    try:
        for obj in s3.list_objects(Bucket=bucket_name, Prefix=username)['Contents']:
            file_path = obj['Key']
            file_name = file_path.replace(f'{username}/', '')  # Remove the 'username/' prefix
            files.append(file_name)
    except Exception as e:
        print("An error occurred: " + str(e))

    return files

def delete_file_from_bucket(username, filename):
    s3 = boto3.client('s3',
                      aws_access_key_id=os.getenv('ACCESS_KEY'),
                      aws_secret_access_key=os.getenv('SECRET_KEY'))
    bucket_name = 'knowledgebucket123'

    print(f"Username: {username}")  # Print the username
    print(f"Filename: {filename}")  # Print the filename
    print(f"Bucket Name: {bucket_name}")  # Print the bucket name

    try:
        print(f"Attempting to delete {username}/{filename} from the bucket {bucket_name}.")
        s3.delete_object(Bucket=bucket_name, Key=f'{username}/{filename}')
        print(f"Deleted {username}/{filename} from the bucket.")
    except Exception as e:
        print("An error occurred: " + str(e))
        raise e  # re-raise the exception to propagate the error to the calling function
