import os
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Tuple, Optional


def extract_error_block(output: str) -> str:
    """Estract a specific error block from Fast Downward output."""
    if not output.strip():
        return "Unknown error (empty output)"

    lines = output.split('\n')

    # First check for specific error patterns
    specific_patterns = [
        r"Undefined object\s*Got:\s*(\w+)",  # Not defined object error
        r"Undefined predicate\s*Got:\s*(\w+)",  # Not defined predicate error
        r"Syntax error.*",  # Sintax error
        r"Parse error.*",  # Parsing error
    ]

    # Search for specific patterns in the output and catch the context
    for i, line in enumerate(lines):
        for pattern in specific_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                # Catch the context around the error line
                start_idx = max(0, i - 1)
                end_idx = min(len(lines), i + 3)
                context_lines = []

                # Add the error line itself
                for j in range(start_idx, end_idx):
                    line_content = lines[j].strip()
                    if line_content and not line_content.startswith('INFO'):
                        context_lines.append(line_content)

                if context_lines:
                    return '\n'.join(context_lines)


    # If no specific error found, check for exit codes
    if re.search(r'translate exit code: (?!0\b)\d+', output):
        # Search for the last non-INFO line that seems to indicate an error
        for i in reversed(range(len(lines))):
            line = lines[i].strip()
            # Search raw that seems errors, but they are not INFO lines
            if (line and
                    not line.startswith('INFO') and
                    not line.startswith('translate exit code') and
                    not line.startswith('Driver aborting') and
                    ('error' in line.lower() or 'undefined' in line.lower() or 'got:' in line.lower())):

                # Search for context around the error line
                start_idx = max(0, i - 1)
                end_idx = min(len(lines), i + 3)
                context_lines = []

                for j in range(start_idx, end_idx):
                    context_line = lines[j].strip()
                    if (context_line and
                            not context_line.startswith('INFO') and
                            not context_line.startswith('translator')):
                        context_lines.append(context_line)

                if context_lines:
                    return '\n'.join(context_lines)

        # If no specific error found, return a generic message
        return "Translation failed - check PDDL syntax and object definitions"

    # Search for generic error keywords in the output
    error_keywords = ['error', 'failed', 'undefined', 'syntax']
    for line in lines:
        line_lower = line.lower().strip()
        if any(keyword in line_lower for keyword in error_keywords) and not line_lower.startswith('info'):
            return line.strip()

    # Finally returns all the output
    return output.strip()


class PDDLValidator:
    # Driver options come before the input files; A* with LM-cut returns an optimal plan,
    # so its length is the true quest depth.
    FD_DRIVER_ARGS = ["--overall-time-limit", "25s"]
    FD_SEARCH_ARGS = ["--search", "astar(lmcut())"]

    def __init__(self, fd_path: str | None = None, wsl_distro: str | None = None,
                 depth_constraints: dict | None = None):
        """Fast Downward validator with plan-length (depth) bounds.

        On Windows the planner runs inside WSL (wsl_distro, or the default distro when None).
        fd_path is the Fast Downward checkout; it defaults to $FAST_DOWNWARD_PATH, else ~/downward.
        """
        self.depth_constraints = depth_constraints
        if platform.system() == "Windows":
            wsl = ["wsl", *(["-d", wsl_distro] if wsl_distro else []), "-e"]
            home = self._wsl_home(wsl)
            self.python = [*wsl, "python3"]
        else:
            home = str(Path.home())
            self.python = [sys.executable]
        self.fd_path = fd_path or os.environ.get("FAST_DOWNWARD_PATH") or f"{home}/downward"

    @staticmethod
    def _wsl_home(wsl: list[str]) -> str:
        """Return the WSL user's home directory; fail fast if WSL is not usable."""
        try:
            result = subprocess.run([*wsl, "printenv", "HOME"], capture_output=True, text=True)
        except FileNotFoundError:
            raise RuntimeError("WSL not found. Please install WSL on Windows 10/11")
        if result.returncode != 0 or not result.stdout.strip():
            raise RuntimeError("WSL not properly installed or configured (no Linux distribution?)")
        return result.stdout.strip()

    def _check_depth(self, output: str) -> Optional[str]:
        """Return an error message if the plan length violates the depth constraints, else None."""
        if not self.depth_constraints:
            return None
        match = re.search(r"Plan length: (\d+) step", output)
        if not match:
            return "Plan length not found in Fast Downward output"
        steps = int(match.group(1))
        min_d = int(self.depth_constraints.get("min") or 1)
        max_d = int(self.depth_constraints.get("max") or steps)
        if not min_d <= steps <= max_d:
            return f"Plan length {steps} outside depth constraints [{min_d}, {max_d}]"
        return None

    def validate(self, domain_content: str, problem_content: str) -> Tuple[
        bool, Optional[str], Optional[str]]:
        """Validate domain and problem using Fast Downward. Returns (success, error_message, plan_text)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "domain.pddl").write_text(domain_content, encoding="utf-8")
            Path(tmpdir, "problem.pddl").write_text(problem_content, encoding="utf-8")
            # Run inside tmpdir with relative paths: WSL maps the Windows working directory itself,
            # and the planner writes sas_plan there, readable from both sides. No shell is involved.
            command = [*self.python, f"{self.fd_path}/fast-downward.py", *self.FD_DRIVER_ARGS,
                       "domain.pddl", "problem.pddl", *self.FD_SEARCH_ARGS]

            try:
                result = subprocess.run(command, cwd=tmpdir, capture_output=True, text=True, timeout=60)
            except subprocess.TimeoutExpired:
                return False, "Validation timeout - problem might be too complex", None
            except FileNotFoundError:
                return False, "Fast Downward executable not found", None

            # Combine stdout and stderr for analysis
            full_output = result.stdout + "\n" + result.stderr

            print("=== Fast Downward output ===")
            print(full_output)
            print("============================")

            if "Solution found!" in full_output:
                depth_error = self._check_depth(full_output)
                if depth_error:
                    return False, depth_error, None
                plan_file = Path(tmpdir, "sas_plan")
                return True, None, plan_file.read_text(encoding="utf-8") if plan_file.exists() else None
            if "Completely explored state space -- no solution!" in full_output:
                return False, "Goal is provably unreachable from initial state", None
            if "Search stopped without finding a solution." in full_output:
                return False, "No solution found - goal might be unreachable", None
            if result.returncode == 0:
                return False, "Unknown outcome despite successful execution", None
            return False, f"Fast Downward error:\n{extract_error_block(full_output)}", None
