from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base
import os
import base64
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle

mcp = FastMCP("Gmail MCP Server")

# Defining Tools
@mcp.tool()
def get_gmail_message(message_id: str = None, query: str = None) -> dict:
    """
    Retrieve email content from a Gmail account using either a specific message ID or a search query.
    
    Authentication happens automatically using credentials from environment variables. First-time use 
    requires browser-based authorization.
    
    Args:
        message_id: The unique ID of a specific Gmail message to retrieve. If provided, query parameter is ignored.
                   Example: "18de3456a7b890cd"
        
        query: Gmail search query using Gmail's advanced search operators. Returns only the first matching message.
               
               Common search operators:
               - from:[email] - Messages from a specific sender
               - to:[email] - Messages to a specific recipient
               - subject:[text] - Messages with specific text in subject
               - after:[YYYY/MM/DD] - Messages after date
               - before:[YYYY/MM/DD] - Messages before date
               - is:unread - Unread messages
               - has:attachment - Messages with attachments
               - in:[folder] - Messages in a specific folder/label (e.g., in:inbox, in:trash, in:spam)
               - label:[name] - Messages with a specific label
               
               Example queries:
               - "from:medium.com subject:\"Daily Digest\" in:inbox" 
               - "from:github.com is:unread in:inbox"
               - "subject:invoice after:2023/01/01 in:inbox"
               - "in:spam from:newsletter"
               - "label:work has:attachment"
               - "in:trash subject:meeting"
               
               For complex searches, combine multiple operators:
               - "from:medium.com in:inbox after:2023/01/01 has:attachment"
    
    Returns:
        dict: On success, returns email details including:
            - id: Unique message ID
            - threadId: Conversation thread ID
            - labelIds: List of Gmail labels (e.g., "INBOX", "UNREAD")
            - snippet: Brief preview of the message
            - subject: Email subject line
            - from: Sender information
            - to: Recipient information 
            - date: Date and time sent
            - body: Full email body text (plain text version)
    
    Error Handling:
        All errors are returned as dictionaries with an "error" key containing the error message.
        Common error scenarios:
        
        - Missing parameters: 
          {"error": "Either message_id or query must be provided."}
          
        - No matching messages: 
          {"error": "No messages found matching the query."}
          
        - Authentication errors:
          {"error": "Failed to authenticate with Gmail API: [specific error message]"}
          
        - Missing environment variables:
          {"error": "Missing required environment variables (GMAIL_TOKEN_PATH or GMAIL_CREDENTIALS_PATH)"}
          
        - File access errors:
          {"error": "Could not access token/credentials file: [specific error message]"}
          
        - Gmail API errors:
          {"error": "Gmail API error: [specific error message]"}
    """
    try:
        # Validate environment variables
        token_path = os.getenv('GMAIL_TOKEN_PATH')
        credentials_path = os.getenv('GMAIL_CREDENTIALS_PATH')
        
        if not token_path or not credentials_path:
            return {
                "error": "Missing environment variables. Please set GMAIL_TOKEN_PATH and GMAIL_CREDENTIALS_PATH."
            }
            
        # Define the scopes
        SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
        
        # Authentication handling
        creds = None
        try:
            if os.path.exists(token_path):
                with open(token_path, 'rb') as token:
                    creds = pickle.load(token)
        except (FileNotFoundError, PermissionError, pickle.PickleError) as e:
            return {"error": f"Token access error: {str(e)}"}
            
        # If credentials don't exist or are invalid, get new ones
        if not creds or not creds.valid:
            try:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not os.path.exists(credentials_path):
                        return {"error": f"Credentials file not found at {credentials_path}"}
                    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                    creds = flow.run_local_server(port=0)
                
                # Save the credentials for the next run
                with open(token_path, 'wb') as token:
                    pickle.dump(creds, token)
            except Exception as e:
                return {"error": f"Authentication error: {str(e)}"}
        
        # Build the Gmail API service
        try:
            service = build('gmail', 'v1', credentials=creds)
        except Exception as e:
            return {"error": f"Failed to initialize Gmail API: {str(e)}"}
        
        # Parameter validation
        user_id = 'me'
        if not (message_id or query):
            return {"error": "Either message_id or query must be provided."}
        
        # API request handling with proper error checking
        try:
            if message_id:
                msg = service.users().messages().get(userId=user_id, id=message_id, format='full').execute()
                return _format_message(msg)
            elif query:
                results = service.users().messages().list(userId=user_id, q=query).execute()
                messages = results.get('messages', [])
                
                if not messages:
                    return {"error": "No messages found matching the query."}
                
                msg = service.users().messages().get(userId=user_id, id=messages[0]['id'], format='full').execute()
                return _format_message(msg)
        except Exception as e:
            return {"error": f"Gmail API error: {str(e)}"}
            
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}

def _format_message(msg):
    """
    Extract and format key components from a Gmail API message object.
    
    This function processes the complex Gmail API message format, extracting metadata
    from headers and decoding the message body from base64. It handles both single-part
    and multi-part MIME messages, prioritizing plain text content when available.
    
    Args:
        msg: Raw Gmail API message object containing nested payload structure
    
    Returns:
        dict: Formatted email with standardized fields:
            - id: Unique Gmail message identifier
            - threadId: Conversation thread identifier
            - labelIds: Gmail organizational labels
            - snippet: Short preview text
            - subject: Email subject from headers
            - from: Sender email address and name
            - to: Recipient email address(es)
            - date: Timestamp of the message
            - body: Decoded plain text content of the email
    """
    # Extract header information
    headers = {}
    for header in msg['payload']['headers']:
        headers[header['name']] = header['value']
    
    # Extract body parts and content
    body = ""
    if 'parts' in msg['payload']:
        for part in msg['payload']['parts']:
            if part['mimeType'] == 'text/plain':
                body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                break
    elif 'body' in msg['payload'] and 'data' in msg['payload']['body']:
        body = base64.urlsafe_b64decode(msg['payload']['body']['data']).decode('utf-8')
    
    return {
        "id": msg['id'],
        "threadId": msg['threadId'],
        "labelIds": msg.get('labelIds', []),
        "snippet": msg.get('snippet', ''),
        "subject": headers.get('Subject', ''),
        "from": headers.get('From', ''),
        "to": headers.get('To', ''),
        "date": headers.get('Date', ''),
        "body": body
    }

# Ensure the MCP server is exposed properly
if __name__ == "__main__":
    mcp.run()


# MCP Developer API Reference:

# # Defining Resource Templates - Placeholder
# @mcp.resource("greeting://{name}")
# def get_greeting(name: str) -> str:
#     """Get a greeting message for the given name."""
#     return f"Hello, {name}!"

# # Defining Resources - Placeholder
# @mcp.resource("config://app")
# def get_standard_greeting() -> str:
#     """App configuration message."""
#     return "Hello, World!"

# # Defining Prompts - Placeholder
# @mcp.prompt()
# def debug_error(error: str) -> list[base.Message]:
#     return [
#         base.UserMessage("I'm seeing this error:"),
#         base.UserMessage(error),
#         base.AssistantMessage("I'll help debug that. What have you tried so far?"),
#     ]