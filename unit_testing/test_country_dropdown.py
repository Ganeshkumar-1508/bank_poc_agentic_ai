"""
Test script to verify the country dropdown in Financial News page
displays all countries from the API.
"""
from playwright.sync_api import sync_playwright
import time

def test_country_dropdown():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print("Navigating to Financial News page...")
        page.goto('http://localhost:8089/financial-news/')
        
        # Wait for the page to fully load
        page.wait_for_load_state('networkidle')
        
        # Wait a bit for the countries to load via API
        time.sleep(2)
        
        # Check if dropdown exists
        country_dropdown = page.locator('#news_country')
        is_present = country_dropdown.count() > 0
        
        print(f"Country dropdown present: {is_present}")
        
        if is_present:
            # Get all options in the dropdown
            options = country_dropdown.locator('option').all()
            option_count = len(options)
            
            print(f"Number of options in dropdown: {option_count}")
            
            # Get the text of each option to see what countries are there
            print("\nFirst 10 countries in dropdown:")
            for i, option in enumerate(options[:10]):
                text = option.text_content()
                print(f"  {i+1}. {text}")
            
            print(f"\n... and {option_count - 10} more" if option_count > 10 else "")
            
            # Take a screenshot showing the dropdown
            page.screenshot(path='Test/outputs/country_dropdown_screenshot.png', full_page=True)
            print("\nScreenshot saved to Test/outputs/country_dropdown_screenshot.png")
            
            # Check if we have a significant number of countries (should be ~250)
            if option_count >= 200:
                print(f"\n✓ SUCCESS: Dropdown contains {option_count} countries (expected ~250)")
            elif option_count > 0:
                print(f"\n⚠ WARNING: Dropdown only contains {option_count} countries (expected ~250)")
            else:
                print("\n✗ ERROR: Dropdown is empty!")
        else:
            print("ERROR: Country dropdown not found on the page!")
            page.screenshot(path='Test/outputs/country_dropdown_error.png', full_page=True)
        
        browser.close()

if __name__ == "__main__":
    test_country_dropdown()