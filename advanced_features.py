import os
import re
from typing import Dict, List, Optional, Tuple


def parse_plan_steps(ai_text: str, max_steps: int = 8) -> List[str]:
    """Parse step lines from AI output into a clean list."""
    steps: List[str] = []
    for line in ai_text.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        cleaned = re.sub(r'^[-*]\s*', '', cleaned)
        cleaned = re.sub(r'^\d+[\.)]\s*', '', cleaned)
        if cleaned:
            steps.append(cleaned)
    return steps[:max_steps]


def interpret_advanced_nl_request(text: str) -> Optional[Dict[str, str]]:
    """Interpret natural language tool requests."""
    msg = text.strip()
    msg_lower = msg.lower().strip()

    if msg_lower in ["list files", "show files", "show project files", "ls"]:
        return {"action": "listfiles", "path": "."}

    match = re.match(r'^(?:list|show) files(?: in)?\s+(.+)$', msg_lower)
    if match:
        return {"action": "listfiles", "path": match.group(1).strip()}

    match = re.match(r'^(?:read|open|show) file\s+(.+)$', msg, re.IGNORECASE)
    if match:
        return {"action": "readfile", "path": match.group(1).strip()}

    match = re.match(r'^(?:search code for|find in code)\s+(.+)$', msg, re.IGNORECASE)
    if match:
        return {"action": "searchcode", "query": match.group(1).strip()}

    if msg_lower in ["git status", "git log", "git diff", "git branch", "git push", "git pull"]:
        return {"action": "git", "args": msg_lower.split()[1:]}

    if msg_lower in ["show config", "show settings", "config"]:
        return {"action": "config"}

    match = re.match(r'^set config\s+([A-Za-z_][A-Za-z0-9_]*)\s+(.+)$', msg, re.IGNORECASE)
    if match:
        return {"action": "setconfig", "key": match.group(1).upper(), "value": match.group(2).strip()}

    match = re.match(r'^change config\s+([A-Za-z_][A-Za-z0-9_]*)\s+to\s+(.+)$', msg, re.IGNORECASE)
    if match:
        return {"action": "setconfig", "key": match.group(1).upper(), "value": match.group(2).strip()}

    return None


def update_env_file(key: str, value: str, env_path: str = '.env') -> None:
    """Update or add a key-value pair in .env file."""
    if os.path.exists(env_path):
        with open(env_path, 'r') as env_file:
            lines = env_file.readlines()
    else:
        lines = []

    key_found = False
    for idx, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[idx] = f"{key}={value}\n"
            key_found = True
            break

    if not key_found:
        lines.append(f"{key}={value}\n")

    with open(env_path, 'w') as env_file:
        env_file.writelines(lines)


def list_directory_summary(path: str, project_dir: str, max_items: int = 50) -> Tuple[bool, str, List[str], List[str]]:
    """Validate and list a directory; returns (ok, message, dirs, files)."""
    abs_path = os.path.abspath(path)
    if not abs_path.startswith(project_dir):
        return False, "❌ Access denied: Can only list files within project directory.", [], []

    if not os.path.exists(path):
        return False, f"❌ Path not found: {path}", [], []

    if not os.path.isdir(path):
        return False, f"❌ Not a directory: {path}", [], []

    items = sorted(os.listdir(path))
    dirs = [item for item in items if os.path.isdir(os.path.join(path, item))][:max_items]
    files = [item for item in items if os.path.isfile(os.path.join(path, item))][:max_items]
    return True, "", dirs, files


def read_file_preview(path: str, project_dir: str, preview_chars: int = 3500) -> Tuple[bool, str, str, bool]:
    """Read validated file preview; returns (ok, message, preview, truncated)."""
    abs_path = os.path.abspath(path)
    if not abs_path.startswith(project_dir):
        return False, "❌ Access denied: Can only read files within project directory.", "", False

    if not os.path.isfile(path):
        return False, f"❌ File not found: {path}", "", False

    with open(path, 'r', encoding='utf-8', errors='ignore') as file_obj:
        content = file_obj.read()

    preview = content[:preview_chars]
    return True, "", preview, len(content) > preview_chars


def search_codebase(search_term: str, root: str = '.') -> List[str]:
    """Search text across codebase files (safe local traversal)."""
    matches: List[str] = []
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ['.git', 'env', 'venv', '__pycache__', 'node_modules']]
        for file_name in files:
            if file_name.endswith(('.py', '.js', '.md', '.txt', '.json')):
                file_path = os.path.join(current_root, file_name)
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as file_obj:
                        for line_num, line in enumerate(file_obj, 1):
                            if search_term.lower() in line.lower():
                                matches.append(f"{file_path}:{line_num}:{line.strip()}")
                except Exception:
                    continue
    return matches
