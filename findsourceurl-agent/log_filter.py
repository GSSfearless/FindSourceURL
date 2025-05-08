import re
import sys
import os

def clean_ansi_codes(text):
    ansi_escape = re.compile(r'\\x1B(?:[@-Z\\\\-_]|\\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

# Keywords/patterns that indicate a line is important and should be kept directly
KEEP_PATTERNS_DIRECT = [
    r"--- Executing Node:",
    r"--- Evaluating Edge:",
    r"Decision:",
    r"LLM .* Analysis Result:",
    r"\\[Internal Tool\\]", # Escaped for regex
    r"\\[Browser Tool -", # Escaped for regex
    r"Error",
    r"Traceback",
    r"SyntaxError",
    r"Exception",
    r"TimeoutError",
    r"\\[Perform Upload Node\\] Cleaned analysis result:",
    r"\\[Upload Browse Node\\] Captured text and screenshot",
    r"Screenshot .* saved to:",
    r"OPENAI_API_KEY found",
    r"Attempting to use image path:",
    r"ChatOpenAI LLM initialized successfully",
    r"\\[LangChain\\] Debug mode enabled",
    r"--- Graph Finished ---",
    r"--- Graph Invocation Error ---",
    r"--- Starting LangGraph Agent ---",
    r"Tool End: .* \\(Output Summary:", # Escaped for regex
    r"^\\[\\\] ", # Lines starting with [*] like in Playwright logs for actionability
    r"python :", # For python execution errors like the SyntaxError we saw
    r"\\s*\\^\\s*$", # Lines that are just a pointer for SyntaxError
    r"^\s*File \"", # Lines from Traceback indicating file path
    r"^\s*\S+Error:", # Lines starting with an error type
]

# Keywords that, if present, make a generic LangChain line more interesting
INTERESTING_IN_LANGCHAIN_LOG = [
    "error",
    "fail",
    "retry",
    "warning",
    # Specific state keys we might care about if they appear in generic logs
    "current_url",
    "page_content", # This might be too verbose, but let's see
    "analysis_result",
    "tool_input",
]

def process_log_file(input_filepath="agent_run.log", output_filepath="agent_run.summary.log"):
    print(f"Processing {input_filepath} to {output_filepath}...")
    kept_lines_count = 0
    total_lines_count = 0
    lines_since_last_kept = 0
    max_consecutive_skipped = 5 # Max consecutive generic lines to skip before printing a placeholder

    if not os.path.exists(input_filepath):
        print(f"Error: Input log file '{input_filepath}' not found. Please run agent_main.py first.")
        return

    with open(input_filepath, "r", encoding="utf-8", errors='ignore') as infile, \
         open(output_filepath, "w", encoding="utf-8") as outfile:
        
        for line_number, raw_line in enumerate(infile, 1):
            total_lines_count += 1
            cleaned_line_content = clean_ansi_codes(raw_line.rstrip())
            
            keep_this_line = False
            
            # First, check direct keep patterns
            for pattern in KEEP_PATTERNS_DIRECT:
                if re.search(pattern, cleaned_line_content, re.IGNORECASE):
                    keep_this_line = True
                    break
            
            # If not directly kept, check if it's a LangChain/Graph line that contains interesting keywords
            if not keep_this_line:
                if re.match(r"\\[(chain|llm|tool|agent|prompt)/.*\\]", cleaned_line_content): # Generic LangChain log prefix
                    for keyword in INTERESTING_IN_LANGCHAIN_LOG:
                        if keyword.lower() in cleaned_line_content.lower():
                            keep_this_line = True
                            break
                    if not keep_this_line and len(cleaned_line_content) < 150 : # Keep shorter LangChain lines
                         # Example: keep short "Exiting Chain run with output: {'output': 'click'}"
                         if re.search(r"Exiting .* run with output:", cleaned_line_content) or \
                            re.search(r"Entering .* run with input:", cleaned_line_content):
                             keep_this_line = True


            if keep_this_line:
                if lines_since_last_kept > max_consecutive_skipped:
                    outfile.write(f"    (... {lines_since_last_kept} lines skipped ...)\\n")
                outfile.write(raw_line) # Write original line with ANSI for context if kept, or cleaned_line_content
                kept_lines_count += 1
                lines_since_last_kept = 0
            else:
                lines_since_last_kept += 1
        
        if lines_since_last_kept > 0: # If the file ends with skipped lines
            outfile.write(f"    (... {lines_since_last_kept} lines skipped ...)\\n")


    print(f"Processing complete. Kept approximately {kept_lines_count} lines out of {total_lines_count}.")
    print(f"Summary log saved to: {output_filepath}")

if __name__ == "__main__":
    input_log = "agent_run.log"
    summary_log = "agent_run.summary.log"
    
    # Simple arg parsing for potentially different filenames
    if len(sys.argv) > 1:
        input_log = sys.argv[1]
        if len(sys.argv) > 2:
            summary_log = sys.argv[2]
        else:
            # Construct summary log name from input log name
            base, ext = os.path.splitext(input_log)
            summary_log = base + ".summary" + ext

    process_log_file(input_log, summary_log) 