import asyncio
from playwright.async_api import async_playwright, Playwright, Page, Browser
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

# --- LangChain & LangGraph Imports ---
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain.globals import set_debug
from langgraph.graph import StateGraph, END # Import StateGraph and END
# from langgraph.checkpoint.sqlite import SqliteSaver # <<< COMMENTED OUT this unused import

from bs4 import BeautifulSoup

# Load environment variables from .env file
load_dotenv()

# --- Enable LangChain Debug Mode ---
set_debug(True)
print("[LangChain] Debug mode enabled.")

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

async def _upload_file_internal(selector: str, file_path: str) -> str:
    print(f"\n[Internal Tool] _upload_file_internal(selector='{selector}', file_path='{file_path}')")
    
    if not os.path.isabs(file_path):
        script_dir = os.path.dirname(__file__)
        absolute_file_path = os.path.join(script_dir, file_path)
    else:
        absolute_file_path = file_path
        
    if not os.path.exists(absolute_file_path):
         print(f"[Browser Tool - Upload] File not found at resolved path: {absolute_file_path}")
         return f"Error: File not found at the specified path: {absolute_file_path}"

    try:
        page = await get_page()
        if not page or page.is_closed():
            return "Error: No active page available to upload file to. Use browse_web_page first."

        print(f"[Browser Tool - Upload] Attempting to upload file '{absolute_file_path}' to selector: {selector}")
        element = page.locator(selector)
        await element.wait_for(state='visible', timeout=15000) 
        await element.set_input_files(absolute_file_path, timeout=20000)
        print(f"[Browser Tool - Upload] Successfully set input files for selector: {selector}")
        await page.wait_for_timeout(3000)
        return f"Successfully initiated upload of file '{os.path.basename(absolute_file_path)}' to element '{selector}'. The page may have changed."
    except Exception as e:
        error_message = f"Error uploading file to {selector}: {str(e)}\n{traceback.format_exc()}"
        print(f"[Browser Tool - Upload] {error_message}")
        if '_page_instance' in globals() and _page_instance and not _page_instance.is_closed():
            try:
                await _page_instance.screenshot(path="error_screenshot_upload_failed.png")
                print("[Browser Tool - Upload] Saved screenshot on error to error_screenshot_upload_failed.png")
            except Exception as ss_e:
                print(f"[Browser Tool - Upload] Could not save screenshot on error: {ss_e}")
        return f"Error: Could not upload file '{os.path.basename(absolute_file_path)}' to selector '{selector}'. Details: {str(e)}"

# --- LangGraph State Definition ---
class AgentState(TypedDict):
    task: str                 # The initial task description
    image_path: str           # Path to the user's image
    current_url: Optional[str] # The current URL the browser is on
    page_content: Optional[str] # Simplified text content of the current page
    screenshot: Optional[str] # Base64 encoded screenshot of the current page
    analysis_result: Optional[str] # Result from LLM analysis (e.g., description, selector, final urls)
    error_message: Optional[str] # Any error encountered
    # We might add fields like 'found_urls' later

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
        state["screenshot"] = None
        
    return state

async def analyze_upload_dialog_node(state: AgentState) -> AgentState:
    """Node to call LLM to analyze screenshot and text to find the upload file button/link selector."""
    print("--- Executing Node: analyze_upload_dialog ---")
    
    screenshot_b64 = state.get("screenshot")
    text_content = state.get("page_content", "")

    if not screenshot_b64:
        print("Error: No screenshot available for upload dialog analysis.")
        state["error_message"] = "No screenshot available for upload dialog analysis."
        state["analysis_result"] = "Upload element selector not found"
        return state

    # Prompt for LLM to find the upload file element
    # The user shared a screenshot showing "上传文件" (shàngchuán wénjiàn - upload file) as a link.
    # We need to guide the LLM to find a clickable element for file upload.
    vision_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert visual analysis assistant. Your task is to analyze the provided screenshot and text from a webpage that shows a dialog for uploading an image for a reverse image search. "
                   "Your goal is to locate the clickable element (like a button or a link) that allows the user to select a file to upload from their computer."),
        ("human", [
            {"type": "text", "text": f"""Here is the relevant text from the page dialog (it might be in Chinese or English):
```
{text_content[:1000]}...```

"""
                                      "Now, look carefully at this screenshot of the dialog:"},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}
            },
            {"type": "text", "text": "\n\nBased on the screenshot and text, identify the clickable element (e.g., a link or button) that a user would click to UPLOAD A FILE from their computer. "
                                      "The text for this element might be '上传文件', 'upload file', 'select file', 'browse', or similar. It might be an `<input type=\'file\'>` element, or a `<span>` or `<a>` tag styled as a button. "
                                      "Respond with a plausible CSS selector for this element (e.g., `input[type=\'file']`, `span.upload-button`, `a[href=\'#upload']`). "
                                      "If you can confidently determine a selector, provide ONLY the selector. "
                                      "If you cannot determine a specific CSS selector but can describe it visually (e.g., 'The blue button labeled Upload'), provide that description. "
                                      "If you cannot find any such element, respond ONLY with 'Upload element selector not found'."}
        ])
    ])
    
    chain = vision_prompt | llm
    
    try:
        print("Invoking LLM for upload dialog analysis...")
        response = await chain.ainvoke({})
        analysis = response.content.strip()
        print(f"LLM Upload Dialog Analysis Result: {analysis}")
        
        state["analysis_result"] = analysis # This could be a selector, a description, or "not found"
        state["error_message"] = None
            
    except Exception as e:
        print(f"Error during LLM upload dialog analysis: {e}")
        print(traceback.format_exc())
        state["error_message"] = f"LLM upload dialog analysis failed: {e}"
        state["analysis_result"] = "Upload element selector not found"

    return state

async def perform_upload_node(state: AgentState) -> AgentState:
    """Node to perform the file upload using a selector or description."""
    print("--- Executing Node: perform_upload ---")
    
    target_selector_or_description = state.get("analysis_result")
    image_to_upload = state.get("image_path")

    if not target_selector_or_description or target_selector_or_description == "Upload element selector not found":
        error_msg = "No selector or description provided for file upload."
        print(error_msg)
        state["error_message"] = error_msg
        return state

    if not image_to_upload or not os.path.exists(image_to_upload):
        error_msg = f"Image path invalid or file not found: {image_to_upload}"
        print(error_msg)
        state["error_message"] = error_msg
        return state

    # We should refine the prompt for `analyze_upload_dialog_node` to strongly prefer selectors.
    
    # <<< MODIFIED: Handle potential backticks from LLM and refine selector check >>>
    cleaned_analysis_result = target_selector_or_description.strip()
    if cleaned_analysis_result.startswith("`") and cleaned_analysis_result.endswith("`"):
        cleaned_analysis_result = cleaned_analysis_result[1:-1]

    # More robust check for what might be a CSS selector vs. a natural language description.
    # Simple selectors usually don't have many spaces unless they are part of an attribute value string.
    # Descriptions usually have multiple words separated by spaces.
    # This is still a heuristic.
    is_likely_selector = False
    if cleaned_analysis_result and (" " not in cleaned_analysis_result or "[" in cleaned_analysis_result): # Basic check: no space OR space is within attribute selector
        # Further check: does it look like a common selector pattern?
        if re.match(r"^[\.#]?[a-zA-Z0-9_\-]+.*$", cleaned_analysis_result) or \
           re.match(r"^[a-zA-Z0-9_\-]+\[.*\]+.*$", cleaned_analysis_result) or \
           re.match(r"^input|^a|^button|^span|^div|^li", cleaned_analysis_result, re.IGNORECASE): # Starts with common tags
            is_likely_selector = True
    
    print(f"[Perform Upload Node] Cleaned analysis result: '{cleaned_analysis_result}', Is likely selector: {is_likely_selector}")

    if is_likely_selector:
        upload_result = await _upload_file_internal(selector=cleaned_analysis_result, file_path=image_to_upload)
        if "Error" in upload_result:
            print(f"Error during file upload: {upload_result}")
            state["error_message"] = upload_result
        else:
            print(f"File upload initiated: {upload_result}")
            state["error_message"] = None
            # We need to browse again to see the results page
            state["analysis_result"] = "File upload initiated. Need to browse results." 
    else:
        # Here we would handle a description, perhaps by calling a new tool similar to 
        # _click_element_by_description_internal but for finding an upload input.
        # For now, we treat this as an error / unsupported path.
        error_msg = f"Upload target is a description, not a direct selector. This path is not yet fully implemented: {target_selector_or_description}"
        print(error_msg)
        state["error_message"] = error_msg
        state["analysis_result"] = "Upload failed: target was a description."

    return state
    
# ... other nodes like analyze_upload_dialog, perform_upload, browse_results, analyze_results will follow ...

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
    """Determines next step after analyzing the upload dialog page."""
    print("--- Evaluating Edge: should_perform_upload_or_end ---")
    analysis_result = state.get("analysis_result")
    error = state.get("error_message")

    if error:
        print(f"Decision: Error during upload dialog analysis -> End ({error})")
        return "end_error"
    
    if analysis_result == "Upload element selector not found":
        print("Decision: Upload element selector not found -> End")
        return "end_not_found"
    
    # Basic check if it might be a selector vs a description
    # A more robust check or a different state field might be needed here.
    # For now, if it's not "not found" and no error, assume we try to upload.
    if analysis_result:
        print(f"Decision: Upload element selector/description found ({analysis_result}) -> Perform Upload")
        return "perform_upload"
    else:
        print("Decision: Upload dialog analysis failed (empty result) -> End Error")
        state["error_message"] = "Upload dialog analysis result was empty."
        return "end_error"

def should_browse_results_or_end(state: AgentState) -> str:
    """Determines next step after attempting file upload."""
    print("--- Evaluating Edge: should_browse_results_or_end ---")
    error = state.get("error_message")
    analysis_result = state.get("analysis_result")

    if error:
        print(f"Decision: Error during upload -> End ({error})")
        return "end_error"
    
    if analysis_result == "File upload initiated. Need to browse results.":
        print("Decision: Upload initiated -> Browse for results (currently END)")
        # Later, this will go to a new browse_results_node
        return "end_temp_after_upload" # Temporarily end here
    else:
        print(f"Decision: Upload status unexpected ({analysis_result}) -> End Error")
        state["error_message"] = f"Unexpected status after upload: {analysis_result}"
        return "end_error"

# --- Build the Graph --- 

workflow = StateGraph(AgentState)

# Define the nodes
workflow.add_node("start_browse", start_browse_node)
workflow.add_node("analyze_vision", analyze_vision_node) 
workflow.add_node("click", click_node) 
workflow.add_node("capture_upload_dialog_page", upload_browse_node) # Renamed upload_browse_node for clarity
workflow.add_node("analyze_upload_dialog", analyze_upload_dialog_node) # New node
workflow.add_node("perform_upload", perform_upload_node) # New node
# ... add other nodes later ...

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
        "capture_upload_dialog_page": "capture_upload_dialog_page", # Connects to the renamed upload_browse_node
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
    should_browse_results_or_end,
    {
        "end_temp_after_upload": END, # Temporarily end here, will be browse_results_node
        "end_error": END
    }
)

# Compile the graph
# memory = SqliteSaver.from_conn_string(":memory:") # Example in-memory checkpointing
app = workflow.compile() # checkpointer=memory)

# --- Main Execution (Using LangGraph) ---
async def run_graph(task: str, image_path: str):
    """Invokes the LangGraph agent."""
    print("\n--- Starting LangGraph Agent ---")
    config = {"configurable": {"thread_id": "user-session-1"}}
    initial_state = AgentState(task=task, image_path=image_path)
    
    try:
        # Stream events to see the flow
        async for event in app.astream_events(initial_state, config=config, version="v1"):
            kind = event["event"]
            node_name = event['name'] # Get name regardless of event type
            
            if kind == "on_chain_start":
                print(f"\nStarting step: {node_name}")
            elif kind == "on_chain_end":
                # <<< STRICT OMISSION: Never print direct output for on_chain_end >>>
                print(f"Finished step: {node_name} (Output details omitted)") 
            elif kind == "on_tool_start":
                 # Ensure input is truncated if potentially large
                 tool_input = str(event['data'].get('input'))
                 print(f"  Tool Start: {node_name} (Input: {tool_input[:100]}{'...' if len(tool_input) > 100 else ''})") 
            elif kind == "on_tool_end":
                 # <<< STRICT OMISSION: Always summarize or truncate tool output >>>
                 tool_output = event['data'].get('output')
                 output_summary = ""
                 if isinstance(tool_output, dict) and "screenshot_base64" in tool_output:
                      # Specific summary for browse tool
                      output_summary = f"text_len={len(tool_output.get('text_content', ''))}, screenshot: {'Yes' if tool_output.get('screenshot_base64') else 'No'}"
                 elif tool_output is not None:
                      # Generic truncation for other outputs
                      output_str = str(tool_output)
                      output_summary = f"{output_str[:80]}{'...' if len(output_str) > 80 else ''}"
                 else:
                      output_summary = "None"
                 print(f"  Tool End: {node_name} (Output Summary: {output_summary})")
                 
    except Exception as e:
        print(f"\n--- Graph Invocation Error ---")
        print(f"{type(e).__name__}: {e}")
        print(traceback.format_exc())
    finally:
        await close_page_and_browser()
        print("\n--- Graph Finished ---")

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