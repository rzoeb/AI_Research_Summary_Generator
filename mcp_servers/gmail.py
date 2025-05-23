from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base
import os
import base64
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
from bs4 import BeautifulSoup
import json
from urllib.parse import urlparse, urlunparse

mcp = FastMCP("Gmail MCP Server")

# Defining Tools
@mcp.tool()
def get_gmail_message(message_id: str = None, query: str = None) -> dict:
    """
    Retrieve email content from a Gmail account using either a specific message ID or a search query.
    
    Authentication happens automatically using credentials from environment variables. First-time use 
    requires browser-based authorization.
    
    Args:
        message_id: The unique ID of a specific Gmail message to retrieve. If provided, the query parameter is ignored.
                   Example: "18de3456a7b890cd"
        
        query: A Gmail search query that uses Gmail's advanced search operators. The query is used to
               locate emails matching specific criteria and returns only the first matching message.
               
               **Supported Operators and Examples:**
               
               - **from:**  
                 Searches for messages sent from a specific sender.  
                 Example: from:noreply@medium.com
               
               - **to:**  
                 Searches for messages sent to a specific recipient.  
                 Example: to:support@example.com
               
               - **subject:**  
                 Searches for messages with specific text in the subject line.  
                 Example: subject:invoice
               
               - **after:** and **before:**  
                 Searches for messages sent after or before a specific date (format: YYYY/MM/DD).  
                 Example: after:2023/01/01 before:2023/12/31
               
               - **is:**  
                 Searches for messages with a particular status (e.g., unread, starred).  
                 Example: is:unread
               
               - **has:**  
                 Searches for messages that contain specific features, such as attachments.  
                 Example: has:attachment
               
               - **in:** or **label:**  
                 Searches for messages in a specific folder/label (e.g., inbox, trash, spam).  
                 Example: in:inbox or label:work
               
               **Advanced Query Syntax Best Practices:**
               
               - **Avoid Quoting Field Names:**  
                 Do not enclose search operator fields (e.g., from:, subject:) or their values in double quotes 
                 unless you are explicitly performing an exact phrase search. For example, use subject:invoice rather 
                 than "subject:invoice". Quoting these fields may cause Gmail to treat them as literal strings rather 
                 than operators.
               
               - **Exact Phrase Searches:**  
                 To search for an exact phrase within the email body or subject, enclose the phrase in double quotes.  
                 Example: subject:"monthly report"
               
               - **Logical Operators:**  
                 When combining operators, use uppercase logical operators (e.g., OR, AND, NOT) to ensure proper 
                 parsing.  
                 Example: from:github.com OR from:gitlab.com
               
               - **Literal Escape Characters:**  
                 Note that any Python escape characters (e.g., \\n, \\t) in the query string will be passed 
                 literally to the Gmail API. Ensure that your query does not inadvertently include escape sequences 
                 that alter the intended search pattern.
               
               **Example Queries:**
               
               - from:noreply@medium.com in:inbox (This is the exact query to use to get the latest Medium Daily Digest email)
               - from:github.com is:unread in:inbox
               - subject:invoice after:2023/01/01 in:inbox
               - in:spam from:newsletter
               - label:work has:attachment
               - in:trash subject:"team meeting"
               
               For complex searches, combine multiple operators without quoting the field names:
               
               - from:medium.com in:inbox after:2023/01/01 has:attachment
               
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
            - body: Full email body text in HTML format (when available, plain text as fallback)
    
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

@mcp.tool()
def extract_medium_articles(email_body: str) -> str:
    """
    Extract article information from Medium Daily Digest newsletters in HTML format.
    
    This tool parses Medium Daily Digest HTML emails and extracts article titles, author names,
    and direct article links. It uses BeautifulSoup to navigate the HTML structure, identifying
    common patterns found in Medium newsletters.
    
    IMPORTANT: This tool ONLY works with Medium Daily Digest newsletter emails in HTML format.
    It is specifically designed for the structure of Medium's email newsletters and will not
    work with other email formats.
    
    Args:
        email_body: The complete HTML content of a Medium Daily Digest email as a string.
                   This should be the raw HTML body from the email, not a plain text version.
                   
    Returns:
        str: A JSON string containing an array of article objects. Each object has:
            - "Article Name": The title of the article
            - "Link": The URL to the full article
            - "Author": The name of the article's author (or "Unknown" if not found)
            
        Example response:
        '[
            {
                "Article Name": "How to Build a Neural Network from Scratch",
                "Link": "https://medium.com/towards-data-science/neural-network-scratch-12345",
                "Author": "Jane Doe"
            },
            {
                "Article Name": "The Future of Artificial Intelligence",
                "Link": "https://medium.com/ai-magazine/future-ai-67890",
                "Author": "John Smith"
            }
        ]'
    
    Error Handling:
        All errors are handled gracefully, with the function returning specific results:
        
        - Empty JSON array: If the email is not a Medium Daily Digest, or no articles could be found
          '[]'
          
        - Partial results: If some articles were found but had incomplete information,
          those with at least a title and link will be included
          
        - Missing author: If an article's author cannot be determined, the "Author" field
          will be set to "Unknown"
          
        - Invalid HTML: If the email_body is not valid HTML or cannot be parsed,
          an empty JSON array is returned ('[]')
          
        No exceptions are raised to the caller, making this tool safe to use without
        additional error handling.
    """
    articles = []
    
    try:
        # Parse the HTML
        soup = BeautifulSoup(email_body, 'html.parser')
        
        # Check if this appears to be a Medium Daily Digest (case-insensitive)
        if "medium daily digest" not in email_body.lower() and "today's highlights" not in email_body.lower():
            return json.dumps([])
        
        # Find all article sections - using multiple strategies for robustness
        article_sections = soup.find_all('div', class_=lambda c: c and 'cd' in (c.split() if c else []))
        
        for section in article_sections:
            article = {}
            
            # Extract title from h2 element
            title_elem = section.find('h2')
            if title_elem:
                article['Article Name'] = title_elem.get_text(strip=True)
            
            # Extract author - try multiple locations where author info might be
            # Strategy 1: Look in the specific author section
            author_container = section.find('div', class_=lambda c: c and 'cl' in (c.split() if c else []))
            if author_container:
                author_span = author_container.find('span', class_=lambda c: c and 'ct' in (c.split() if c else []))
                if author_span and author_span.find('a'):
                    article['Author'] = author_span.find('a').get_text(strip=True)
            
            # Strategy 2: Look for any author-like spans if not found
            if 'Author' not in article:
                author_spans = section.find_all('span', class_=lambda c: c and 'aw' in (c.split() if c else []))
                for span in author_spans:
                    if span.find('a') and not span.find('span', class_=lambda c: c and 'in' in (c.split() if c else [])):
                        article['Author'] = span.find('a').get_text(strip=True)
                        break
            
            # Extract article link - using multiple strategies
            # Strategy 1: Find link containing the article title
            if title_elem:
                link_parent = title_elem.find_parent('a')
                if link_parent and 'href' in link_parent.attrs:
                    url_result = _get_short_url(link_parent['href'])
                    if not isinstance(url_result, dict) or "error" not in url_result:
                        article['Link'] = url_result
            
            # Strategy 2: Look in the main content div
            if 'Link' not in article:
                content_div = section.find('div', class_=lambda c: c and 'di' in (c.split() if c else []))
                if content_div:
                    link_elem = content_div.find('a', class_='ag')
                    if link_elem and 'href' in link_elem.attrs:
                        url_result = _get_short_url(link_elem['href'])
                        if not isinstance(url_result, dict) or "error" not in url_result:
                            article['Link'] = url_result
            
            # Only add articles with at least title and link
            if article.get('Article Name') and article.get('Link'):
                # Set default author if not found
                if 'Author' not in article:
                    article['Author'] = "Unknown"
                
                articles.append(article)
    
    except Exception as e:
        # If parsing fails, return empty JSON array
        print(f"Error parsing Medium Daily Digest: {str(e)}")
        return json.dumps([])
    
    # Return articles as a JSON string
    return json.dumps(articles)

@mcp.tool()
def get_medium_articles_from_gmail() -> str:
    """
    Retrieve and extract Medium articles from the latest Medium Daily Digest email in the Gmail inbox.

    This tool combines the functionality of `get_gmail_message` and `extract_medium_articles` to directly fetch
    Medium articles from the latest Medium Daily Digest email. The search query "from:noreply@medium.com in:inbox"
    is hardcoded to locate the email.

    Returns:
        str: A JSON string containing an array of article objects. Each object has:
            - "Article Name": The title of the article
            - "Link": The URL to the full article
            - "Author": The name of the article's author (or "Unknown" if not found)

        Example response:
        '{
            {
                "Article Name": "How to Build a Neural Network from Scratch",
                "Link": "https://medium.com/towards-data-science/neural-network-scratch-12345",
                "Author": "Jane Doe"
            },
            {
                "Article Name": "The Future of Artificial Intelligence",
                "Link": "https://medium.com/ai-magazine/future-ai-67890",
                "Author": "John Smith"
            }
        }'

    Error Handling:
        All errors are returned as JSON strings with an "error" key containing the error message.
        Common error scenarios:

        - No Medium Daily Digest email found:
          '{"error": "No Medium Daily Digest email found in the inbox."}'

        - Email body extraction failure:
          '{"error": "Failed to extract email body from the Medium Daily Digest email."}'

        - Article extraction failure:
          '{"error": "Failed to extract articles from the Medium Daily Digest email."}'

        - Authentication errors:
          '{"error": "Failed to authenticate with Gmail API: [specific error message]"}'

        - Missing environment variables:
          '{"error": "Missing required environment variables (GMAIL_TOKEN_PATH or GMAIL_CREDENTIALS_PATH)"}'

        - File access errors:
          '{"error": "Could not access token/credentials file: [specific error message]"}'

        - Gmail API errors:
          '{"error": "Gmail API error: [specific error message]"}'

    """
    try:
        # Hardcoded search query for Medium Daily Digest email
        query = "from:noreply@medium.com in:inbox"

        # Retrieve the latest Medium Daily Digest email
        email_response = get_gmail_message(query=query)

        if "error" in email_response:
            return json.dumps({"error": email_response["error"]})

        # Extract the email body
        email_body = email_response.get("body", "")
        if not email_body:
            return json.dumps({"error": "Failed to extract email body from the Medium Daily Digest email."})

        # Extract Medium articles from the email body
        articles_response = extract_medium_articles(email_body)
        if not articles_response:
            return json.dumps({"error": "Failed to extract articles from the Medium Daily Digest email."})

        return articles_response

    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {str(e)}"})

# Helper Functions
def _format_message(msg):
    """
    Extract and format key components from a Gmail API message object.
    
    This function processes the complex Gmail API message format, extracting metadata
    from headers and decoding the message body from base64. It handles both single-part
    and multi-part MIME messages.
    
    Processing details:
    - Header information (subject, from, to, date) is extracted directly
    - Message body is prioritized in this order:
      1. HTML content (when available)
      2. Plain text content (when HTML is not available)
    - No conversion to markdown is performed for any fields
    
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
            - body: Decoded content of the email (HTML format when available)
    """
    # Extract header information
    headers = {}
    for header in msg['payload']['headers']:
        headers[header['name']] = header['value']
    
    # Extract body parts and content - prioritize HTML content
    body_html = ""
    body_plain = ""
    
    # Function to recursively extract MIME parts
    def extract_parts(payload):
        nonlocal body_html, body_plain
        
        # Check if this is a multipart message
        if 'parts' in payload:
            for part in payload['parts']:
                extract_parts(part)
        
        # Check the MIME type and extract content
        mime_type = payload.get('mimeType', '')
        if mime_type == 'text/html' and 'body' in payload and 'data' in payload['body']:
            body_html = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        elif mime_type == 'text/plain' and 'body' in payload and 'data' in payload['body']:
            body_plain = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
    
    # Start extraction with the main payload
    extract_parts(msg['payload'])
    
    # Prioritize HTML body, fall back to plain text
    body = body_html if body_html else body_plain
    
    # If still no body content, check for simple body structure
    if not body and 'body' in msg['payload'] and 'data' in msg['payload']['body']:
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

def _get_short_url(url):
    """
    Extracts the canonical URL from a full Medium article URL by removing tracking parameters.
    
    This function processes a Medium article URL that might contain appended query parameters
    and fragments used for referral tracking or analytics. It utilizes Python's urllib.parse module
    to decompose the URL into its fundamental parts, and then rebuilds the URL to include only the
    scheme, network location (netloc), and path. This ensures that any extra tracking data is removed,
    leaving the clean, canonical URL.
    
    Args:
        url (str): The full Medium article URL, potentially containing query parameters and fragments.
    
    Returns:
        str or dict: The canonical URL constructed from the scheme, netloc, and path if parsing succeeds,
                    or a dictionary with an error message if parsing fails or the URL is invalid.
                    Error format: {"error": "Error message details"}
    """
    try:
        if not url or not isinstance(url, str):
            return {"error": "Invalid URL: URL must be a non-empty string"}
        
        parts = urlparse(url)
        
        # Verify we have enough components to form a valid URL
        if not parts.scheme or not parts.netloc:
            return {"error": "Invalid URL: Missing scheme or domain"}
            
        return urlunparse((parts.scheme, parts.netloc, parts.path, '', '', ''))
    except Exception as e:
        # Return an error dictionary instead of the original URL
        return {"error": f"URL parsing error: {str(e)}"}

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