import boto3
import os

def lambda_handler(event, context):
    # Get the username from the event
    username = event['userName']

    s3 = boto3.client('s3',
                      aws_access_key_id=os.getenv('ACCESS_KEY'),
                      aws_secret_access_key=os.getenv('SECRET_KEY'))
    bucket_name = 'knowledgebucket123'
    folder_name = f"{username}/"  # The folder name is the username

    try:
        s3.put_object(Bucket=bucket_name, Key=folder_name)
        print(f"Successfully created folder {folder_name} in bucket {bucket_name}.")
    except Exception as e:
        print(f"Failed to create folder in S3 bucket. Error: {str(e)}")