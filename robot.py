import os # Standard library
import sys
import datetime
import re
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.getenv("OPENROUTER_API_KEY"))

# Logging function to keep track of the robot's work
def log_action(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("robot_log.txt", "a") as f:
        f.write(f"[{timestamp}] {message}\n")

SYSTEM_PROMPT = """
You are a Senior File Robot.
CRITICAL RULES:
1. Output ONLY a single Markdown code block (```python ... ```). Do NOT write any text outside this block.
2. Use os.walk(). INSIDE the loop, check: if any(x in root for x in ['Windows', 'Program Files', 'AppData', '$Recycle.Bin']): continue
3. Use try-except blocks for EVERY file operation to skip PermissionError.
4. If moving files, check if the destination file exists. If it does, append a timestamp to the filename.
5. You ARE ALLOWED to create files and folders. Use os.makedirs(path, exist_ok=True) for folders.
6. Every file operation must use log_action("description").
"""

def clean_code_block(response):
    """Extracts code from a markdown block if present."""
    match = re.search(r'```(?:\w+)?\n(.*?)```', response, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: check if the response is just code or has some conversational prefix
    if "def " in response or "import " in response:
        # If no markdown but looks like code, try to return it.
        # But safest is to return as is if no blocks found, assuming the prompt worked.
        return response.strip()
    return response.strip()

def get_robot_instruction(user_query, dry_run=True):
    mode_instruction = (
        "STRICT RULE: Only list the actions you would take. "
        "Do NOT move files. Use print() to show what WOULD happen."
        if dry_run else "STRICT RULE: Execute the actual file operations."
    )
    
    full_prompt = f"{SYSTEM_PROMPT}\n{mode_instruction}"
    
    try:
        response = client.chat.completions.create(
            model="openrouter/free", # Using OpenRouter's auto-free model
            messages=[
                {"role": "system", "content": full_prompt},
                {"role": "user", "content": user_query}
            ]
        )
        return clean_code_block(response.choices[0].message.content)
    except Exception as e:
        return f"Error connecting to OpenRouter: {e}"

def execute_robot_code(code):
    print("\nRobot is working...")
    
    # Check for error messages from API
    if code.startswith("Error"):
        print(f"ERROR: {code}")
        return
    
    # We pass 'log_action' into the exec environment so the AI can use it
    namespace = {
        "os": os,
        "shutil": __import__('shutil'),
        "glob": __import__('glob'),
        "log_action": log_action
    }

    # Protect the parent's stdin from being closed or replaced by executed code.
    import sys as _sys
    saved_stdin_fd = None
    try:
        try:
            saved_stdin_fd = os.dup(0)
        except Exception:
            saved_stdin_fd = None

        try:
            exec(code, namespace)
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

def main():
    def has_stdin():
        try:
            return sys.stdin is not None and sys.stdin.fileno() >= 0
        except Exception:
            return False

    def safe_input(prompt='', default=None):
        try:
            return input(prompt)
        except (RuntimeError, EOFError) as e:
            if isinstance(e, RuntimeError) and 'lost sys.stdin' in str(e):
                return default
            if isinstance(e, EOFError):
                return default
            raise

    # Support running a single command via CLI args (non-interactive)
    if len(sys.argv) > 1:
        user_input = ' '.join(sys.argv[1:])
        dry_run = True
        generated_code = get_robot_instruction(user_input, dry_run=dry_run)
        print(f"Generated Code [DRY RUN (from args)]:\n{generated_code}")
        confirm = safe_input("Run this code? (y/n, default n): ", default='n')
        if confirm and confirm.lower() == 'y':
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

        # 1. Get code from Gemini (with dry-run flag)
        generated_code = get_robot_instruction(user_input, dry_run=dry_run)

        # 2. Show the code to the user for confirmation (Optional but safer)
        mode_label = "DRY RUN (Simulation)" if dry_run else "LIVE EXECUTION"
        print(f"Generated Code [{mode_label}]:\n{generated_code}")
        confirm = safe_input("Run this code? (y/n): ", default='n')

        if confirm and confirm.lower() == 'y':
            execute_robot_code(generated_code)

if __name__ == "__main__":
    main()
    