import os
import sys
import datetime
import re
import shutil
import glob
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_URL = "https://openrouter.ai/api/v1"
MODEL_NAME = "google/gemini-2.0-flash-001"

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

SYSTEM_PROMPT = """
You are a File Robot powered by Google Gemini.
CRITICAL RULES:
1. Output ONLY a single Markdown code block (```python ... ```). Do NOT write any text outside this block.
2. If asked to search "whole drive" or "C:", ALWAYS use os.walk('C:/') but INSIDE the loop, YOU MUST STRICTLY SKIP: 'Windows', 'Program Files', 'Program Files (x86)', 'AppData', '$Recycle.Bin', 'System Volume Information'.
   Code: if any(x in root for x in ['Windows', 'Program Files', 'AppData', '$Recycle.Bin']): continue
3. Use try-except blocks for EVERY file operation to skip PermissionError.
4. If moving files, check if the destination file exists. If it does, append a timestamp to the filename to avoid overwriting.
5. You ARE ALLOWED to create files and folders. Use os.makedirs(path, exist_ok=True) for folders.
6. Every file operation must use log_action("ACTION: description"). Use uppercase for the action type (e.g., MOVED: file.pdf, CREATED: folder, DELETED: temp.txt).
"""

def log_action(message):
    """Logs actions to robot_log.txt with a timestamp."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("robot_log.txt", "a") as f:
        f.write(f"[{timestamp}] {message}\n")

def clean_code_block(response):
    """Extracts code from a markdown block if present."""
    match = re.search(r'```(?:\w+)?\n(.*?)```', response, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: check if the response is just code or has some conversational prefix
    if "def " in response or "import " in response:
        return response.strip()
    return response.strip()

def get_robot_instruction(user_query, dry_run=True):
    """Gets Python code from the AI based on the user query."""
    mode_instruction = (
        "STRICT RULE: Only list the actions you would take. "
        "Do NOT move files. Use print() to show what WOULD happen."
        if dry_run else "STRICT RULE: Execute the actual file operations."
    )
    
    full_prompt = f"{SYSTEM_PROMPT}\n{mode_instruction}"
    
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": full_prompt},
                {"role": "user", "content": user_query}
            ]
        )
        return clean_code_block(response.choices[0].message.content)
    except Exception as e:
        return f"Error connecting to AI Provider: {e}"

def execute_robot_code(code):
    """Executes the generated Python code in a controlled environment."""
    print("\nRobot is working...")
    
    if code.startswith("Error"):
        print(f"ERROR: {code}")
        return
    
    # Environment for the executed code
    namespace = {
        "os": os,
        "shutil": shutil,
        "glob": glob,
        "log_action": log_action
    }

    # Protect stdin
    import sys as _sys
    saved_stdin_fd = None
    try:
        try:
            saved_stdin_fd = os.dup(0)
        except Exception:
            saved_stdin_fd = None

        try:
            exec(code, namespace)
            log_action("Task execution successful")
            print("\nTask Completed. Check robot_log.txt for details.")
        except Exception as e:
            log_action(f"ERROR: {str(e)}")
            print(f"ERROR: Robot failed: {e}")
    finally:
        if saved_stdin_fd is not None:
            try:
                os.dup2(saved_stdin_fd, 0)
                _sys.stdin = os.fdopen(0, 'r')
            except Exception:
                pass
            try:
                os.close(saved_stdin_fd)
            except Exception:
                pass

def has_stdin():
    """Checks if standard input is available."""
    try:
        return sys.stdin is not None and sys.stdin.fileno() >= 0
    except Exception:
        return False

def safe_input(prompt='', default=None):
    """Safely gets input from the user, handling errors."""
    try:
        return input(prompt)
    except (RuntimeError, EOFError) as e:
        if isinstance(e, RuntimeError) and 'lost sys.stdin' in str(e):
            return default
        if isinstance(e, EOFError):
            return default
        raise

def main():
    # Support running a single command via CLI args (non-interactive)
    if len(sys.argv) > 1:
        user_input = ' '.join(sys.argv[1:])
        dry_run = True
        generated_code = get_robot_instruction(user_input, dry_run=dry_run)
        log_action(f"CLI Request: {user_input} | Dry Run: {dry_run}")
        execute_robot_code(generated_code)
        return

    if not has_stdin():
        print("No stdin available. Run from a console or pass a command as arguments to run non-interactively.")
        return

    print("Welcome to Python Robot CLI")
    print("Type your command or 'exit' to quit.")

    while True:
        user_input = safe_input("\nYou: ", default='exit')
        if user_input is None:
            print("No input available; exiting.")
            break
        if user_input.lower() in ['exit', 'quit']:
            break

        # Ask for dry-run mode
        dry_run_input = safe_input("Dry Run? (y/n, default y): ", default='y')
        dry_run = (dry_run_input or 'y').strip().lower() != 'n'

        generated_code = get_robot_instruction(user_input, dry_run=dry_run)
        log_action(f"Request: {user_input} | Dry Run: {dry_run}")

        if dry_run:
            execute_robot_code(generated_code)
        else:
            print(f"Generated Code [LIVE EXECUTION]:\n{generated_code}")
            confirm = safe_input("Run this code? (y/n): ", default='n')

            if confirm and confirm.lower() == 'y':
                execute_robot_code(generated_code)

if __name__ == "__main__":
    main()