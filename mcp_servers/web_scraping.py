from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base
import os
from datetime import datetime
import json
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import datetime
import asyncio

# Initialize the MCP server
mcp = FastMCP("Web Scraping MCP Server")

# Load environment variables for Medium credentials and cookies file path
MEDIUM_EMAIL = os.getenv("MEDIUM_EMAIL", "your-email@example.com")
MEDIUM_PASSWORD = os.getenv("MEDIUM_PASSWORD", "your-password")
MEDIUM_COOKIES_FILE = os.getenv("MEDIUM_COOKIES_FILE", "medium_cookies.json")
DEBUG_MODE = os.getenv('DEBUG_MODE', 'false').lower() == 'true'

# Create screenshots directory if it doesn't exist and DEBUG_MODE is true
SCREENSHOTS_DIR = "debugging_screenshots"
if DEBUG_MODE:
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# Defining Tools
@mcp.tool()
async def validate_medium_cookies() -> dict: # The dictionary outputted by the tool will have a "debug_info" key containing the debug information if DEBUG_MODE is true" 
    """
    Validates if the saved Medium cookies are still valid.
    
    This tool checks if the Medium cookie file exists, contains valid cookie data,
    and if the cookies still provide authenticated access to Medium.com. It navigates
    to Medium.com with the saved cookies and checks for elements that indicate a logged-in
    state.
    
    No parameters are required for this tool.
    
    Returns:
        dict: A dictionary containing:
            - "valid": Boolean indicating if the cookies are valid
            - "error": Error message if validation failed, None otherwise
    """
    debug_info = {
        "timestamp": datetime.datetime.now().isoformat(),
        "cookies_file": MEDIUM_COOKIES_FILE,
        "file_exists": False,
        "cookies_loaded": False,
        "cookie_count": 0,
        "screenshots": [],
        "process_steps": [],
        "errors": []
    }
    
    def add_debug_step(step_name, details=None):
        step_info = {
            "step": step_name,
            "time": datetime.datetime.now().isoformat(),
        }
        if details:
            step_info["details"] = details
        debug_info["process_steps"].append(step_info)
    
    add_debug_step("start_validation")
    
    # Check if cookie file exists
    if not os.path.exists(MEDIUM_COOKIES_FILE):
        error_msg = f"Cookie file not found at {MEDIUM_COOKIES_FILE}"
        debug_info["errors"].append(error_msg)
        add_debug_step("file_check_failed", {"error": error_msg})
        return {
            "valid": False, 
            "error": error_msg,
            "debug_info": debug_info if DEBUG_MODE else None
        }
    
    debug_info["file_exists"] = True
    add_debug_step("file_exists")
    
    # Load cookies
    try:
        with open(MEDIUM_COOKIES_FILE, "r") as f:
            cookies = json.load(f)
            
        if not cookies or len(cookies) == 0:
            error_msg = "Cookie file exists but contains no cookies"
            debug_info["errors"].append(error_msg)
            add_debug_step("empty_cookies", {"error": error_msg})
            return {
                "valid": False, 
                "error": error_msg,
                "debug_info": debug_info if DEBUG_MODE else None
            }
            
        debug_info["cookies_loaded"] = True
        debug_info["cookie_count"] = len(cookies)
        add_debug_step("cookies_loaded", {"count": len(cookies)})
    except Exception as e:
        error_msg = f"Error loading cookies: {str(e)}"
        debug_info["errors"].append(error_msg)
        add_debug_step("loading_failed", {"error": error_msg})
        return {
            "valid": False, 
            "error": error_msg,
            "debug_info": debug_info if DEBUG_MODE else None
        }
    
    # Validate cookies with Playwright
    add_debug_step("initializing_playwright")
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)  # Use headless mode for validation
            add_debug_step("browser_launched")
            
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
            )
            add_debug_step("context_created")
            
            # Add the cookies to the context
            await context.add_cookies(cookies)
            add_debug_step("cookies_added_to_context")
            
            # Create a new page
            page = await context.new_page()
            add_debug_step("page_created")
            
            try:
                add_debug_step("navigating_to_medium")
                await page.goto("https://medium.com", wait_until="networkidle")
                
                # Check if we're logged in
                auth_indicators = [
                    'button[aria-label="User"]',
                    'img.avatar',
                    'a[href*="/@"]',
                    'button:has-text("Write")',
                    'div[data-testid="user-menu"]',
                    # Additional selectors that are more resilient to UI changes
                    'div[aria-label="Profile"]',
                    'img[alt*="Profile picture"]',
                    'button:has-text("Sign out")',
                    'a[href="/me"]',
                    'a[href="/me/stories"]',
                    'a:has-text("Member")',
                    'a:has-text("profile")',
                    # More general checks - any of these would indicate a logged-in state
                    'button:has-text("Notifications")',
                    'button:has-text("Lists")',
                    'button:has-text("Stories")'
                ]
                
                # Add HTML content check as fallback if selectors fail
                logged_in = False
                found_selector = None
                
                for selector in auth_indicators:
                    try:
                        if await page.locator(selector).count() > 0 and await page.locator(selector).is_visible():
                            logged_in = True
                            found_selector = selector
                            add_debug_step("authentication_confirmed", {"selector": selector})
                            break
                    except Exception as e:
                        add_debug_step("selector_check_failed", {"selector": selector, "error": str(e)})
                
                # Fallback check: Look for logged-in indicators in the page content if selectors didn't work
                if not logged_in:
                    add_debug_step("trying_content_based_check")
                    page_content = await page.content()
                    logged_in_indicators = [
                        "Sign out",
                        "Your stories",
                        "Your profile",
                        "Account settings",
                        "Write a story"
                    ]
                    
                    for indicator in logged_in_indicators:
                        if indicator.lower() in page_content.lower():
                            logged_in = True
                            add_debug_step("content_check_authenticated", {"indicator": indicator})
                            break
                
                # Take a screenshot for debugging
                screenshot_path = _take_screenshot(page, "cookie_validation")
                if screenshot_path:
                    debug_info["screenshots"].append(screenshot_path)
                add_debug_step("screenshot_taken", {"path": screenshot_path} if screenshot_path else {"skipped": True})
                
                if logged_in:
                    add_debug_step("validation_successful")
                    return {
                        "valid": True, 
                        "error": None,
                        "debug_info": debug_info if DEBUG_MODE else None
                    }
                else:
                    error_msg = "Cookie validation failed - Not logged into Medium"
                    debug_info["errors"].append(error_msg)
                    add_debug_step("validation_failed", {"error": error_msg})
                    return {
                        "valid": False, 
                        "error": error_msg,
                        "debug_info": debug_info if DEBUG_MODE else None
                    }
                    
            except Exception as e:
                error_msg = f"Error during validation: {str(e)}"
                debug_info["errors"].append(error_msg)
                add_debug_step("validation_exception", {"error": error_msg})
                return {
                    "valid": False, 
                    "error": error_msg,
                    "debug_info": debug_info if DEBUG_MODE else None
                }
            finally:
                await page.close()
                add_debug_step("page_closed")
        except Exception as e:
            error_msg = f"Browser automation error: {str(e)}"
            debug_info["errors"].append(error_msg)
            add_debug_step("browser_error", {"error": error_msg})
            return {
                "valid": False, 
                "error": error_msg,
                "debug_info": debug_info if DEBUG_MODE else None
            }
        finally:
            if 'browser' in locals():
                await browser.close()
                add_debug_step("browser_closed")

@mcp.tool()
async def scrape_medium_article_content(short_url: str) -> dict: # The dictionary outputted by the tool will have a "debug_info" key containing the debug information if DEBUG_MODE is true and there is an error 
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
    # Initialize debugging info
    debug_info = {
        "timestamp": datetime.datetime.now().isoformat(),
        "url": short_url,
        "screenshots": [],
        "process_steps": [],
        "cookies_saved": False,
        "cookies_loaded": False,
        "login_attempted": False,
        "login_successful": False,
        "page_title": None,
        "html_content_length": 0,
        "errors": []
    }
    
    def add_debug_step(step_name, details=None):
        step_info = {
            "step": step_name,
            "time": datetime.datetime.now().isoformat(),
        }
        if details:
            step_info["details"] = details
        debug_info["process_steps"].append(step_info)
    
    try:
        add_debug_step("start", {"url": short_url})
        
        # Validate URL format
        if not short_url or not isinstance(short_url, str):
            debug_info["errors"].append("Invalid URL: URL must be a non-empty string")
            return {
                "error": "Invalid URL: URL must be a non-empty string", 
                "debug_info": debug_info if DEBUG_MODE else None
            }
        
        parts = urlparse(short_url)
        if not parts.scheme or not parts.netloc:
            debug_info["errors"].append("Invalid URL: Missing scheme or domain")
            return {
                "error": "Invalid URL: Missing scheme or domain", 
                "debug_info": debug_info if DEBUG_MODE else None
            }
        
        # Initialize playwright and scrape the article
        add_debug_step("initializing_playwright")
        async with async_playwright() as p:
            try:
                # Use headless mode based on DEBUG_MODE
                browser = await p.chromium.launch(headless=not DEBUG_MODE)
                add_debug_step("browser_launched", {"headless": not DEBUG_MODE})
                
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
                )
                add_debug_step("context_created")
                
                # Attempt to restore session from cookies; if unavailable, perform login
                cookies_loaded = await _load_cookies(context)
                debug_info["cookies_loaded"] = cookies_loaded
                add_debug_step("cookies_load_attempt", {"success": cookies_loaded})
                
                if not cookies_loaded:
                    add_debug_step("login_required")
                    page = await context.new_page()
                    debug_info["login_attempted"] = True
                    
                    # Take screenshot at the beginning
                    screenshot_path = _take_screenshot(page, "login_start")
                    if screenshot_path:
                        debug_info["screenshots"].append(screenshot_path)
                    
                    try:
                        login_result = await _login_medium(page)
                        debug_info["login_successful"] = login_result["authenticated"]
                        add_debug_step("login_attempt", login_result)
                        
                        if login_result["authenticated"]:
                            cookies_saved = await _save_cookies(context)
                            debug_info["cookies_saved"] = cookies_saved
                            add_debug_step("cookies_saved", {"success": cookies_saved})
                        else:
                            debug_info["errors"].append(f"Failed to authenticate with Medium: {login_result['error']}")
                            # Take a screenshot of the failed login state
                            screenshot_path = _take_screenshot(page, "login_failed")
                            if screenshot_path:
                                debug_info["screenshots"].append(screenshot_path)
                            
                            return {
                                "error": f"Failed to authenticate with Medium: {login_result['error']}",
                                "debug_info": debug_info if DEBUG_MODE else None
                            }
                    except Exception as e:
                        error_msg = str(e)
                        debug_info["errors"].append(f"Login exception: {error_msg}")
                        add_debug_step("login_exception", {"error": error_msg})
                        
                        # Take a screenshot of the error state
                        screenshot_path = _take_screenshot(page, "login_exception")
                        if screenshot_path:
                            debug_info["screenshots"].append(screenshot_path)
                        
                        return {
                            "error": f"Failed to authenticate with Medium: {error_msg}",
                            "debug_info": debug_info if DEBUG_MODE else None
                        }
                    finally:
                        await page.close()
                        add_debug_step("login_page_closed")
                
                # Use a new page for scraping the article
                add_debug_step("creating_article_page")
                page = await context.new_page()
                
                try:
                    # Go directly to try accessing the article
                    add_debug_step("navigating_to_article", {"url": short_url})
                    await page.goto(short_url, wait_until="networkidle")
                    
                    # Wait longer for dynamic content to load
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(3)
                    
                    # Take a screenshot of what we're seeing
                    screenshot_path = _take_screenshot(page, "article_page")
                    if screenshot_path:
                        debug_info["screenshots"].append(screenshot_path)
                    
                    # Get page title
                    page_title = await page.title()
                    debug_info["page_title"] = page_title
                    add_debug_step("page_loaded", {"title": page_title})
                    
                    # Verify we're not on a login page or paywall
                    page_content = await page.content()
                    is_login_page = any(phrase in page_content.lower() 
                                       for phrase in ["sign in", "become a member", "join medium"])
                    
                    if is_login_page:
                        debug_info["errors"].append("Authentication failed: Redirected to login page or hit a paywall")
                        add_debug_step("auth_check_failed", {"is_login_page": True})
                        return {
                            "error": "Authentication failed: Redirected to login page or hit a paywall",
                            "debug_info": debug_info if DEBUG_MODE else None
                        }
                    
                    add_debug_step("auth_check_passed", {"is_login_page": False})
                    
                    # Scrape the article content
                    add_debug_step("scraping_article_content")
                    article_data = await _scrape_medium_article(page, short_url)
                    
                    # Add debug information to article data
                    debug_info["html_content_length"] = len(await page.content())
                    
                    # Check for article content
                    if not article_data.get("Name"):
                        debug_info["errors"].append("Failed to extract article title")
                        add_debug_step("title_extraction_failed")
                        
                        # Take a screenshot of the page for debugging
                        screenshot_path = _take_screenshot(page, "title_extraction_failed")
                        if screenshot_path:
                            debug_info["screenshots"].append(screenshot_path)
                    
                    if not article_data.get("Scraped text"):
                        debug_info["errors"].append("Failed to extract article content")
                        add_debug_step("content_extraction_failed")
                        
                        # Take a screenshot of the page for debugging
                        screenshot_path = _take_screenshot(page, "content_extraction_failed")
                        if screenshot_path:
                            debug_info["screenshots"].append(screenshot_path)
                    
                    # Always include debug info in article data during debug mode
                    if DEBUG_MODE:
                        article_data["debug_info"] = debug_info
                    
                    add_debug_step("completed", {
                        "has_title": bool(article_data.get("Name")),
                        "content_length": len(article_data.get("Scraped text", "")),
                        "image_count": len(article_data.get("Images", []))
                    })
                    
                    return article_data
                    
                except Exception as e:
                    error_msg = str(e)
                    debug_info["errors"].append(f"Article extraction error: {error_msg}")
                    add_debug_step("article_extraction_exception", {"error": error_msg})
                    
                    # Take a screenshot of the error state
                    screenshot_path = _take_screenshot(page, "article_extraction_error")
                    if screenshot_path:
                        debug_info["screenshots"].append(screenshot_path)
                    
                    return {
                        "error": f"Failed to extract article content: {error_msg}",
                        "debug_info": debug_info if DEBUG_MODE else None
                    }
                finally:
                    await page.close()
                    add_debug_step("article_page_closed")
            except Exception as e:
                error_msg = str(e)
                debug_info["errors"].append(f"Browser automation error: {error_msg}")
                add_debug_step("browser_automation_error", {"error": error_msg})
                return {
                    "error": f"Browser automation error: {error_msg}",
                    "debug_info": debug_info if DEBUG_MODE else None
                }
            finally:
                if 'browser' in locals():
                    await browser.close()
                    add_debug_step("browser_closed")
    except Exception as e:
        error_msg = str(e)
        debug_info["errors"].append(f"Unexpected error: {error_msg}")
        add_debug_step("unexpected_error", {"error": error_msg})
        return {
            "error": f"Unexpected error: {error_msg}",
            "debug_info": debug_info if DEBUG_MODE else None
        }

# Helper Functions
def _take_screenshot(page, name):
    """Helper function to take screenshots only when DEBUG_MODE is True"""
    if DEBUG_MODE:
        try:
            now = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"{SCREENSHOTS_DIR}/{name}_{now}.png"
            page.screenshot(path=screenshot_path)
            return screenshot_path
        except Exception as e:
            print(f"Failed to take screenshot: {e}")
            return None
    return None

async def _login_medium(page):
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
            - "debug": Dictionary containing debugging information
    """
    debug = {
        "steps": [],
        "selectors_found": {},
        "current_url": None,
        "page_title": None
    }
    
    def add_step(name, details=None):
        step = {"name": name, "time": datetime.datetime.now().isoformat()}
        if details:
            step.update(details)
        debug["steps"].append(step)
        
    try:
        # Save debug info about environment
        add_step("environment", {
            "email": MEDIUM_EMAIL[:3] + "..." + MEDIUM_EMAIL[-8:] if MEDIUM_EMAIL else "not_set",
            "password_length": len(MEDIUM_PASSWORD) if MEDIUM_PASSWORD else 0,
            "cookies_file": MEDIUM_COOKIES_FILE
        })
        
        # Navigate to the Medium homepage first
        add_step("navigating_to_medium_homepage")
        # Use networkidle to ensure all resources are loaded
        await page.goto("https://medium.com", wait_until="networkidle")
        debug["current_url"] = page.url
        debug["page_title"] = await page.title()
        
        # Take a screenshot of the homepage
        screenshot_path = _take_screenshot(page, "medium_homepage")
        if screenshot_path:
            add_step("medium_homepage_screenshot", {"path": screenshot_path})
        
        # Wait for page to be fully loaded
        await page.wait_for_load_state("networkidle")
        
        # Check for sign-in button (try multiple selectors)
        signin_selectors = [
            'a:has-text("Sign In")',
            'a[href*="sign-in"]',
            'a[href*="signin"]',
            'button:has-text("Sign in")'
        ]
        
        signin_button = None
        found_selector = None
        
        for selector in signin_selectors:
            try:
                # Use proper count check instead of the object check
                if await page.locator(selector).count() > 0 and await page.locator(selector).first.is_visible():
                    signin_button = page.locator(selector).first
                    found_selector = selector
                    debug["selectors_found"]["signin_button"] = selector
                    break
            except Exception as e:
                add_step("selector_check_failed", {"selector": selector, "error": str(e)})
        
        if not signin_button:
            # Take a screenshot of the page when sign-in button not found
            screenshot_path = _take_screenshot(page, "signin_button_not_found")
            if screenshot_path:
                add_step("signin_button_not_found_screenshot", {"path": screenshot_path})
            
            # Try to capture all available button text for debugging
            buttons_text = []
            for button in await page.locator('button').all():
                try:
                    text = await button.inner_text()
                    if text.strip():
                        buttons_text.append(text.strip())
                except:
                    pass
                    
            links_text = []
            for link in await page.locator('a').all():
                try:
                    text = await link.inner_text()
                    if text.strip():
                        links_text.append(text.strip())
                except:
                    pass
            
            add_step("available_ui_elements", {
                "buttons": buttons_text[:10],  # Limit to first 10 to avoid huge output
                "links": links_text[:10]
            })
            
            return {
                "authenticated": False, 
                "error": "Sign In button not found on Medium homepage",
                "debug": debug
            }
        
        add_step("clicking_signin_button", {"selector_used": found_selector})
        await signin_button.click()
        
        # Use explicit wait rather than fixed sleep
        await page.wait_for_load_state("networkidle")
        
        # Take a screenshot after clicking sign-in
        screenshot_path = _take_screenshot(page, "after_signin_click")
        if screenshot_path:
            add_step("after_signin_click_screenshot", {"path": screenshot_path})
        
        debug["current_url"] = page.url
        debug["page_title"] = await page.title()
        
        # Check for "Sign in with email" option
        email_option_selectors = [
            'button:has-text("Sign in with email")',
            'button[data-action="sign-in-with-email"]',
            'button:has-text("Email")',
            'a:has-text("sign in with email")'
        ]
        
        email_option = None
        found_selector = None
        
        for selector in email_option_selectors:
            try:
                # Use proper count check instead of the object check
                if await page.locator(selector).count() > 0 and await page.locator(selector).first.is_visible():
                    email_option = page.locator(selector).first
                    found_selector = selector
                    debug["selectors_found"]["email_option"] = selector
                    break
            except Exception as e:
                add_step("selector_check_failed", {"selector": selector, "error": str(e)})
        
        if not email_option:
            # Take a screenshot when email option not found
            now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"{SCREENSHOTS_DIR}/email_option_not_found_{now}.png"
            await page.screenshot(path=screenshot_path)
            add_step("email_option_not_found_screenshot", {"path": screenshot_path})
            
            # Try to capture all available button text for debugging
            buttons_text = []
            for button in await page.locator('button').all():
                try:
                    text = await button.inner_text()
                    if text.strip():
                        buttons_text.append(text.strip())
                except:
                    pass
            
            add_step("available_buttons", {"buttons": buttons_text[:10]})
            
            return {
                "authenticated": False, 
                "error": "Email sign-in option not found",
                "debug": debug
            }
        
        add_step("clicking_email_option", {"selector_used": found_selector})
        await email_option.click()
        
        # Use explicit wait rather than fixed sleep
        await page.wait_for_load_state("networkidle")
        
        # Take a screenshot after clicking email option
        screenshot_path = _take_screenshot(page, "after_email_option_click")
        if screenshot_path:
            add_step("after_email_option_click_screenshot", {"path": screenshot_path})
        
        # Wait for the email input field to appear
        # Use a more explicit wait for the email field
        try:
            await page.wait_for_selector('input[type="email"]', state="visible", timeout=5000)
        except:
            # Try alternative selectors if the specific one fails
            pass
        
        # Find email input field
        email_field_selectors = [
            'input[type="email"]',
            'input[name="email"]',
            'input[id*="email"]',
            'input[placeholder*="email"]'
        ]
        
        email_field = None
        found_selector = None
        
        for selector in email_field_selectors:
            try:
                # Use proper count check instead of the object check
                if await page.locator(selector).count() > 0 and await page.locator(selector).first.is_visible():
                    email_field = page.locator(selector).first
                    found_selector = selector
                    debug["selectors_found"]["email_field"] = selector
                    break
            except Exception as e:
                add_step("selector_check_failed", {"selector": selector, "error": str(e)})
        
        if not email_field:
            # Take a screenshot when email field not found
            screenshot_path = _take_screenshot(page, "email_field_not_found")
            if screenshot_path:
                add_step("email_field_not_found_screenshot", {"path": screenshot_path})
            
            return {
                "authenticated": False, 
                "error": "Email input field not found",
                "debug": debug
            }
        
        add_step("filling_email_field", {"selector_used": found_selector, "email_length": len(MEDIUM_EMAIL)})
        await email_field.fill(MEDIUM_EMAIL)
        
        # Give a short pause after filling
        await asyncio.sleep(1)
        
        # Find continue button
        continue_button_selectors = [
            'button:has-text("Continue")',
            'button[type="submit"]',
            'button.button--primary'
        ]
        
        continue_button = None
        found_selector = None
        
        for selector in continue_button_selectors:
            try:
                # Use proper count check instead of the object check
                if await page.locator(selector).count() > 0 and await page.locator(selector).first.is_visible():
                    continue_button = page.locator(selector).first
                    found_selector = selector
                    debug["selectors_found"]["continue_button"] = selector
                    break
            except Exception as e:
                add_step("selector_check_failed", {"selector": selector, "error": str(e)})
        
        if not continue_button:
            # Take a screenshot when continue button not found
            now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"{SCREENSHOTS_DIR}/continue_button_not_found_{now}.png"
            await page.screenshot(path=screenshot_path)
            add_step("continue_button_not_found_screenshot", {"path": screenshot_path})
            
            return {
                "authenticated": False, 
                "error": "Continue button not found",
                "debug": debug
            }
        
        add_step("clicking_continue_button", {"selector_used": found_selector})
        await continue_button.click()
        
        # Wait for the network to be idle
        await page.wait_for_load_state("networkidle")
        
        # Take a screenshot after clicking continue
        now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = f"{SCREENSHOTS_DIR}/after_continue_click_{now}.png"
        await page.screenshot(path=screenshot_path)
        add_step("after_continue_click_screenshot", {"path": screenshot_path})
        
        debug["current_url"] = page.url
        debug["page_title"] = await page.title()
        
        # Wait for page to stabilize
        await asyncio.sleep(2)
        
        # Check for password field
        password_field_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            'input[id*="password"]'
        ]
        
        password_field = None
        found_selector = None
        
        for selector in password_field_selectors:
            try:
                # Use proper count check instead of the object check
                if await page.locator(selector).count() > 0 and await page.locator(selector).first.is_visible():
                    password_field = page.locator(selector).first
                    found_selector = selector
                    debug["selectors_found"]["password_field"] = selector
                    break
            except Exception as e:
                add_step("selector_check_failed", {"selector": selector, "error": str(e)})
        
        if password_field:
            add_step("filling_password_field", {
                "selector_used": found_selector,
                "password_length": len(MEDIUM_PASSWORD) if MEDIUM_PASSWORD else 0
            })
            await password_field.fill(MEDIUM_PASSWORD)
            await asyncio.sleep(1)
            
            # Find sign in button
            signin_button_selectors = [
                'button:has-text("Sign in")',
                'button[type="submit"]',
                'button.button--primary'
            ]
            
            signin_button = None
            found_selector = None
            
            for selector in signin_button_selectors:
                try:
                    # Use proper count check instead of the object check
                    if await page.locator(selector).count() > 0 and await page.locator(selector).first.is_visible():
                        signin_button = page.locator(selector).first
                        found_selector = selector
                        debug["selectors_found"]["password_signin_button"] = selector
                        break
                except Exception as e:
                    add_step("selector_check_failed", {"selector": selector, "error": str(e)})
            
            if not signin_button:
                # Take a screenshot when sign in button not found
                now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = f"{SCREENSHOTS_DIR}/signin_button_not_found_{now}.png"
                await page.screenshot(path=screenshot_path)
                add_step("signin_button_not_found_screenshot", {"path": screenshot_path})
                
                return {
                    "authenticated": False, 
                    "error": "Sign in button not found after password entry",
                    "debug": debug
                }
            
            add_step("clicking_signin_button", {"selector_used": found_selector})
            await signin_button.click()
            
            # Wait for the network to be idle
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)
            
            # Take a screenshot after clicking sign in
            now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"{SCREENSHOTS_DIR}/after_signin_password_{now}.png"
            await page.screenshot(path=screenshot_path)
            add_step("after_signin_password_screenshot", {"path": screenshot_path})
        else:
            add_step("no_password_field_found", {"likely_using_email_link": True})
        
        # Verify login success by checking for user-specific elements
        auth_check_selectors = [
            'button[aria-label="User"]',   # Current avatar button
            'img.avatar',                  # Avatar image
            'a[href*="/@"]',               # Profile link
            'a[href="/me"]',               # "Me" link
            'button:has-text("Write")',    # Write button (logged-in users)
            'div[data-testid="user-menu"]' # User menu
        ]
        
        is_authenticated = False
        authenticated_selector = None
        
        for selector in auth_check_selectors:
            try:
                # Use proper count check instead of the object check
                if await page.locator(selector).count() > 0 and await page.locator(selector).first.is_visible():
                    is_authenticated = True
                    authenticated_selector = selector
                    debug["selectors_found"]["auth_confirmation"] = selector
                    break
            except Exception as e:
                add_step("auth_check_failed", {"selector": selector, "error": str(e)})
        
        if is_authenticated:
            add_step("authentication_successful", {"selector_found": authenticated_selector})
            
            # Take a screenshot of success state
            now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"{SCREENSHOTS_DIR}/login_success_{now}.png"
            await page.screenshot(path=screenshot_path)
            add_step("login_success_screenshot", {"path": screenshot_path})
            
            return {"authenticated": True, "error": None, "debug": debug}
        else:
            add_step("authentication_failed")
            
            # Take a screenshot of failed state
            now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"{SCREENSHOTS_DIR}/login_failed_{now}.png"
            await page.screenshot(path=screenshot_path)
            add_step("login_failed_screenshot", {"path": screenshot_path})
            
            # Additional check: See if there's an error message
            error_message = ""
            try:
                for error_selector in ['.error-message', '.form-error', '.errorMessage']:
                    if await page.locator(error_selector).count() > 0:
                        error_message = await page.locator(error_selector).first.inner_text()
                        add_step("error_message_found", {"message": error_message})
                        break
            except:
                pass
            
            # Check if we got redirected to a verify page (2FA)
            if "verify" in page.url.lower():
                return {
                    "authenticated": False, 
                    "error": "Two-factor authentication required. Manual login needed.",
                    "debug": debug
                }
            
            # Check for CAPTCHA - this would require human intervention
            page_content = await page.content()
            if "captcha" in page_content.lower():
                return {
                    "authenticated": False, 
                    "error": "CAPTCHA detected. Manual login required.",
                    "debug": debug
                }
            
            return {
                "authenticated": False, 
                "error": f"Could not verify successful login. {error_message}",
                "debug": debug
            }
        
    except Exception as e:
        error_msg = str(e)
        add_step("exception", {"error": error_msg})
        
        # Take a screenshot of the exception state
        try:
            now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"{SCREENSHOTS_DIR}/login_exception_{now}.png"
            await page.screenshot(path=screenshot_path)
            add_step("exception_screenshot", {"path": screenshot_path})
        except:
            pass
        
        return {"authenticated": False, "error": error_msg, "debug": debug}

async def _save_cookies(context):
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
        cookies = await context.cookies()
        
        # Check if we actually have cookies to save
        if not cookies or len(cookies) == 0:
            return False
            
        # Try to save cookies
        cookie_dir = os.path.dirname(MEDIUM_COOKIES_FILE)
        if cookie_dir and not os.path.exists(cookie_dir):
            os.makedirs(cookie_dir, exist_ok=True)
            
        with open(MEDIUM_COOKIES_FILE, "w") as f:
            json.dump(cookies, f)
            
        # Verify file was created
        if not os.path.exists(MEDIUM_COOKIES_FILE):
            return False
            
        return True
    except Exception as e:
        return False

async def _load_cookies(context):
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
            
        # Check if we have valid cookies
        if not cookies or len(cookies) == 0:
            return False
            
        await context.add_cookies(cookies)
        return True
    except Exception:
        return False

def _process_article_html(html):
    """
    Processes the HTML content of an article, replacing image tags with inline placeholders.
    
    This function parses the article's HTML content using BeautifulSoup and traverses the document.
    When it encounters an <img> tag, it replaces the tag with a placeholder string in the format:
    "[IMG: image_url]". The function then returns a plain text representation of the article with
    these inline placeholders and a list of image URLs found in the article content.
    
    Args:
        html (str): The HTML content of the article.
    
    Returns:
        tuple: A tuple containing:
            - str: Plain text with image placeholders
            - list: List of image URLs found in the article content
    """
    if not html or len(html.strip()) == 0:
        return "", []
        
    soup = BeautifulSoup(html, "html.parser")
    image_urls = []
    
    # Replace each image tag with a placeholder containing its 'src' attribute
    # and collect article image URLs simultaneously
    for img in soup.find_all("img"):
        src = img.get("src")
        if src:
            # Filter to include only meaningful article images (exclude tiny UI elements)
            # Medium article images typically have specific URL patterns or size attributes
            is_article_image = False
            
            # Check image URL patterns common for Medium article content images
            medium_image_patterns = [
                "miro.medium.com",
                "/resize:",
                "/max/",
                "/fit:",
                "/progressive:"
            ]
            
            if any(pattern in src for pattern in medium_image_patterns):
                is_article_image = True
            
            # Check image dimensions via attributes (if available)
            # Medium article images are typically larger than UI elements
            try:
                width = img.get('width')
                height = img.get('height')
                if width and height:
                    # Convert to integers if they're strings
                    if isinstance(width, str) and width.isdigit():
                        width = int(width)
                    if isinstance(height, str) and height.isdigit():
                        height = int(height)
                    
                    # If dimensions suggest it's a substantial image, include it
                    if (isinstance(width, int) and isinstance(height, int) and 
                            width > 100 and height > 100):
                        is_article_image = True
            except:
                pass
                
            # Check parent elements - article images are often in specific containers
            parent_classes = []
            parent = img.parent
            for _ in range(3):  # Check up to 3 levels up
                if parent and parent.get('class'):
                    parent_classes.extend(parent.get('class'))
                if parent:
                    parent = parent.parent
                    
            article_content_classes = ['graf-image', 'section-image', 'post-image', 'progressiveMedia']
            if any(cls in parent_classes for cls in article_content_classes):
                is_article_image = True
                
            # Replace with placeholder only if it's identified as an article image
            if is_article_image:
                placeholder = f"[IMG: {src}]"
                image_urls.append(src)
                img.replace_with(placeholder)
            else:
                # Remove non-article images without creating placeholders
                img.replace_with("")
    
    # Use a space as a separator to ensure text elements remain separated
    return soup.get_text(separator=" ", strip=True), image_urls

async def _scrape_medium_article(page, short_url):
    """
    Scrapes a Medium article by navigating to its canonical URL and extracting key content.
    
    This function navigates to the article, waits for dynamic content to load, and extracts:
      - The article's title (from the page title)
      - The article's full text with inline image placeholders embedded at the specific locations
        where images originally appear (by processing the inner HTML of the <article> element)
      - A list of image URLs that are actually part of the article content (not UI elements)
    
    Args:
        page: The Playwright page instance used to navigate and extract content.
        short_url (str): The canonical URL (without tracking parameters) constructed from the URL scheme, 
                         netloc, and path.
    
    Returns:
        dict: A dictionary containing:
            - 'Name': The title of the article.
            - 'Link': The canonical URL of the article.
            - 'Scraped text': The plain text content of the article with image placeholders inserted.
            - 'Images': A list of article image URLs extracted from the article content.
            - 'article_debug': (Only when DEBUG_MODE=True) Dictionary containing debugging information:
                - title: Article title found
                - url: Current page URL
                - content_length: Length of the raw HTML content
                - selectors_tried: List of attempted article selectors and their results
                - using_body_fallback: Whether body content was used as fallback
                - article_image_count: Number of images found in the article
                - processed_text_length: Length of the final processed text
    """
    # Get the article title (strip " | Medium" suffix if present)
    article_name = await page.title()
    if article_name and " | Medium" in article_name:
        article_name = article_name.split(" | Medium")[0]
    
    # Debug info for article extraction
    article_debug = {
        "title": article_name,
        "url": page.url,
        "content_length": len(await page.content()),
        "selectors_tried": []
    }
    
    # Find the article element - try multiple selectors that might match Medium's structure
    article_selectors = [
        "article",
        "div[role='article']",
        "section.pw-post-body",
        "section[role='main']",
        "div.story",
        "div.meteredContent",
        "div.postArticle-content",
        "div.section-inner"
    ]
    
    article_html = ""
    for selector in article_selectors:
        try:
            if await page.locator(selector).count() > 0:
                article_html = await page.locator(selector).first.inner_html()
                article_debug["selectors_tried"].append({
                    "selector": selector,
                    "found": True,
                    "content_length": len(article_html)
                })
                if article_html and len(article_html.strip()) > 0:
                    break
            else:
                article_debug["selectors_tried"].append({
                    "selector": selector,
                    "found": False
                })
        except Exception as e:
            article_debug["selectors_tried"].append({
                "selector": selector,
                "error": str(e)
            })

    # If we still don't have article content, take body as fallback
    if not article_html:
        try:
            article_html = await page.inner_html("body")
            article_debug["using_body_fallback"] = True
        except Exception as e:
            article_debug["body_fallback_error"] = str(e)
    
    # Process the HTML to insert image placeholders and get article image URLs
    processed_text, article_image_urls = _process_article_html(article_html)
    
    article_debug["article_image_count"] = len(article_image_urls)
    article_debug["processed_text_length"] = len(processed_text)
    
    return {
        "Name": article_name,
        "Link": short_url,
        "Scraped text": processed_text,
        "Images": article_image_urls,  # Now using only article images from processed content
        "article_debug": article_debug if DEBUG_MODE else None
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
