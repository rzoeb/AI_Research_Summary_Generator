import asyncio
import os
import json
from playwright.async_api import async_playwright
import time

# Get environment variables
MEDIUM_COOKIES_FILE = os.getenv("MEDIUM_COOKIES_FILE", "medium_cookies.json")

async def main():
    """
    Interactive script to help manually log in to Medium and save authentication cookies.
    
    This tool will:
    1. Open a visible browser window
    2. Navigate to the Medium homepage
    3. Wait for you to manually log in
    4. Save your authentication cookies once you're logged in
    """
    print("\n=== Medium Cookie Generator ===")
    print("This tool will help you manually log in to Medium and save your authentication cookies.")
    print("These cookies will be used by the web scraping tool to access Medium content without hitting CAPTCHA challenges.")
    
    async with async_playwright() as p:
        # Launch browser in non-headless mode so you can interact with it
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
        )
        
        # Create a new page
        page = await context.new_page()
        
        # Navigate to Medium homepage
        print("\nOpening Medium homepage. Please log in manually through the browser window...")
        await page.goto("https://medium.com", wait_until="networkidle")
        
        # Wait for user to manually log in
        print("\nPlease complete these steps in the browser window:")
        print("1. Click on 'Sign In' button")
        print("2. Complete the login process using your email, social media, or other method")
        print("3. Verify you're successfully logged in by seeing your avatar in the top right")
        print("\nThis window will wait for 5 minutes while you complete the login.")
        
        # Check for login every 10 seconds for up to 5 minutes
        max_wait_time = 5 * 60  # 5 minutes in seconds
        start_time = time.time()
        
        login_detected = False
        while time.time() - start_time < max_wait_time:
            # Check for authentication indicators
            for selector in ['button[aria-label="User"]', 'img.avatar', 'a[href*="/@"]', 'button:has-text("Write")']:
                try:
                    if await page.locator(selector).count() > 0 and await page.locator(selector).first.is_visible():
                        login_detected = True
                        break
                except:
                    pass
            
            if login_detected:
                break
                
            # Wait before checking again
            await asyncio.sleep(10)
            print("Waiting for login... (Press Ctrl+C to cancel)")
            
        if login_detected:
            print("\n✅ Login detected! Saving cookies...")
            cookies = await context.cookies()
            
            # Ensure directory exists
            cookie_dir = os.path.dirname(MEDIUM_COOKIES_FILE)
            if cookie_dir and not os.path.exists(cookie_dir):
                os.makedirs(cookie_dir, exist_ok=True)
                
            # Save cookies to file
            with open(MEDIUM_COOKIES_FILE, "w") as f:
                json.dump(cookies, f)
                
            print(f"Cookies saved to: {MEDIUM_COOKIES_FILE}")
            print("These cookies will be used automatically by the web scraper.")
        else:
            print("\n❌ Login not detected within the 5-minute timeout.")
            print("Please try again when you have time to complete the login process.")
        
        # Close the browser
        await browser.close()
        print("\nBrowser closed. You can close this window now.")

if __name__ == "__main__":
    asyncio.run(main())