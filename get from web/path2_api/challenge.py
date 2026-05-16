"""
Anti-bot challenge solver for zujuan.xkw.com

The website uses an Alibaba Cloud WAF (alicfw) that returns a challenge page
with obfuscated MurmurHash-based JavaScript. The JS computes a hash from:
- parm_0, parm_1 (hidden inputs)
- window.location.host, window.location.protocol
- document.documentElement.clientWidth, clientHeight

This module uses a Node.js subprocess with JSDOM to execute the challenge JS
and extract the resulting cookies.
"""

import json
import os
import re
import shutil
import subprocess
import sys

# Path to the Node.js solver script
_SOLVER_JS = os.path.join(os.path.dirname(__file__), 'solve_challenge.js')

# Find the real node binary (the shell may wrap it in a function)
# Prefer nvm node over system node for ESM compatibility
def _find_node():
    nvm_versions = os.path.expanduser('~/.nvm/versions/node')
    if os.path.isdir(nvm_versions):
        versions = sorted(os.listdir(nvm_versions), reverse=True)
        for v in versions:
            node_path = os.path.join(nvm_versions, v, 'bin', 'node')
            if os.path.isfile(node_path):
                return node_path
    return shutil.which('node') or 'node'

_NODE_BIN = _find_node()


def _solve_via_node(html: str, url: str = 'https://zujuan.xkw.com/') -> dict:
    """Run the Node.js challenge solver with HTML content via stdin."""
    try:
        result = subprocess.run(
            [_NODE_BIN, _SOLVER_JS, '--stdin', url],
            input=html,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.path.dirname(__file__),
        )
        # Parse the last JSON line from stdout
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if line.startswith('{'):
                return json.loads(line)
        return {}
    except subprocess.TimeoutExpired:
        print("[Challenge] Solver timed out")
        return {}
    except Exception as e:
        print(f"[Challenge] Solver error: {e}")
        return {}


def _detect_challenge(html: str) -> bool:
    """Check if the HTML is an anti-bot challenge page."""
    return 'parm_0' in html and 'hash32' in html and 'alicfw' in html


def solve_challenge(session, url: str) -> bool:
    """
    Detect and solve anti-bot challenge for a URL.

    Args:
        session: requests.Session
        url: Target URL

    Returns:
        True if cookies were successfully obtained
    """
    try:
        resp = session.get(url, timeout=15)
        html = resp.text

        if not _detect_challenge(html):
            return True  # No challenge on this URL

        print("[Challenge] Anti-bot challenge detected, solving via Node.js...")
        cookies = _solve_via_node(html, url)

        if 'alicfw' in cookies:
            for name, value in cookies.items():
                session.cookies.set(name, value, domain='.zujuan.xkw.com')
                session.cookies.set(name, value, domain='.xkw.com')
            print(f"[Challenge] Cookies obtained: {list(cookies.keys())}")
            return True
        else:
            print("[Challenge] Failed to obtain alicfw cookie")
            return False

    except Exception as e:
        print(f"[Challenge] Error: {e}")
        return False


def ensure_challenge_cookies(session, url: str = 'https://zujuan.xkw.com/gzsx/zsd27942/qt2701d3o2/') -> bool:
    """
    Ensure the session has valid anti-bot cookies.
    Only solves the challenge if needed (cookies missing or expired).

    Returns True if cookies are valid.
    """
    # Check if we already have valid cookies
    if 'alicfw' in session.cookies.get_dict():
        # Test with a quick request
        try:
            resp = session.get(url, timeout=10)
            if not _detect_challenge(resp.text):
                return True
            print("[Challenge] Existing cookies expired, re-solving...")
        except Exception:
            pass

    return solve_challenge(session, url)


if __name__ == '__main__':
    import requests
    sess = requests.Session()
    sess.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    })
    ok = solve_challenge(sess, sys.argv[1] if len(sys.argv) > 1 else
                          'https://zujuan.xkw.com/gzsx/zsd27942/qt2701d3o2/')
    print(f"Challenge solved: {ok}")
    if ok:
        print(f"Cookies: {sess.cookies.get_dict()}")
