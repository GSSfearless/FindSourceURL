import asyncio
from playwright.async_api import async_playwright, Playwright, Page, Browser, TimeoutError as PlaywrightTimeoutError
import os
from dotenv import load_dotenv
import traceback # For better error logging
import base64 # For encoding screenshot
from io import BytesIO # For handling image bytes
from PIL import Image # For image resizing
import re # For regular expressions
import json # For potentially parsing tool message content
from typing import TypedDict, Annotated, List, Union, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
import logging # Ensure logging is imported

# --- LangChain & LangGraph Imports ---
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.tools import tool
from langchain.globals import set_debug
from langgraph.graph import StateGraph, END # Import StateGraph and END
# from langgraph.checkpoint.sqlite import SqliteSaver # <<< COMMENTED OUT this unused import - Now TRULY commenting out

from bs4 import BeautifulSoup

# Assuming setup_logging() is defined somewhere and initializes a logger instance
# For example:
# def setup_logging():
#     l = logging.getLogger(__name__)
#     # ... configure l ...
#     return l
# logger = setup_logging() 
# OR, if logger is configured more directly:
logger = logging.getLogger(__name__) # Default way to get a logger
# Ensure your logging configuration (level, handlers) is set up appropriately for this logger.
# If you have a global `setup_logging` function that does this, ensure it's called before nodes are run.

# <<< ADDED TOP-LEVEL DEBUG PRINT >>>
print("[DEBUG] agent_main.py script started")
# <<< END ADDED SECTION >>>

# Load environment variables from .env file
load_dotenv()

# --- Enable LangChain Debug Mode ---
set_debug(False)
print("[LangChain] Debug mode disabled (set_debug(False)). Relying on custom prints.")

# --- LLM Initialization ---
try:
    # Using GPT-4o as it's generally strong in reasoning and potentially vision later
    # Ensure your OpenAI key has access to this model or change to gpt-3.5-turbo etc.
    llm = ChatOpenAI(model="gpt-4o", temperature=0, max_tokens=1024) # Using gpt-4o, explicitly set max_tokens
    print("ChatOpenAI LLM initialized successfully with gpt-4o.")
except Exception as e:
    print(f"Error initializing ChatOpenAI: {e}")
    print("Please ensure your OPENAI_API_KEY is set correctly in the .env file and has access to gpt-4o.")
    exit()

# --- Playwright Browser/Page Management ---
_playwright_instance: Playwright | None = None
_browser_instance: Browser | None = None
_page_instance: Page | None = None # Global page instance for the agent's current context

async def get_playwright() -> Playwright:
    global _playwright_instance
    if _playwright_instance is None:
        print("[Browser Manager] Starting Playwright...")
        _playwright_instance = await async_playwright().start()
    return _playwright_instance

async def get_browser(p: Playwright | None = None) -> Browser:
    global _browser_instance
    if _browser_instance is None:
        pw = p or await get_playwright()
        try:
            # Running headless=False for initial debugging of the agent flow
            _browser_instance = await pw.chromium.launch(headless=False, slow_mo=100) 
            print("[Browser Manager] New browser instance launched.")
        except Exception as e:
            print(f"[Browser Manager] Error launching browser: {e}")
            raise
    return _browser_instance

async def get_page(b: Browser | None = None) -> Page:
    """Gets the current page instance, creating it if necessary."""
    global _page_instance
    if _page_instance is None or _page_instance.is_closed():
        browser = b or await get_browser()
        try:
            _page_instance = await browser.new_page()
            print("[Browser Manager] New page instance created.")
            await _page_instance.set_viewport_size({"width": 1366, "height": 768})
        except Exception as e:
            print(f"[Browser Manager] Error creating new page: {e}")
            raise
    return _page_instance

async def close_page_and_browser():
    global _page_instance, _browser_instance, _playwright_instance
    if _page_instance and not _page_instance.is_closed():
        await _page_instance.close()
        _page_instance = None
        print("[Browser Manager] Page instance closed.")
    if _browser_instance and _browser_instance.is_connected(): # Check if connected before closing
        await _browser_instance.close()
        _browser_instance = None
        print("[Browser Manager] Browser instance closed.")
    if _playwright_instance:
        await _playwright_instance.stop()
        _playwright_instance = None
        print("[Browser Manager] Playwright instance stopped.")

# Helper function to filter screenshot from state for cleaner logging
def filter_screenshot_from_state(state_dict: dict) -> dict:
    if not isinstance(state_dict, dict):
        # If it's not a dict (e.g., None or some other type passed by mistake), return it as is.
        # This can happen if a node returns something unexpected.
        logger.debug(f"[Filter State] Input was not a dict, returning as is: {type(state_dict)}")
        return state_dict 
    filtered_state = state_dict.copy()
    if "screenshot" in filtered_state and filtered_state["screenshot"]:
        if isinstance(filtered_state["screenshot"], str):
            # Limit the logged length to avoid excessive log even for length calculation
            screenshot_len_kb = len(filtered_state["screenshot"]) / 1024
            if screenshot_len_kb > 100: # Only show actual length if it's somewhat reasonable
                 filtered_state["screenshot"] = f"[...screenshot_base64_omitted (len: {screenshot_len_kb:.1f}KB)...]"
            else:
                 filtered_state["screenshot"] = f"[...screenshot_base64_omitted (len: {screenshot_len_kb:.1f}KB)...]"
        else:
            filtered_state["screenshot"] = "[...screenshot_base64_omitted (not a string format)...]"
    return filtered_state

# Helper function to capture current page state - MOVED AND MODIFIED
async def _capture_current_page() -> dict:
    """Captures current page URL, content, and screenshot. Handles errors."""
    page = await get_page()
    if not page or page.is_closed():
        logger.error("[Capture Page] Page not available or closed.")
        return {"current_url": None, "page_content": None, "screenshot": None, "error_message": "Page not available for capture."}
    try:
        logger.debug("[Capture Page] Getting URL, HTML content, and screenshot...")
        url = page.url
        # content = await page.content() # Full content can be very large

        # Simplified text extraction
        text_content = await page.evaluate("document.body.innerText || \"\"") 
        simplified_text = ' '.join(text_content.split()[:1000]) # Limit text length more generously for context
        logger.debug(f"[Capture Page] Extracted text (limited): {simplified_text[:100]}...")

        screenshot_bytes = await page.screenshot()
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
        
        debug_screenshot_path = "debug_captured_page.png" # Generic name
        try:
            with open(debug_screenshot_path, "wb") as f:
                f.write(screenshot_bytes)
            logger.info(f"[Capture Page] Debug screenshot saved to: {debug_screenshot_path}")
        except Exception as e_ss_save:
            logger.warning(f"[Capture Page] Could not save debug screenshot: {e_ss_save}")

        return {
            "current_url": url,
            "page_content": simplified_text, 
            "screenshot": screenshot_b64,
            "error_message": None
        }
    except Exception as e:
        logger.error(f"[Capture Page] Error capturing page state: {e}")
        current_url_on_error = "Error_fetching_url"
        try:
            if page and not page.is_closed():
                 current_url_on_error = page.url
        except: # Broad except as a last resort for URL
            pass
        return {"current_url": current_url_on_error, "page_content": None, "screenshot": None, "error_message": f"Error capturing page: {e}"}

# --- Tool Definitions (Keep the original tool functions for now) ---
# We will call these functions from within our graph nodes.

async def _browse_web_page_internal(url: str) -> dict:
    print(f"\n[Internal Tool] _browse_web_page_internal(url='{url}')")
    try:
        page = await get_page()
        if not page: 
            return {
                "text_content": "Error: Page instance could not be created.",
                "screenshot_base64": None,
                "error": "Page instance not available."
            }
        
        print(f"[Browser Tool - Browse] Navigating to {url}...")
        await page.goto(url, wait_until='networkidle', timeout=45000)
        print("[Browser Tool - Browse] Navigation successful. Getting content and screenshot...")
        
        # Get text content
        html_content = await page.content()
        soup = BeautifulSoup(html_content, 'html.parser')
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()
        text_content = soup.get_text()
        lines = (line.strip() for line in text_content.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        simplified_text = '\n'.join(chunk for chunk in chunks if chunk)
        
        # Get screenshot and resize
        screenshot_bytes = await page.screenshot(type='png') # Get screenshot as bytes
        
        # Resize image using Pillow to reduce size (and cost)
        # Max width 768px, height will scale proportionally. Quality 85.
        img = Image.open(BytesIO(screenshot_bytes))
        max_width = 768 
        if img.width > max_width:
            scale_ratio = max_width / img.width
            new_height = int(img.height * scale_ratio)
            img = img.resize((max_width, new_height), Image.LANCZOS) # Use LANCZOS for better quality resize
        
        # <<< ADDED: Save the image locally for debugging >>>
        try:
            debug_screenshot_path = "debug_screenshot.png" 
            img.save(debug_screenshot_path, format="PNG")
            print(f"[Browser Tool - Browse] Debug screenshot saved to: {debug_screenshot_path}")
        except Exception as save_e:
            print(f"[Browser Tool - Browse] Warning: Could not save debug screenshot: {save_e}")
        # <<< END ADDED SECTION >>>

        buffered = BytesIO()
        img.save(buffered, format="PNG", quality=85, optimize=True) # Save resized image to buffer
        screenshot_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        
        print(f"[Browser Tool - Browse] Returning text and screenshot (text_len: {len(simplified_text)}, screenshot_size_approx_b64: {len(screenshot_base64)}).")
        
        # Truncate text if too long for context, but keep screenshot
        max_text_length_for_llm = 3000 
        if len(simplified_text) > max_text_length_for_llm:
            simplified_text = simplified_text[:max_text_length_for_llm] + "... [Text content truncated for LLM context]"

        return {
            "text_content": simplified_text,
            "screenshot_base64": screenshot_base64,
            "url": page.url # Return current URL as well
        }
        
    except Exception as e:
        error_message = f"Error browsing {url}: {str(e)}\n{traceback.format_exc()}"
        print(f"[Browser Tool - Browse] {error_message}")
        current_url = "Unknown"
        if '_page_instance' in globals() and _page_instance and not _page_instance.is_closed():
             current_url = _page_instance.url
        return {
            "text_content": f"Error: Could not browse {url}. Details: {str(e)}",
            "screenshot_base64": None,
            "error": str(e),
            "url": current_url
        }

async def _click_element_by_description_internal(description: str) -> str:
    print(f"\n[Internal Tool] _click_element_by_description_internal(description='{description}')")
    try:
        page = await get_page()
        if not page or page.is_closed(): return "Error: No active page."
        
        print(f"[Browser Tool - Click by Desc] Attempting to click element described as: {description}")
        
        # Strategy 1: Try specific aria-labels (Most reliable)
        possible_selectors = [
            "div[aria-label='按图搜索']",
            "div[aria-label='Search by image']",
            "button[aria-label='按图搜索']",
            "button[aria-label='Search by image']",
            "span[aria-label='按图搜索']", # Try span as well
            "span[aria-label='Search by image']",
            "div[role='button'][aria-label*='搜索']", # More generic search label
            "div[role='button'][aria-label*='Search']",
            "textarea[aria-label='搜索图片'] + div >> internal:control=enter-frame >> div[role='button'][aria-label*='搜索']" # Example complex selector if icon is in sibling div or frame
        ]
        
        clicked = False
        for i, selector in enumerate(possible_selectors):
            try:
                print(f"[Browser Tool - Click by Desc] Trying CSS selector strategy #{i+1}: {selector}")
                element = page.locator(selector).first
                await element.wait_for(state='visible', timeout=3000) # Shorter timeout for trying many
                # await element.wait_for(state='enabled', timeout=3000)
                await element.click(timeout=3000)
                print(f"[Browser Tool - Click by Desc] Successfully clicked using selector: {selector}")
                clicked = True
                break 
            except Exception as e:
                # print(f"[Browser Tool - Click by Desc] CSS Selector strategy #{i+1} failed: {selector} - {type(e).__name__}")
                pass # Silently continue if selector fails

        # Strategy 2: Try Playwright's get_by_role if CSS failed
        if not clicked:
            possible_roles_and_names = [
                ("button", re.compile('按图搜索|Search by image', re.IGNORECASE)),
                ("link", re.compile('按图搜索|Search by image', re.IGNORECASE)), # Sometimes it might be a link
                ("button", re.compile('搜索|Search', re.IGNORECASE)) # Generic fallback
            ]
            for i, (role, name_regex) in enumerate(possible_roles_and_names):
                try:
                    print(f"[Browser Tool - Click by Desc] Trying get_by_role strategy #{i+1}: role={role}, name={name_regex.pattern}")
                    element = page.get_by_role(role, name=name_regex).first
                    await element.wait_for(state='visible', timeout=3000)
                    # await element.wait_for(state='enabled', timeout=3000)
                    await element.click(timeout=3000)
                    print(f"[Browser Tool - Click by Desc] Successfully clicked using get_by_role: role={role}, name={name_regex.pattern}")
                    clicked = True
                    break
                except Exception as e:
                    # print(f"[Browser Tool - Click by Desc] get_by_role strategy #{i+1} failed: {role}/{name_regex.pattern} - {type(e).__name__}")
                    pass # Silently continue

        if clicked:
            await page.wait_for_timeout(3000) # Wait after successful click
            # <<< ADDED: Wait longer and take screenshot after click >>>
            print("[Browser Tool - Click by Desc] Click successful. Waiting 10s and taking screenshot...")
            await page.wait_for_timeout(10000) 
            try:
                screenshot_path_after_click = "screenshot_after_click.png"
                await page.screenshot(path=screenshot_path_after_click)
                print(f"[Browser Tool - Click by Desc] Screenshot after click saved to: {screenshot_path_after_click}")
            except Exception as ss_e:
                print(f"[Browser Tool - Click by Desc] Could not save screenshot after click: {ss_e}")
            # <<< END ADDED SECTION >>>
            return f"Successfully clicked the element described as '{description}' using a likely locator."
        else:
            print("[Browser Tool - Click by Desc] All tested strategies failed.")
            raise Exception("Could not find or click the element based on the description using any known strategy.")

    except Exception as e:
        error_message = f"Error clicking element described as '{description}': {str(e)}\n{traceback.format_exc()}"
        print(f"[Browser Tool - Click by Desc] {error_message}")
        if '_page_instance' in globals() and _page_instance and not _page_instance.is_closed():
            try:
                await _page_instance.screenshot(path="error_screenshot_click_desc_failed.png")
                print("[Browser Tool - Click by Desc] Saved screenshot on error to error_screenshot_click_desc_failed.png")
            except Exception as ss_e:
                print(f"[Browser Tool - Click by Desc] Could not save screenshot on error: {ss_e}")
        return f"Error: Could not click element described as '{description}'. Details: {str(e)}"

async def _upload_file_internal(locator_or_text: str, file_path: str) -> dict:
    """
    Attempts to upload a file using a file input element found by various strategies.
    After setting the file input, it captures the current page state.
    """
    page = await get_page()
    if not page:
        logger.error("[Browser Tool - Upload Internal] Page not available.")
        return {
            "upload_status": "Upload failed: Page not available.",
            "current_url": None, "page_content": None, "screenshot": None,
            "error_message": "Upload failed: Page not available."
        }

    if not os.path.exists(file_path):
        logger.error(f"[Browser Tool - Upload Internal] File not found: {file_path}")
        return {
            "upload_status": f"Upload failed: File not found at {file_path}",
            "current_url": page.url, "page_content": await page.content(), "screenshot": None,
            "error_message": f"Upload failed: File not found at {file_path}"
        }

    error_message = "Upload failed: Could not find or interact with file input after multiple attempts."
    upload_successful = False
    file_input_el = None # Initialize file_input_el

    try:
        # Common selectors for file input elements
        file_input_selectors = [
            "input[type='file']",
            "//input[@type='file']", # XPath version
            "form input[type='file']",
            "div input[type='file']",
            "[data-testid='file-input']", # Common test ID
            "input[name='image']", # Common name
            "input[name='file']"
        ]

        logger.info(f"[Browser Tool - Upload Internal] Waiting for a file input element to become available...")

        for i, selector in enumerate(file_input_selectors):
            logger.debug(f"[Browser Tool - Upload Internal] Trying file input selector #{i+1}: {selector}")
            try:
                await page.wait_for_selector(selector, state="attached", timeout=2000)
                file_input_el = page.locator(selector).first
                # --- CRITICAL FIX: Ensure NO await here ---
                if file_input_el.is_attached():
                     logger.info(f"[Browser Tool - Upload Internal] Found file input element with selector: {selector}")
                     break
                else:
                     file_input_el = None # Reset if found but not attached
            except PlaywrightTimeoutError:
                logger.debug(f"[Browser Tool - Upload Internal] Selector {selector} not found or not attached quickly.")
                file_input_el = None # Reset on timeout
                continue
            except Exception as e:
                logger.warning(f"[Browser Tool - Upload Internal] Error checking selector {selector}: {e}")
                file_input_el = None # Reset on other errors
                continue

        # Check if file_input_el was successfully found and is attached
        # --- CRITICAL FIX: Ensure NO await here ---
        if not file_input_el or not file_input_el.is_attached():
            logger.error("[Browser Tool - Upload Internal] No file input element found or attached using common selectors.")
            error_message = "Upload failed: No suitable file input element found on the page."
        else:
            # Log the outerHTML *before* trying to interact, helps debugging
            try:
                 outer_html = await file_input_el.evaluate('element => element.outerHTML')
                 logger.info(f"[Browser Tool - Upload Internal] Using file input element: {outer_html}")
            except Exception as eval_e:
                 logger.warning(f"[Browser Tool - Upload Internal] Could not evaluate outerHTML for found input: {eval_e}")
                 logger.info(f"[Browser Tool - Upload Internal] Using file input element found with selector, but could not get HTML.")

            await file_input_el.set_input_files(file_path)
            logger.info(f"[Browser Tool - Upload Internal] set_input_files(\'{file_path}\') called successfully.")
            upload_successful = True
            error_message = None # Clear error message as upload was successful

    except PlaywrightTimeoutError as e: # Catch specific timeout errors if they bubble up
        logger.error(f"[Browser Tool - Upload Internal] Timeout error during upload attempt: {e}")
        error_message = f"Upload failed due to timeout: {e}"
    except Exception as e:
        logger.error(f"[Browser Tool - Upload Internal] General error during upload attempt: {e}\\n{traceback.format_exc()}") # Log traceback too
        error_message = f"Upload failed: {e}"

    # --- Return logic ---
    if upload_successful:
        await asyncio.sleep(2) # Give page a moment to react
        logger.info("[Browser Tool - Upload Internal] Capturing page state after file selection...")
        capture_data = await _capture_current_page() # Assumes _capture_current_page is defined globally
        # Check if capture itself failed
        if capture_data.get("error_message"):
             logger.warning(f"[Browser Tool - Upload Internal] File selection successful, but failed to capture page state afterwards: {capture_data['error_message']}")
             # Return success for upload, but with capture error details
             return {
                 "upload_status": "File selected, but page state capture failed.",
                 "current_url": capture_data.get("current_url"), # May be None or stale
                 "page_content": None,
                 "screenshot": None,
                 "error_message": capture_data["error_message"] # Propagate capture error
             }
        else:
             # Happy path: Upload and capture successful
             return {
                 "upload_status": "File selected. Page state captured for next step analysis.",
                 "current_url": capture_data.get("current_url"),
                 "page_content": capture_data.get("page_content"),
                 "screenshot": capture_data.get("screenshot"),
                 "error_message": None
             }
    else:
        # Upload failed, attempt to capture page state for debugging
        logger.info("[Browser Tool - Upload Internal] Upload failed. Capturing current page state for debugging...")
        current_page_state = await _capture_current_page()
        # Log the state capture result along with the original upload error
        logger.debug(f"[Browser Tool - Upload Internal] State capture after failed upload result: {filter_screenshot_from_state(current_page_state)}")
        return {
            "upload_status": "Upload failed.",
            "current_url": current_page_state.get("current_url", page.url if page and not page.is_closed() else None),
            "page_content": current_page_state.get("page_content"),
            "screenshot": current_page_state.get("screenshot"),
            "error_message": error_message # The original error from the upload attempt
        }

# --- LangGraph State Definition ---
class AgentState(TypedDict):
    task: str
    image_path: str
    current_url: str
    page_content: str
    screenshot: str
    error_message: str | None
    analysis_result: str

# --- LangGraph Nodes Definitions ---

async def start_browse_node(state: AgentState) -> AgentState:
    """Node to initiate the browsing process by navigating to Google Images."""
    print("--- Executing Node: start_browse ---")
    url_to_browse = "https://images.google.com/"
    browse_result = await _browse_web_page_internal(url_to_browse)
    
    if browse_result.get("error"):
        print(f"Error in start_browse: {browse_result['error']}")
        state["error_message"] = browse_result["error"]
    else:
        state["current_url"] = browse_result.get("url")
        state["page_content"] = browse_result.get("text_content")
        state["screenshot"] = browse_result.get("screenshot_base64")
        state["error_message"] = None # Clear previous errors

    return state

# --- Placeholder Nodes (to be implemented) ---
async def analyze_vision_node(state: AgentState) -> AgentState:
    """Node to call LLM to analyze screenshot and text to find the next action."""
    print("--- Executing Node: analyze_vision ---")
    
    screenshot_b64 = state.get("screenshot")
    text_content = state.get("page_content", "")
    task_prompt = state.get("task", "Find source URL for an image.") # Use original task for context

    if not screenshot_b64:
        print("Error: No screenshot available for analysis.")
        state["error_message"] = "No screenshot available for analysis."
        state["analysis_result"] = "Camera icon not visually found" # Treat as not found
        return state

    # Construct the prompt for the LLM
    # We need to guide it to perform step 3 of our conceptual plan
    vision_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert visual analysis assistant. Your task is to analyze the provided screenshot and text from a webpage (Google Images). "
                   "Your goal is to locate the 'Search by image' camera icon."),
        ("human", [
            {"type": "text", "text": f"Here is the relevant text from the page:\n```\n{text_content[:1000]}...```\n\n" # Limit text length
                                      "Now, look carefully at this screenshot of the page:"},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}
            },
            {"type": "text", "text": "\n\nBased ONLY on the screenshot, look INSIDE the main search bar, specifically on the RIGHT side. "
                                      "You should see a microphone icon and a camera icon. Identify the CAMERA icon. "
                                      "If you see the camera icon, respond ONLY with a concise visual description (e.g., 'Camera icon inside search bar on the right'). "
                                      "If you CANNOT visually find the camera icon inside the search bar, respond ONLY with 'Camera icon not visually found'."}
        ])
    ])
    
    # Chain the prompt and LLM
    chain = vision_prompt | llm
    
    try:
        print("Invoking LLM for visual analysis...")
        response = await chain.ainvoke({})
        analysis = response.content.strip()
        print(f"LLM Analysis Result: {analysis}")
        
        # Validate analysis result format slightly
        if analysis.startswith("Camera icon") or analysis == "Camera icon not visually found":
            state["analysis_result"] = analysis
            state["error_message"] = None
        else:
            # If LLM gives unexpected output, treat as error/not found for now
            print(f"Warning: LLM analysis result unexpected format: {analysis}")
            state["analysis_result"] = "Camera icon not visually found" 
            state["error_message"] = "LLM analysis format unexpected."
            
    except Exception as e:
        print(f"Error during LLM visual analysis: {e}")
        print(traceback.format_exc())
        state["error_message"] = f"LLM analysis failed: {e}"
        state["analysis_result"] = "Camera icon not visually found" # Default on error

    return state

async def click_node(state: AgentState) -> dict:
    """Node to perform the click action based on analysis result."""
    print("--- Executing Node: click (Placeholder) ---")
    description_or_selector = state.get("analysis_result")
    if description_or_selector and description_or_selector != "Camera icon not visually found":
        click_result = await _click_element_by_description_internal(description_or_selector)
        if "Error" in click_result:
            # <<< Return only the update dictionary >>>
            return {"error_message": click_result} 
        else:
             # <<< Return only the update dictionary >>>
             return {"error_message": None} 
    else:
        error_msg = "No valid target description/selector provided for clicking."
        if not description_or_selector:
             error_msg = "Analysis result missing for click node."
        # <<< Return only the update dictionary >>>
        return {"error_message": error_msg} 
    # The implicit return state is removed, we now explicitly return update dicts

async def upload_browse_node(state: AgentState) -> AgentState:
    """Node to capture the page state after clicking, expecting the upload dialog.
    This node DOES NOT navigate, it captures the current page."""
    print("--- Executing Node: upload_browse ---")
    try:
        page = await get_page()
        if not page or page.is_closed():
            state["error_message"] = "Error: Page instance not available for upload_browse."
            state["page_content"] = None
            state["screenshot"] = None
            return state

        print("[Upload Browse Node] Page active. Getting current content and screenshot...")
        
        # Get text content (similar to _browse_web_page_internal but without goto)
        html_content = await page.content()
        soup = BeautifulSoup(html_content, 'html.parser')
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()
        text_content = soup.get_text()
        lines = (line.strip() for line in text_content.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        simplified_text = '\n'.join(chunk for chunk in chunks if chunk)
        
        # Get screenshot and resize (similar to _browse_web_page_internal)
        screenshot_bytes = await page.screenshot(type='png')
        img = Image.open(BytesIO(screenshot_bytes))
        max_width = 768
        if img.width > max_width:
            scale_ratio = max_width / img.width
            new_height = int(img.height * scale_ratio)
            img = img.resize((max_width, new_height), Image.LANCZOS)
        
        # Save a debug screenshot specifically for this node
        try:
            debug_upload_dialog_path = "debug_upload_dialog_screenshot.png"
            img.save(debug_upload_dialog_path, format="PNG")
            print(f"[Upload Browse Node] Debug screenshot for upload dialog saved to: {debug_upload_dialog_path}")
        except Exception as save_e:
            print(f"[Upload Browse Node] Warning: Could not save debug screenshot for upload dialog: {save_e}")

        buffered = BytesIO()
        img.save(buffered, format="PNG", quality=85, optimize=True)
        screenshot_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        
        print(f"[Upload Browse Node] Captured text and screenshot (text_len: {len(simplified_text)}, screenshot_size_approx_b64: {len(screenshot_base64)}).")

        max_text_length_for_llm = 3000
        if len(simplified_text) > max_text_length_for_llm:
            simplified_text = simplified_text[:max_text_length_for_llm] + "... [Text content truncated for LLM context]"

        state["current_url"] = page.url # Update current URL just in case, though it shouldn't change
        state["page_content"] = simplified_text
        state["screenshot"] = screenshot_base64
        state["error_message"] = None

    except Exception as e:
        error_message = f"Error in upload_browse_node: {str(e)}\n{traceback.format_exc()}"
        print(f"[Upload Browse Node] {error_message}")
        state["error_message"] = str(e)
        # Optionally try to get URL even on error
        current_url_on_error = "Unknown"
        if '_page_instance' in globals() and _page_instance and not _page_instance.is_closed():
             current_url_on_error = _page_instance.url
        state["current_url"] = current_url_on_error
        state["page_content"] = None
        state["screenshot"] = None # Ensure screenshot is None on error
        
    return state

async def analyze_upload_dialog_node(state: AgentState) -> AgentState:
    """Node to analyze the screenshot of the upload dialog and find the upload element selector."""
    print("--- Executing Node: analyze_upload_dialog ---")
    page = await get_page()
    if not page or page.is_closed():
        state["error_message"] = "Error: Page instance not available for upload dialog analysis."
        state["analysis_result"] = "Error: Missing input for analysis."
        return state

    text_content = state.get("page_content")
    screenshot_b64 = state.get("screenshot")
    current_url = state.get("current_url") # For context

    if not text_content or not screenshot_b64:
        state["error_message"] = "Error: Missing page content or screenshot for upload dialog analysis."
        state["analysis_result"] = "Error: Missing input for analysis."
        return state

    # <<< MODIFIED SYSTEM AND HUMAN PROMPT BELOW >>>
    vision_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert visual analysis assistant focused on web automation. "
                   "The user has already clicked a 'search by image' (camera) icon, and the screenshot you are seeing shows the MODAL DIALOG that appeared for uploading an image. "
                   "Your ONLY task is to analyze the elements WITHIN THIS MODAL DIALOG. IGNORE any background elements like search bars or other icons that are NOT part of this dialog. "
                   "Inside this dialog, find the clickable element (e.g., a link, a button, or an area that looks like an <input type=\"file\">) that allows the user to SELECT A FILE from their computer to upload. "
                   "Do NOT look for a search button or an image paste area. Focus on the file SELECTION/UPLOAD element."),
        ("human", [
            {"type": "text", "text": f"""Here is the relevant text from the page dialog (URL: {current_url}):
```
{text_content[:1000]}...```

Screenshot of the UPLOAD DIALOG (focus ONLY on this dialog):
It should contain options like 'upload a file', 'select file', '粘贴图片网址', '或上传文件'."""},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}
            },
            {"type": "text", "text": "\n\nBased on the screenshot and text of the MODAL DIALOG, what is the most appropriate and robust CSS selector for the file UPLOAD link/button (e.g., `a.upload-link`, `button[aria-label='Upload file']`, `input[type='file']`)? "
                                      "If you can identify it clearly, provide ONLY the CSS selector string. "
                                      "If you are less certain about a CSS selector but can identify the exact text of the element (e.g., '上传文件' or 'upload a file'), provide ONLY that exact text string. "
                                      "If you cannot find a suitable element for file upload within the dialog, respond with 'File upload element not found in dialog'."}
        ])
    ])
    # <<< END MODIFIED PROMPT >>>

    print("[Analyze Upload Dialog Node] Sending request to LLM for vision analysis of the upload dialog...")
    llm = ChatOpenAI(model="gpt-4o", temperature=0, max_tokens=250) # Correctly initialize LLM
    chain = vision_prompt | llm | StrOutputParser()
    
    try:
        analysis_result = await chain.ainvoke({})
        state["analysis_result"] = analysis_result
        state["error_message"] = None # Clear previous errors
        print(f"[Analyze Upload Dialog Node] LLM Analysis Result:\n{analysis_result}")
    except Exception as e:
        print(f"[Analyze Upload Dialog Node] Error during LLM invocation: {e}")
        state["error_message"] = f"LLM analysis of upload dialog failed: {e}"
        state["analysis_result"] = "Error: LLM analysis of upload dialog failed."
        
    return state

async def perform_upload_node(state: AgentState) -> AgentState:
    logger.info("--- Executing Node: perform_upload ---")
    image_path = state.get("image_path")
    # analysis_result here is the locator/text for the "upload file" button/link itself
    upload_trigger_element_description = state.get("analysis_result", "").strip().strip("'\"")

    if not image_path:
        logger.error("[Perform Upload Node] Image path not found in state.")
        state["error_message"] = "Cannot perform upload: Image path missing."
        return state
    
    if not upload_trigger_element_description:
        logger.error("[Perform Upload Node] Upload trigger element description not found in state.")
        state["error_message"] = "Cannot perform upload: Upload trigger element description missing."
        return state

    logger.info(f"[Perform Upload Node] Cleaned analysis result for upload element: '{upload_trigger_element_description}'")
    
    upload_result_dict = await _upload_file_internal(
        locator_or_text=upload_trigger_element_description, # This is what LLM found for the upload dialog trigger
        file_path=image_path
    )

    state["current_url"] = upload_result_dict.get("current_url", state.get("current_url"))
    state["page_content"] = upload_result_dict.get("page_content", state.get("page_content"))
    state["screenshot"] = upload_result_dict.get("screenshot", state.get("screenshot"))
    state["error_message"] = upload_result_dict.get("error_message")
    
    # Clear previous analysis_result (which was for upload trigger)
    # The next node (analyze_post_upload_page_node) will populate it with submit button analysis.
    state["analysis_result"] = "" 

    if upload_result_dict.get("error_message"):
        logger.error(f"[Perform Upload Node] Upload failed: {upload_result_dict.get('error_message')}")
    else:
        logger.info(f"[Perform Upload Node] Upload status: {upload_result_dict.get('upload_status')}")
        logger.info(f"[Perform Upload Node] Page state captured for submit button analysis. URL: {state['current_url']}")
    
    logger.debug(f"[DEBUG perform_upload_node END] Final state before return: {filter_screenshot_from_state(state.copy())}")
    return state

async def browse_results_node(state: AgentState) -> AgentState:
    """Node to capture the content of the results page *without* navigating."""
    logger.info("--- Executing Node: browse_results ---")
    current_url = state.get("current_url")
    if not current_url:
        state["error_message"] = "Error: current_url not found in state before browsing results."
        return state
    
    logger.info(f"[Browse Results Node] Capturing content from current URL: {current_url}")
    
    # Now calls the global _capture_current_page
    capture_result = await _capture_current_page()

    if capture_result.get("error_message"):
        state["error_message"] = f"Error browsing results: {capture_result['error_message']}"
    elif capture_result.get("error"):
        state["error_message"] = f"Error browsing results: {capture_result['error']}"
    else:
        state["page_content"] = capture_result.get("page_content")
        state["screenshot"] = capture_result.get("screenshot")
        state["current_url"] = capture_result.get("current_url") # Update URL just in case
        state["error_message"] = None # Clear previous errors if browse is successful
        logger.info("[Browse Results Node] Successfully captured results page content and screenshot.")
        
    return state

async def analyze_results_node(state: AgentState) -> AgentState:
    """Node to analyze the results page screenshot and text to extract source URLs."""
    print("--- Executing Node: analyze_results ---")
    # <<< ADDED DEBUG PRINT >>>
    print("[DEBUG] Entering analyze_results_node")
    page_content = state.get("page_content")
    screenshot_b64 = state.get("screenshot")
    current_url = state.get("current_url") # For context

    if not page_content or not screenshot_b64:
        state["error_message"] = "Error: Missing page content or screenshot for results analysis."
        state["analysis_result"] = "Error: Missing input for results analysis."
        return state

    analysis_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert visual analysis assistant. Your task is to analyze the provided screenshot and text from a Google Lens search results page. "
                   "Focus on the section titled '包含匹配图片的页面' (Pages that include matching images). "
                   "Extract all the source URLs listed under that section. "
                   "Format your response clearly, starting with 'Visually similar images found.', then mentioning the section title found, and finally listing the extracted URLs under 'Found URLs:'."),
        ("human", [
            {"type": "text", "text": f"""Relevant text from the results page (URL: {current_url}):
```
{page_content[:1000]}...```

Screenshot of the results page:"""},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}},
            {"type": "text", "text": "\n\nPlease analyze the screenshot and text, specifically find the section '包含匹配图片的页面' and list all the source URLs shown under it."}
        ])
    ])
    
    print("[Analyze Results Node] Invoking LLM for results analysis...")
    llm = ChatOpenAI(model="gpt-4o", temperature=0, max_tokens=1000)
    chain = analysis_prompt | llm | StrOutputParser()
    
    try:
        analysis_result = await chain.ainvoke({})
        state["analysis_result"] = analysis_result
        state["error_message"] = None
        print(f"[Analyze Results Node] LLM Analysis Result:\n{analysis_result}")
    except Exception as e:
        print(f"[Analyze Results Node] Error during LLM invocation: {e}")
        state["error_message"] = f"LLM analysis failed: {e}"
        state["analysis_result"] = "Error: LLM analysis failed."
        
    return state

# --- LangGraph Conditional Edges --- 

def should_click_or_end(state: AgentState) -> str:
    """Determines the next step after visual analysis."""
    print("--- Evaluating Edge: should_click_or_end ---")
    analysis_result = state.get("analysis_result")
    error = state.get("error_message")
    if error:
        print(f"Decision: Error detected -> End ({error})")
        return "end_error"
    if analysis_result == "Camera icon not visually found":
        print("Decision: Icon not found -> End")
        return "end_not_found"
    elif analysis_result: # Assumes any other non-empty result is a description/selector to click
        print("Decision: Description/Selector for camera icon found -> Click")
        return "click"
    else:
        print("Decision: Camera analysis failed -> End Error")
        state["error_message"] = "Camera analysis result was empty or missing."
        return "end_error"

def should_browse_for_upload_or_end(state: AgentState) -> str:
    """Determines the next step after attempting a click (to open upload dialog)."""
    print("--- Evaluating Edge: should_browse_for_upload_or_end ---")
    error = state.get("error_message")
    if error:
        print(f"Decision: Click (to open dialog) failed -> End ({error})")
        return "end_error"
    else:
        print("Decision: Click (to open dialog) successful -> Capture Upload Dialog Page")
        return "capture_upload_dialog_page" # New transition name

def should_perform_upload_or_end(state: AgentState) -> str:
    """Conditional edge deciding whether to upload or end."""
    print("--- Evaluating Edge: should_perform_upload_or_end ---")
    analysis_result = state.get("analysis_result")
    error_message = state.get("error_message") # Check for errors from previous node too

    if error_message and "Error:" in error_message:
         print(f"Decision: Error found ('{error_message}'). Ending graph.")
         return "__end__"
         
    if not analysis_result or "not found" in analysis_result.lower() or "error" in analysis_result.lower():
        print(f"Decision: No valid analysis result ('{analysis_result}'). Ending graph.")
        return "__end__"

    # <<< MODIFIED: Heuristic to accept short text as potential locators >>>
    cleaned_result = analysis_result.strip()
    if cleaned_result.startswith("`") and cleaned_result.endswith("`"):
        cleaned_result = cleaned_result[1:-1].strip()
        
    # Consider it a likely locator if it's not clearly a long description
    # Heuristic: Fewer than 4 words AND does not contain 'icon' (which was our previous failure mode)
    word_count = len(cleaned_result.split())
    is_likely_locator = bool(cleaned_result) and word_count < 4 and "icon" not in cleaned_result.lower()

    if is_likely_locator:
        print(f"Decision: Analysis result ('{analysis_result}') looks like a locator/text (heuristic: <4 words, no 'icon'). Proceeding to upload.")
        return "perform_upload"
    else:
        # If it doesn't look like a selector/short text, assume it's a description or error
        print(f"Decision: Analysis result ('{analysis_result}') does not look like a locator/text (heuristic failed). Ending graph.")
        # We could potentially add a node here to ASK the user for the selector if we get a description
        return "__end__" # End for now if it's descriptive

def should_browse_results_or_end(state: AgentState) -> str:
    """Determines whether to browse results page or end after upload attempt."""
    print("--- Evaluating Edge: should_browse_results_or_end ---")
    # <<< ADDED DEBUG PRINT >>>
    print(f"[DEBUG Edge should_browse_results_or_end START] Incoming state: {state}")
    print(f"[DEBUG Edge] Current error_message in state: {state.get('error_message')!r}")
    print(f"[DEBUG Edge] Current upload_result in state: {state.get('upload_result')!r}")
    # <<< END ADDED DEBUG PRINTS >>>
    upload_result = state.get("upload_result") # Check upload_result now
    error = state.get("error_message")

    # Prioritize explicit errors from the state
    if error and "Error:" in error:
        print(f"Decision: Error state detected -> End ({error})")
        return "end_error"
        
    # Check if upload_result indicates success
    if upload_result and "successfully" in upload_result.lower():
        print(f"Decision: Upload successful ('{upload_result}') -> Browse Results")
        return "browse_results" # Go to the new node
    else:
        print(f"Decision: Upload failed or status unclear ('{upload_result}') -> End Error")
        # Ensure error message reflects this if not already set
        if not error:
             state["error_message"] = f"Upload failed or status unclear: {upload_result}"
        return "end_error"

def should_return_results_or_end(state: AgentState) -> str:
    """Determines whether to end successfully with results or end with an error after analysis."""
    print("--- Evaluating Edge: should_return_results_or_end ---")
    analysis_result = state.get("analysis_result")
    error = state.get("error_message")

    if error and "Error:" in error: # Check for errors during analysis first
        print(f"Decision: Error during results analysis -> End ({error})")
        return "end_error"
        
    if analysis_result and "Found URLs:" in analysis_result:
        print(f"Decision: Found URLs in analysis result -> End Success")
        return "end_success"
    else:
        print(f"Decision: Analysis result does not contain URLs or is missing ('{analysis_result}') -> End Error")
        state["error_message"] = f"Failed to extract URLs from results page. Analysis: {analysis_result}"
        return "end_error"

# --- Build the Graph --- 

workflow = StateGraph(AgentState)

# Define the nodes
workflow.add_node("start_browse", start_browse_node)
workflow.add_node("analyze_vision", analyze_vision_node) 
workflow.add_node("click", click_node) 
workflow.add_node("capture_upload_dialog_page", upload_browse_node)
workflow.add_node("analyze_upload_dialog", analyze_upload_dialog_node)
workflow.add_node("perform_upload", perform_upload_node)
workflow.add_node("browse_results", browse_results_node)
workflow.add_node("analyze_results", analyze_results_node)

# Define the edges
workflow.set_entry_point("start_browse")
workflow.add_edge("start_browse", "analyze_vision")

# Conditional edge after camera icon analysis
workflow.add_conditional_edges(
    "analyze_vision",
    should_click_or_end,
    {
        "click": "click",
        "end_not_found": END, 
        "end_error": END     
    }
)

# Conditional edge after click attempt (to open dialog)
workflow.add_conditional_edges(
    "click",
    should_browse_for_upload_or_end,
    {
        "capture_upload_dialog_page": "capture_upload_dialog_page", 
        "end_error": END 
    }
)

# Edge from capturing upload dialog page to analyzing it
workflow.add_edge("capture_upload_dialog_page", "analyze_upload_dialog")

# Conditional edge after analyzing upload dialog
workflow.add_conditional_edges(
    "analyze_upload_dialog",
    should_perform_upload_or_end,
    {
        "perform_upload": "perform_upload",
        "end_not_found": END,
        "end_error": END
    }
)

# Conditional edge after perform_upload node
workflow.add_conditional_edges(
    "perform_upload",
    should_browse_results_or_end, # Use corrected function
    {
        "browse_results": "browse_results", # Go to browse_results on success
        "end_error": END
    }
)

# <<< ADDED Edge from browsing results to analyzing results >>>
workflow.add_edge("browse_results", "analyze_results")

# <<< ADDED Conditional edge after analyzing results >>>
workflow.add_conditional_edges(
    "analyze_results",
    should_return_results_or_end,
    {
        "end_success": END, # End successfully if URLs are found
        "end_error": END  # End with error if URLs are not found
    }
)

# Compile the graph
app = workflow.compile()

# --- Main Execution (Using LangGraph) ---
async def run_graph(task: str, image_path: str):
    """Invokes the LangGraph agent."""
    print("\n--- Starting LangGraph Agent ---")
    config = {"configurable": {"thread_id": "user-session-1"}}
    initial_state = AgentState(task=task, image_path=image_path)
    
    final_state = None # Initialize final_state
    try:
        # Stream events to see the flow
        async for event in app.astream_events(initial_state, config=config, version="v1"):
            kind = event["event"]
            node_name = event['name'] # Get name regardless of event type
            
            if kind == "on_chain_start":
                print(f"\nStarting step: {node_name}")
            elif kind == "on_chain_end":
                # <<< MODIFIED: Check and replace screenshot in output before printing >>>
                output_data = event['data'].get('output')
                log_output = "Unknown/NotDict" # Default log value
                if isinstance(output_data, dict):
                    # Create a copy to modify for logging
                    log_output = output_data.copy()
                    if "screenshot" in log_output and isinstance(log_output.get("screenshot"), str) and len(log_output.get("screenshot", "")) > 200:
                        log_output["screenshot"] = "[... base64 screenshot omitted by logger ...]"
                    # Also check for the other key used in browse internal tool
                    if "screenshot_base64" in log_output and isinstance(log_output.get("screenshot_base64"), str) and len(log_output.get("screenshot_base64", "")) > 200:
                         log_output["screenshot_base64"] = "[... base64 screenshot_base64 omitted by logger ...]"
                elif output_data is not None:
                     log_output = str(output_data) # Handle non-dict outputs
                
                print(f"Finished step: {node_name} [Output: {log_output}]") 
                # <<< END MODIFIED SECTION >>>
            elif kind == "on_tool_start":
                 # Ensure input is truncated if potentially large
                 tool_input = str(event['data'].get('input'))
                 print(f"  Tool Start: {node_name} [Input: {tool_input[:100]}{'...' if len(tool_input) > 100 else ''}]") 
            elif kind == "on_tool_end":
                 # <<< STRICT OMISSION: Always summarize or truncate tool output >>>
                 tool_output = event['data'].get('output')
                 output_summary = ""
                 if isinstance(tool_output, dict):
                      # Check both potential keys for screenshot data
                      text_content_len = len(tool_output.get('text_content', ''))
                      ss_omitted = False
                      if tool_output.get('screenshot') and isinstance(tool_output.get('screenshot'), str) and len(tool_output.get('screenshot', '')) > 200:
                           output_summary = f"text_len={text_content_len}, screenshot: [omitted in tool_end summary]"
                           ss_omitted = True
                      elif tool_output.get('screenshot_base64') and isinstance(tool_output.get('screenshot_base64'), str) and len(tool_output.get('screenshot_base64', '')) > 200:
                           output_summary = f"text_len={text_content_len}, screenshot_base64: [omitted in tool_end summary]"
                           ss_omitted = True
                      # Handle cases where screenshot might already be omitted string or None/empty
                      if not ss_omitted:
                          ss_val = tool_output.get('screenshot', tool_output.get('screenshot_base64'))
                          if isinstance(ss_val, str) and ss_val.startswith("[... base64"):
                               output_summary = f"text_len={text_content_len}, screenshot: [already omitted]"
                          else:
                               output_summary = f"text_len={text_content_len}, screenshot: No/Empty"
                 elif tool_output is not None:
                      # Generic truncation for other outputs
                      output_str = str(tool_output)
                      output_summary = f"{output_str[:80]}{'...' if len(output_str) > 80 else ''}"
                 else:
                      output_summary = "None"
                 print(f"  Tool End: {node_name} [Output Summary: {output_summary}]")
                 
            # Keep track of the latest state snapshot if needed for final output
            # (Alternative: call get_state after the loop)
            if event["event"] == "on_chain_end": 
                 current_output = event['data'].get('output')
                 if isinstance(current_output, dict): # Nodes usually return the state
                     final_state = current_output # Store the latest state output

        # <<< ADDED: Print final result after the loop >>>
        print("\n--- Graph Execution Complete --- ")
        # Try getting the final state explicitly
        try:
            final_state_explicit = await app.aget_state(config)
            # The state object might have a 'values' attribute or be the dict directly
            final_state_values = getattr(final_state_explicit, 'values', final_state_explicit)
            if isinstance(final_state_values, dict):
                final_result = final_state_values.get('analysis_result')
                error_msg = final_state_values.get('error_message')
                print("\n>>> Final Analysis Result:")
                print(final_result if final_result else "No analysis result found in final state.")
                if error_msg:
                    print(f"Final Error Message: {error_msg}")
            else:
                 print("Could not extract final state values as dictionary.")
        except Exception as e_get_state:
            print(f"Error getting final state explicitly: {e_get_state}")
            # Fallback to the last state captured during streaming if explicit get fails
            if final_state and isinstance(final_state, dict):
                 print("\n>>> Final Analysis Result (from last streamed state):")
                 final_result_streamed = final_state.get('analysis_result')
                 error_msg_streamed = final_state.get('error_message')
                 print(final_result_streamed if final_result_streamed else "No analysis result found in last streamed state.")
                 if error_msg_streamed:
                    print(f"Final Error Message (from last streamed state): {error_msg_streamed}")
            else:
                 print("Could not retrieve final analysis result.")
        # <<< END ADDED SECTION >>>

    except Exception as e:
        print(f"\n--- Graph Invocation Error ---")
        print(f"{type(e).__name__}: {e}")
        print(traceback.format_exc())
    finally:
        await close_page_and_browser()
        print("\n--- Graph Finished (Browser Closed) ---")

if __name__ == "__main__":
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        print("Warning: OPENAI_API_KEY not found in environment variables. Make sure .env file is set up correctly.")
        exit()
    else:
        print("OPENAI_API_KEY found.")

    # Define the task and the image path for the agent
    # *** IMPORTANT: Replace with the ACTUAL path to your test image ***
    # Assumes the script is run from 'findsourceurl-agent' directory
    # and 'data' directory is at the same level as 'findsourceurl-agent'
    relative_image_path = "../data/github.png" 
    test_image_path = os.path.abspath(relative_image_path) 
    
    print(f"Attempting to use image path: {test_image_path}")
    
    if not os.path.exists(test_image_path):
        print(f"Error: Test image not found at resolved path: {test_image_path}")
        print(f"(Looked for relative path: {relative_image_path})")
        print("Please update the 'relative_image_path' variable in agent_main.py or ensure the file exists.")
        exit()
        
    agent_task = f"Find the source URLs for the image located at {test_image_path}"

    # Run the graph execution
    asyncio.run(run_graph(task=agent_task, image_path=test_image_path))

# --- Keep old test function for reference if needed ---
async def test_playwright():
    """ (Previous test function - not called) """
    print("Starting Playwright test...")
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=False, slow_mo=500)
            print("Browser launched.")
            page = await browser.new_page()
            print("New page created.")
            target_url = "https://images.google.com/"
            print(f"Navigating to {target_url}...")
            await page.goto(target_url, wait_until='networkidle', timeout=30000)
            print("Navigation successful.")
            screenshot_path = "google_images_screenshot.png"
            await page.screenshot(path=screenshot_path)
            print(f"Screenshot saved to {screenshot_path}")
            await browser.close()
            print("Browser closed.")
            print("\nPlaywright test completed successfully!")
        except Exception as e:
            print(f"\nAn error occurred during the Playwright test: {e}")
            if 'browser' in locals() and browser.is_connected():
                await browser.close()
                print("Browser closed after error.")