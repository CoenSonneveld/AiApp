import os
from time import sleep
from packaging import version
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session
from flask_session import Session
from werkzeug.utils import secure_filename
import openai
from openai import OpenAI
from functions import create_assistant, list_files_in_bucket, delete_file_from_bucket
from dotenv import load_dotenv
import boto3
from botocore.exceptions import NoCredentialsError, BotoCoreError, ClientError
from extensions import db
from functools import wraps
from models import User
from flask_migrate import Migrate
from uuid import uuid4
from datetime import datetime, timedelta
from flask.sessions import SessionInterface, SessionMixin
from werkzeug.datastructures import CallbackDict
from boto3.dynamodb.conditions import Key
from flask_cors import CORS


# rest of your code

load_dotenv()

s3 = boto3.client('s3',
                  aws_access_key_id=os.getenv('ACCESS_KEY'),
                  aws_secret_access_key=os.getenv('SECRET_KEY'))

# Check OpenAI version is correct
required_version = version.parse("1.1.1")
current_version = version.parse(openai.__version__)
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
openai.api_key = os.getenv('OPENAI_API_KEY')
if current_version < required_version:
  raise ValueError(f"Error: OpenAI version {openai.__version__}"
                   " is less than the required version 1.1.1")
else:
  print("OpenAI version is compatible.")

# Start Flask app
app = application = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = os.getenv('FLASK_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite'
app.config['JSONIFY_MIMETYPE'] = 'application/json'
migrate = Migrate(app, db)
db.init_app(app)

dynamodb = boto3.resource('dynamodb', region_name='eu-central-1')
table = dynamodb.Table('sessions')

class DynamoDBSession(CallbackDict, SessionMixin):
    def __init__(self, initial=None, sid=None):
        def on_update(self):
            self.modified = True
        CallbackDict.__init__(self, initial, on_update)
        self.sid = sid if sid else str(uuid4())
        self.modified = False

class DynamoDBSessionInterface(SessionInterface):
    def open_session(self, app, request):
        sid = request.cookies.get('session')  # Use 'session' instead of app.session_cookie_name
        if sid:
            session_data = table.query(
                KeyConditionExpression=Key('sid').eq(sid)
            )['Items']
            if session_data:
                return DynamoDBSession(initial=session_data[0]['data'], sid=sid)
        return DynamoDBSession()  # Return a new DynamoDBSession object when sid is None

    def save_session(self, app, session, response):
        domain = self.get_cookie_domain(app)
        if session and session.modified:  # Check if session is not None before accessing its attributes
            table.put_item(
                Item={
                    'sid': session.sid,
                    'data': session,
                    'expiration': (datetime.utcnow() + app.permanent_session_lifetime).isoformat()
                }
            )
        response.set_cookie('session', session.sid if session else '',  # Use 'session' instead of app.session_cookie_name
                            expires=self.get_expiration_time(app, session) if session else None,
                            httponly=self.get_cookie_httponly(app),
                            domain=domain)

app.session_interface = DynamoDBSessionInterface()

with app.app_context():
    db.create_all()


# Init client
client = OpenAI(
    api_key=OPENAI_API_KEY
)  # should use env variable OPENAI_API_KEY in secrets (bottom left corner)

def sync_users_with_cognito():
    print("Starting sync_users_with_cognito")  # Debugging line
    client = boto3.client('cognito-idp', region_name='eu-central-1')

    # Get list of users from Cognito
    cognito_users = []
    paginator = client.get_paginator('list_users')
    for page in paginator.paginate(UserPoolId='eu-central-1_2yaDHeNTp'):  # replace with your actual User Pool ID
        for user in page['Users']:
            cognito_users.append(user['Username'])

    print("Users from Cognito:", cognito_users)  # Debugging line

    # Get list of users from your database
    db_users = User.query.all()
    print("Users from database:", [user.username for user in db_users])  # Debugging line

    # Compare the two lists and delete any users from your database that don't exist in Cognito
    for db_user in db_users:
        if db_user.username not in cognito_users:
            print("Deleting user:", db_user.username)  # Debugging line
            db.session.delete(db_user)

    db.session.commit()
    print("Finished sync_users_with_cognito")  # Debugging line

def sync_s3_files_with_cognito():
    print("Starting sync_s3_files_with_cognito")  # Debugging line
    client = boto3.client('cognito-idp', region_name='eu-central-1')
    s3 = boto3.resource('s3')

    # Get list of users from Cognito
    cognito_users = []
    paginator = client.get_paginator('list_users')
    for page in paginator.paginate(UserPoolId='eu-central-1_2yaDHeNTp'):  # replace with your actual User Pool ID
        for user in page['Users']:
            cognito_users.append(user['Username'])

    print("Users from Cognito:", cognito_users)  # Debugging line

    # Get list of files in the S3 bucket
    bucket = s3.Bucket('knowledgebucket123')  # replace with your actual bucket name
    s3_files = [obj.key for obj in bucket.objects.all()]

    print("Files in S3 bucket:", s3_files)  # Debugging line

    # Compare the two lists and delete any files from the S3 bucket that don't correspond to a Cognito user
    for user in cognito_users:
        user_files = [file for file in s3_files if file.startswith(user)]
        if not user_files:
            print("No files found for user:", user)  # Debugging line

    # Delete any files from the S3 bucket that don't correspond to a Cognito user
    for file in s3_files:
        # Extract the username from the file name
        username = file.split('/')[0]
        if username not in cognito_users:
            print("Deleting file:", file)  # Debugging line
            s3.Object('knowledgebucket123', file).delete()

    print("Finished sync_s3_files_with_cognito")  # Debugging line

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'access_token' not in session or 'id_token' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def get_or_create_user(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        user = User(username=username)
        db.session.add(user)
        db.session.commit()
    return user

@app.route('/')
def home():
    return render_template('index.html', username=session.get('username'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        client = boto3.client('cognito-idp', region_name='eu-central-1')
        try:
            response = client.initiate_auth(
                AuthFlow='USER_PASSWORD_AUTH',
                AuthParameters={
                    'USERNAME': username,
                    'PASSWORD': password,
                },
                ClientId=os.getenv('CLIENT_ID'),
            )
            if response.get('ChallengeName') == 'NEW_PASSWORD_REQUIRED':
                session['session_id'] = response['Session']  # Store the session token in the server-side session
                return redirect(url_for('new_password', username=username))  # Redirect without the session token in the URL
        except ClientError as e:
            flash('Your username or password is incorrect.')
            return redirect(url_for('login'))
        
        user = get_or_create_user(username)


        # The response contains the new access, refresh, and ID tokens
        access_token = response['AuthenticationResult']['AccessToken']
        refresh_token = response['AuthenticationResult']['RefreshToken']
        id_token = response['AuthenticationResult']['IdToken']

        # Store the tokens and assistant_id in the session or a secure cookie
        session['access_token'] = access_token
        session['refresh_token'] = refresh_token
        session['id_token'] = id_token
        session['username'] = username
        session['assistant_id'] = user.assistant_id  # Store assistant_id in session

        return redirect(url_for('chat'))
    else:
        return render_template('index.html', username=session.get('username'))

@app.route('/new_password', methods=['GET', 'POST'])
def new_password():
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        new_user = request.form.get('username')

        print(f"New password: {new_password}")  # Debugging line
        print(f"Username: {new_user}")  # Debugging line

        # Check if session_id is None
        session_id = session.get('session_id')
        if session_id is None:
            flash('Session expired. Please login again.')
            return redirect(url_for('login'))  # Redirect to login page

        client = boto3.client('cognito-idp', region_name='eu-central-1')
        try:
            # Respond to the auth challenge
            response = client.respond_to_auth_challenge(
                ClientId=os.getenv('CLIENT_ID'),
                ChallengeName='NEW_PASSWORD_REQUIRED',
                Session=session_id,  # Use session_id here
                ChallengeResponses={
                    'USERNAME': new_user,
                    'NEW_PASSWORD': new_password,  # Include the email in the ChallengeResponses
                }
            )

            # Store the tokens in the session
            session['access_token'] = response['AuthenticationResult']['AccessToken']
            session['id_token'] = response['AuthenticationResult']['IdToken']
            session['refresh_token'] = response['AuthenticationResult']['RefreshToken']
            session['username'] = new_user
            session['session_id'] = session_id

            user = User.query.filter_by(username=new_user).first()
            if user is None:
                # The username does not exist, so you can insert a new user
                user = User(username=new_user)
                db.session.add(user)
            else:
                # The username already exists, update the user's information
                user.username = new_user
                # update other fields of the user as needed
                # user.field = new_value
            db.session.commit()

            # Redirect the user to the confirm page
            return redirect(url_for('confirm', username=new_user))

        except ClientError as e:
            print(e.response['Error']['Message'])
            flash('Your username or password is incorrect.')
            session['session_id'] = session_id  # Store the session_id in the server-side session
            return redirect(url_for('new_password', username=new_user))  # Remove session_id from here

    # Render the new password form
    return render_template('new_password.html')

@app.route('/confirm', methods=['GET', 'POST'])
def confirm():
    if request.method == 'POST':
        return redirect(url_for('chat'))
    return render_template('confirm.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')

        client = boto3.client('cognito-idp', region_name='eu-central-1')
        try:
            print("Before sign_up call")  # Print statement before the sign_up call
            response = client.sign_up(
                ClientId=os.getenv('CLIENT_ID'),
                Username=username,
                Password=password,
                UserAttributes=[
                    {
                        'Name': 'email',
                        'Value': email
                    },
                ]
            )
            print("After sign_up call")  # Print statement after the sign_up call
        except ClientError as e:
            print("Exception during sign_up:", e)
            flash(str(e))
            return redirect(url_for('register'))

        return redirect(url_for('login'))
    else:
        # Render the register form
        return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/is_logged_in', methods=['GET'])
def is_logged_in():
    if 'access_token' in session and 'id_token' in session:
        return {"logged_in": True}
    else:
        return {"logged_in": False}

# Start conversation thread
@app.route('/start', methods=['GET'])
@login_required
def start():
    # Get the current user's username
    username = session.get('username')

    # Get the user from the database
    user = User.query.filter_by(username=username).first()

    if user is None:
        print("Error: User not found")  # Debugging line
        return jsonify({"error": "User not found"}), 400

    thread_id = user.thread_id  # Get the thread ID from the user

    # If the user doesn't have a thread ID, create a new one
    if not thread_id:
        thread = client.beta.threads.create()
        thread_id = thread.id

        # Save the new thread ID to the user
        user.thread_id = thread_id
        db.session.commit()

    return jsonify({"thread_id": thread_id})

@app.route('/chat')
@login_required
def chat_page():
    return render_template('chat.html', username=session.get('username'))

# Generate response
@app.route('/chat', methods=['POST'])
@login_required
def chat():
  data = request.json
  user_input = data.get('message', '')

  # Get the current user's username
  username = session.get('username')

  # Get the user from the database
  user = User.query.filter_by(username=username).first()

  if user_input.lower() == '/clear':
    return jsonify({"response": "Chat cleared"}), 200

  if user is None:
    print("Error: User not found")  # Debugging line
    return jsonify({"error": "User not found"}), 400

  thread_id = user.thread_id  # Get the thread ID from the user

  if not thread_id:
    print("Error: Missing thread_id")  # Debugging line
    return jsonify({"error": "Missing thread_id"}), 400

  # Add the user's message to the thread
  client.beta.threads.messages.create(thread_id=thread_id,
                                      role="user",
                                      content=user_input)

  # Update the assistant_id variable
  assistant_id, instructions, botName = User.get_assistant_info()
  if not assistant_id or not instructions:
    print("Error: Missing assistant ID or instructions")  # Debugging line
    return jsonify({
        "error": "Assistant not found. Please consider adding knowledge first. Also, please add instructions and a bot name to optimize your experience. You can check the current instructions by clicking the bot name"
    }), 403

  # Run the Assistant
  try:
    run = client.beta.threads.runs.create(thread_id=thread_id,
                                        assistant_id=assistant_id)
  except openai.NotFoundError:
        # Return a response indicating the assistant was not found
        return jsonify({"error": "Assistant not found. Please consider adding knowledge first. Also, please add instructions and a bot name to optimize your experience. You can check the current instructions by clicking the bot name"}), 404
  # Check if the Run requires action (function call)
  while True:
    run_status = client.beta.threads.runs.retrieve(thread_id=thread_id,
                                                   run_id=run.id)
    print(f"Run status: {run_status.status}")
    if run_status.status == 'completed':
      break
    sleep(1)  # Wait for a second before checking again

  # Retrieve and return the latest message from the assistant
  messages = client.beta.threads.messages.list(thread_id=thread_id)
  response = messages.data[0].content[0].text.value

  print(f"Assistant response: {response}")  # Debugging line
  return jsonify({"response": response})

@app.route('/chat_history', methods=['GET'])
@login_required
def chat_history():
    # Get the current user's username
    username = session.get('username')

    # Get the user from the database
    user = User.query.filter_by(username=username).first()

    if user is None:
        print("Error: User not found")  # Debugging line
        return jsonify({"error": "User not found"}), 400

    thread_id = user.thread_id  # Get the thread ID from the user

    if not thread_id:
        print("Error: Missing thread_id")  # Debugging line
        return jsonify({"error": "Missing thread_id"}), 400

    # Retrieve all messages from the thread
    messages = client.beta.threads.messages.list(thread_id=thread_id)

    # Iterate over all messages and retrieve their content
    chat_history = []
    for message in messages.data:
        chat_history.append({
            "role": message.role,
            "content": message.content[0].text.value
        })

    return jsonify({"chat_history": chat_history})

@app.route('/knowledge', methods=['GET'])
def get_knowledge():
    try:
        username = session.get('username')  # Get the username from the session
        if username is None:
            return jsonify({"error": "Username not found in session"}), 500

        files = list_files_in_bucket(username)  # List files in the user's folder

        # Convert the files to a list of objects with 'username' and 'filename' properties
        data = [{'username': username, 'filename': filename} for filename in files]

        return jsonify(data)
    except Exception as e:
        return jsonify({"error": "An error occurred while retrieving the files: " + str(e)}), 500

@app.route('/knowledge/<username>/<filename>', methods=['DELETE'])
def delete_file(username, filename):
    try:
        delete_file_from_bucket(username, filename)
        return '', 204
    except Exception as e:
        return jsonify({"error": "An error occurred while deleting the file: " + str(e)}), 500

@app.route('/knowledge', methods=['POST'])
@login_required
def add_knowledge():
    if 'file' not in request.files:
        return jsonify({"error": "No selected file"}), 400
    files = request.files.getlist('file')
    username = session.get('username')  # Get the username from the session
    if username is None:
        return jsonify({"error": "User not logged in"}), 401  # Return an error if username is None
    for file in files:
        if file.filename == '':
            continue
        filename = secure_filename(file.filename)
        s3_file = f'{username}/{filename}'  # Use the username as the folder name
        try:
            s3.upload_fileobj(file, 'knowledgebucket123', s3_file)
        except NoCredentialsError:
            return jsonify({"error": "Credentials not available"}), 400
        except Exception as e:
            return jsonify({"error": "An error occurred while uploading the file: " + str(e)}), 500

    # Get the user from the database
    user = User.query.filter_by(username=username).first()
    if user is None:
        return jsonify({"error": "User not found"}), 404
    
    instructions = user.instructions
    botName = user.botName
    
    # Delete the previous assistant
    if user.assistant_id:
        try:
            client.beta.assistants.delete(assistant_id=user.assistant_id)
            print("Deleted old assistant.")
        except Exception as e:
            print(f"Failed to delete the assistant. Error: {str(e)}")

    # Reinitialize the assistant
    try:
        assistant_id = create_assistant(client, instructions, username, botName)
        user.assistant_id = assistant_id  # Update the assistant ID in the database
        db.session.commit()
    except Exception as e:
        return jsonify({"error": "An error occurred while reinitializing the assistant: " + str(e)}), 500

    return jsonify({"message": "Files uploaded and assistant reinitialized successfully"}), 200

@app.route('/change_chatbot_name', methods=['POST'])
@login_required
def change_chatbot_name():
    new_name = request.get_json().get('new_name')  # Get the new_name from the JSON body of the request
    username = session.get('username')  # Get the username from the session
    print(f"Username from session: {username}")  # Print the username retrieved from the session
    if username is None:
        return jsonify({"error": "User not logged in"}), 401  # Return an error if username is None
    user = User.query.filter_by(username=username).first()  # Get the user from the database
    print(f"User from database: {user}")  # Print the user retrieved from the database
    if user is None:
        return jsonify({"error": "User not found"}), 404  # Return an error if user is not found
    user.botName = new_name
    db.session.commit()
    session['botName'] = new_name  # Store the updated chatbot_name in the session
    return jsonify({"message": "Chatbot name changed successfully"}), 200

@app.route('/get_chatbot_name', methods=['GET'])
@login_required
def get_chatbot_name():
    username = session.get('username')  # Get the username from the session
    user = User.query.filter_by(username=username).first()  # Get the user from the database

    if user is None:
        return jsonify({"error": "User not found"}), 404  # Return an error if user is not found

    return jsonify({"chatbotName": user.botName}), 200  # Return the chatbot name

@app.route('/submit_instructions', methods=['POST'])
def submit_instructions():
    username = session.get('username')
    instructions = request.form['instructions']
    botName = request.form['botName']

    # Get the user from the database
    user = User.query.filter_by(username=username).first()

    if user is None:
        return jsonify({"error": "User not found"}), 404

    # Update the user's instructions
    user.botName = botName    # Save the bot name to the database
    user.instructions = instructions  # Save the instructions to the database
    db.session.commit()

    # Delete the old assistant before creating a new one
    if user.assistant_id:
        try:
            client.beta.assistants.delete(assistant_id=user.assistant_id)
            print("Deleted old assistant.")
        except Exception as e:
            print(f"Failed to delete the assistant. Error: {str(e)}")

    # Create the assistant after the instructions are saved
    assistant_id = create_assistant(client, instructions, username, botName)
    user.assistant_id = assistant_id  # Update the assistant ID in the database
    db.session.commit()

    return {'status': 'success', 'assistant_id': assistant_id}

@app.route('/get_instructions', methods=['GET'])
def get_instructions():
    username = session.get('username')

    # Get the user from the database
    user = User.query.filter_by(username=username).first()

    if user is None:
        return jsonify({"error": "User not found"}), 404

    # Return the user's instructions
    return {'instructions': user.instructions}

@app.route('/get_bot_name', methods=['GET'])
def get_bot_name():
    username = session.get('username')
    if not username:
        return jsonify({"error": "User not authenticated"}), 401

    user = User.query.filter_by(username=username).first()
    if user is None:
        return jsonify({"error": "User not found"}), 404

    return jsonify({"botName": user.botName or "Default Bot Name"})

@app.route('/clear_chat', methods=['POST'])
@login_required
def clear_chat():
    username = session.get('username')
    user = User.query.filter_by(username=username).first()
    if user is None:
        return jsonify({"error": "User not found"}), 404

    # Create a new thread
    new_thread = client.beta.threads.create()

    # Update the user's thread_id in the database
    user.thread_id = new_thread.id
    db.session.commit()

    return jsonify({"status": "Chat cleared"}), 200

@app.route('/gpt', methods=['GET', 'POST'])
@login_required
def handle_user_message():
    if request.method == 'POST':
        user_message = request.form.get('user_message')
        if not user_message:
            return jsonify({"error": "No message provided"}), 400

        client = openai.OpenAI(api_key=openai.api_key)  # Initialize the client

        try:
            response = client.chat.completions.create(
                model="gpt-4-1106-preview",  # Correct model name for GPT-4
                messages=[{"role": "user", "content": user_message}],
                max_tokens=150
            )
            assistant_message = response.choices[0].message.content
            return jsonify({"assistant_message": assistant_message})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    elif request.method == 'GET':
        return render_template('gpt.html')

if __name__ == '__main__':
    with app.app_context():
        sync_users_with_cognito()
        sync_s3_files_with_cognito()
    app.run(host='0.0.0.0', port=8080)