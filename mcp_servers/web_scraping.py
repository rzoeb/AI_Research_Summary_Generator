from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base
import os
import time
import json
from urllib.parse import urlparse, urlunparse
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# Initialize the MCP server
mcp = FastMCP("Web Scraping MCP Server")

# Load environment variables for Medium credentials and cookies file path
MEDIUM_EMAIL = os.getenv("MEDIUM_EMAIL", "your-email@example.com")
MEDIUM_PASSWORD = os.getenv("MEDIUM_PASSWORD", "your-password")
MEDIUM_COOKIES_FILE = os.getenv("MEDIUM_COOKIES_FILE", "medium_cookies.json")

# Defining Tools
@mcp.tool()
def scrape_medium_article_content(short_url: str) -> dict:
    """
    Scrapes a Medium article for its full content using browser automation with Playwright.
    
    This tool navigates to a Medium article, ensures proper authentication using saved session cookies or
    performing a login if necessary, and extracts the article's content, including the title, full text with
    inline image placeholders, and all image URLs present in the article.
    
    Args:
        short_url: The canonical URL of the Medium article to scrape. This should be the clean URL without
                  any tracking parameters, typically in the format "https://medium.com/..." or
                  "https://[publication-name].medium.com/...".
                  
    Returns:
        dict: On success, returns a dictionary containing the article details:
            - "Name": The title of the article as it appears in the browser tab.
            - "Link": The canonical URL of the article (same as the input short_url).
            - "Scraped text": The full text content of the article with image placeholders in the format
                             "[IMG: image_url]" inserted at the positions where images appear in the article.
            - "Images": A list of image URLs extracted from the article.
    
    Error Handling:
        All errors are returned as dictionaries with an "error" key containing the error message.
        Common error scenarios:
        
        - Invalid URL:
          {"error": "Invalid URL provided: [details]"}
          
        - Authentication failure:
          {"error": "Failed to authenticate with Medium: [details]"}
          
        - Navigation error:
          {"error": "Failed to navigate to article: [details]"}
          
        - Content extraction error:
          {"error": "Failed to extract article content: [details]"}
          
        - Browser/Playwright error:
          {"error": "Browser automation error: [details]"}
    """
    try:
        # Validate URL format
        if not short_url or not isinstance(short_url, str):
            return {"error": "Invalid URL: URL must be a non-empty string"}
        
        parts = urlparse(short_url)
        if not parts.scheme or not parts.netloc:
            return {"error": "Invalid URL: Missing scheme or domain"}
        
        # Initialize playwright and scrape the article
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)  # Use headless=True for production
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36"
                )
                
                # Attempt to restore session from cookies; if unavailable, perform login
                login_status = {"authenticated": False, "error": None}
                if not _load_cookies(context):
                    page = context.new_page()
                    try:
                        login_status = _login_medium(page)
                        if login_status["authenticated"]:
                            _save_cookies(context)
                        else:
                            return {"error": f"Failed to authenticate with Medium: {login_status['error']}"}
                    except Exception as e:
                        return {"error": f"Failed to authenticate with Medium: {str(e)}"}
                    finally:
                        page.close()
                
                # Use a new page for scraping the article
                page = context.new_page()
                try:
                    # Go directly to try accessing the article to confirm our authentication worked
                    page.goto(short_url, wait_until="load")
                    time.sleep(5)  # Allow time for dynamic content and scripts to load
                    
                    # Verify we're not on a login page or paywall
                    if "sign in" in page.title().lower() or "become a member" in page.content().lower():
                        return {"error": "Authentication failed: Redirected to login page or hit a paywall"}
                    
                    # Scrape the article content
                    article_data = _scrape_medium_article(page, short_url)
                    
                    # Validate the article data
                    if not article_data.get("Name"):
                        return {"error": "Failed to extract article title"}
                    
                    if not article_data.get("Scraped text"):
                        return {"error": "Failed to extract article content"}
                    
                    return article_data
                except Exception as e:
                    return {"error": f"Failed to extract article content: {str(e)}"}
                finally:
                    page.close()
            except Exception as e:
                return {"error": f"Browser automation error: {str(e)}"}
            finally:
                if 'browser' in locals():
                    browser.close()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}

# Helper Functions
def _login_medium(page):
    """
    Logs into Medium using provided credentials via a simulated user login flow.
    
    This function navigates to the Medium sign-in page, initiates the email-based login process,
    and fills in the user's email (and password if prompted). It waits for a user-specific element,
    such as an avatar image, to appear on the page which indicates a successful login.
    
    Args:
        page: The Playwright page instance used for browser automation.
    
    Returns:
        dict: A status dictionary containing:
            - "authenticated": Boolean indicating if authentication was successful
            - "error": Error message string if authentication failed, None otherwise
    """
    try:
        # Navigate to the Medium homepage first
        page.goto("https://medium.com", wait_until="load")
        time.sleep(3)
        
        # Click the Sign In button in the top right
        signin_button = page.locator('a:has-text("Sign In")').first
        if not signin_button:
            return {"authenticated": False, "error": "Sign In button not found"}
        
        signin_button.click()
        time.sleep(2)
        
        # Click on "Sign in with email" option
        email_option = page.locator('button:has-text("Sign in with email")').first
        if not email_option:
            # Try alternative selectors
            email_option = page.locator('button[data-action="sign-in-with-email"]').first
            if not email_option:
                return {"authenticated": False, "error": "Email sign-in option not found"}
        
        email_option.click()
        time.sleep(2)
        
        # Fill in the email address
        email_field = page.locator('input[type="email"]').first
        if not email_field:
            return {"authenticated": False, "error": "Email input field not found"}
        
        email_field.fill(MEDIUM_EMAIL)
        time.sleep(1)
        
        # Click continue
        continue_button = page.locator('button:has-text("Continue")').first
        if not continue_button:
            return {"authenticated": False, "error": "Continue button not found"}
        
        continue_button.click()
        time.sleep(3)
        
        # Check if password field appears (it should for most accounts)
        password_field = page.locator('input[type="password"]').first
        if password_field:
            password_field.fill(MEDIUM_PASSWORD)
            time.sleep(1)
            
            # Click sign in
            signin_button = page.locator('button:has-text("Sign in")').first
            if not signin_button:
                return {"authenticated": False, "error": "Sign in button not found after password entry"}
            
            signin_button.click()
            time.sleep(5)
        
        # Verify we're logged in by checking for user avatar or profile elements
        # Try multiple possible elements that would indicate successful login
        is_authenticated = False
        selectors_to_try = [
            'button[aria-label="User"]',   # Current avatar button
            'img.avatar',                  # Avatar image
            'a[href*="/@"]',               # Profile link
            'a[href="/me"]'                # "Me" link
        ]
        
        for selector in selectors_to_try:
            if page.locator(selector).count() > 0:
                is_authenticated = True
                break
        
        if not is_authenticated:
            # Take screenshot for debugging
            page.screenshot(path="medium_login_failed.png")
            return {"authenticated": False, "error": "Could not verify successful login"}
        
        return {"authenticated": True, "error": None}
        
    except Exception as e:
        return {"authenticated": False, "error": str(e)}

def _save_cookies(context):
    """
    Saves the current browser context cookies to a file for persistent session management.
    
    This function retrieves all cookies from the given Playwright browser context and writes them
    to a JSON file. These cookies can later be reloaded to maintain a logged-in session without
    needing to perform the login flow again.
    
    Args:
        context: The Playwright browser context containing session cookies.
    
    Returns:
        bool: True if cookies were successfully saved, False otherwise
    """
    try:
        cookies = context.cookies()
        with open(MEDIUM_COOKIES_FILE, "w") as f:
            json.dump(cookies, f)
        return True
    except Exception as e:
        return False

def _load_cookies(context):
    """
    Loads cookies from a file and adds them to the provided browser context to restore a session.
    
    This function attempts to read cookies from a predefined JSON file. If successful, the cookies
    are added to the provided Playwright browser context. This allows the user to bypass the login
    process if a valid session is already stored.
    
    Args:
        context: The Playwright browser context where cookies will be added.
    
    Returns:
        bool: True if cookies were successfully loaded and added; False otherwise.
    """
    try:
        if not os.path.exists(MEDIUM_COOKIES_FILE):
            return False
            
        with open(MEDIUM_COOKIES_FILE, "r") as f:
            cookies = json.load(f)
            context.add_cookies(cookies)
        return True
    except Exception:
        return False

def _process_article_html(html):
    """
    Processes the HTML content of an article, replacing image tags with inline placeholders.
    
    This function parses the article's HTML content using BeautifulSoup and traverses the document.
    When it encounters an <img> tag, it replaces the tag with a placeholder string in the format:
    "[IMG: image_url]". The function then returns a plain text representation of the article with
    these inline placeholders. This preserves the relative ordering of text and images for subsequent
    processing by an LLM.
    
    Args:
        html (str): The HTML content of the article.
    
    Returns:
        str: A plain text representation of the article where image tags are replaced by placeholders
             indicating the image URL.
    """
    if not html or len(html.strip()) == 0:
        return ""
        
    soup = BeautifulSoup(html, "html.parser")
    
    # Replace each image tag with a placeholder containing its 'src' attribute.
    for img in soup.find_all("img"):
        src = img.get("src")
        placeholder = f"[IMG: {src}]"
        img.replace_with(placeholder)
    
    # Use a space as a separator to ensure text elements remain separated.
    return soup.get_text(separator=" ", strip=True)

def _scrape_medium_article(page, short_url):
    """
    Scrapes a Medium article by navigating to its canonical URL and extracting key content.
    
    This function navigates to the article, waits for dynamic content to load, and extracts:
      - The article's title (from the page title)
      - The article's full text with inline image placeholders embedded at the specific locations
        where images originally appear (by processing the inner HTML of the <article> element)
    
    Args:
        page: The Playwright page instance used to navigate and extract content.
        short_url (str): The canonical URL (without tracking parameters) constructed from the URL scheme, 
                         netloc, and path.
    
    Returns:
        dict: A dictionary containing:
            - 'Name': The title of the article.
            - 'Link': The canonical URL of the article.
            - 'Scraped text': The plain text content of the article with image placeholders inserted.
            - 'Images': A list of image URLs extracted from the article (for reference).
    """
    # Get the article title
    article_name = page.title()
    
    # Find the article element - try multiple selectors that might match Medium's structure
    article_selectors = [
        "article",
        "div[role='article']",
        "section[role='main']",
        "div.story"
    ]
    
    article_html = ""
    for selector in article_selectors:
        if page.locator(selector).count() > 0:
            article_html = page.locator(selector).first.inner_html()
            break
    
    # If we still don't have article content, take body as fallback
    if not article_html:
        article_html = page.inner_html("body")
    
    # Process the HTML to insert image placeholders in the correct locations.
    processed_text = _process_article_html(article_html)
    
    # Extract image URLs separately
    image_urls = []
    images = page.locator("img").all()
    for img in images:
        src = img.get_attribute("src")
        if src:
            image_urls.append(src)
    
    return {
        "Name": article_name,
        "Link": short_url,
        "Scraped text": processed_text,
        "Images": image_urls
    }

# Ensure the MCP server is exposed properly
if __name__ == "__main__":
    mcp.run()

# MCP Developer API Reference:

# # Defining Resource Templates - Placeholder
# @mcp.resource("article://{url}")
# def get_article_info(url: str) -> str:
#     """Get information about an article at the given URL."""
#     return f"Article at {url}!"

# # Defining Resources - Placeholder
# @mcp.resource("config://app")
# def get_standard_greeting() -> str:
#     """App configuration message."""
#     return "Hello, World!"

# # Defining Prompts - Placeholder
# @mcp.prompt()
# def article_summary(article_text: str) -> list[base.Message]:
#     return [
#         base.UserMessage("Here's an article:"),
#         base.UserMessage(article_text),
#         base.AssistantMessage("I'll help summarize that. What aspects are you interested in?"),
#     ]
