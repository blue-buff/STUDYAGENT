#!/usr/bin/env python3
"""
Session Monitor: Heartbeat + Expiry Detection for ZuJuan login session.

Strategy:
  1. Periodically (every 30 min) send a request to zujuan.xkw.com user center
  2. Check if the response indicates logged-in state
  3. If logged out, check which specific cookies expired
  4. Log all events to a file for analysis
  5. Optionally trigger alert/notification

The heartbeat serves two purposes:
  - Detect expiry early (before a pipeline run fails)
  - Test if periodic activity extends session lifetime (asp.net sliding expiration)

Usage:
  python session_monitor.py                          # One-shot check
  python session_monitor.py --daemon                 # Run continuously (every 30 min)
  python session_monitor.py --daemon --interval 600  # Every 10 minutes
  python session_monitor.py --once                   # Single check + report

Cron usage:
  */30 * * * * cd ... && python session_monitor.py --once
"""

import json
import os
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import requests

# =============================================================================
# Configuration
# =============================================================================

SHARED_DIR = Path('/Users/song/project/STUDYAGENT/get from web/shared')
STATE_FILE = SHARED_DIR / 'storage-state.json'
LOG_DIR = Path('/Users/song/project/STUDYAGENT/get from web/research_c')
LOG_FILE = LOG_DIR / 'session_monitor.log'

CHECK_URLS = [
    # Primary: user center page (requires full login)
    ('https://zujuan.xkw.com', 'homepage'),
    # Alternative: API base (serves config even without login, but we check content)
    ('https://zujuan.xkw.com/zujuan-api/base', 'api_base'),
]

# Login indicators in homepage HTML
LOGGED_IN_INDICATORS = [
    'J_realname',
    '退出',
    'userId',
]

LOGGED_OUT_INDICATORS = [
    'login-btn',
    '请登录',
]


def load_session():
    """Load Playwright cookies into a requests.Session."""
    with open(STATE_FILE) as f:
        data = json.load(f)

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/125.0.0.0 Safari/537.36',
    })

    for c in data['cookies']:
        session.cookies.set(
            name=c['name'],
            value=c['value'],
            domain=c.get('domain', ''),
            path=c.get('path', '/'),
            expires=c.get('expires') if c.get('expires', -1) > 0 else None,
            secure=c.get('secure', False),
        )

    return session


def check_login_status(session: requests.Session) -> Tuple[bool, str]:
    """
    Check if the session is logged in.
    Returns (is_logged_in, detail_message).
    """
    try:
        resp = session.get(CHECK_URLS[0][0], timeout=15, allow_redirects=True)
        html = resp.text

        # Check for logged-out indicators
        for indicator in LOGGED_OUT_INDICATORS:
            if indicator in html:
                # Verify it's actually a login button, not just text
                if indicator == 'login-btn':
                    # More precise check
                    if 'class="login-btn"' in html or "class='login-btn'" in html:
                        return False, f"Found login button (logged out)"
                else:
                    return False, f"Found '{indicator}' (logged out)"

        # Check for logged-in indicators
        for indicator in LOGGED_IN_INDICATORS:
            if indicator in html:
                return True, f"Found '{indicator}' (logged in)"

        return False, f"No clear login indicator (status={resp.status_code})"

    except requests.RequestException as e:
        return False, f"Request failed: {e}"


def check_cookie_expiry() -> dict:
    """Check which cookies in storage-state.json are expired."""
    with open(STATE_FILE) as f:
        data = json.load(f)

    now_ts = time.time()
    result = {
        'total': len(data['cookies']),
        'expired': [],
        'session': [],
        'valid': [],
    }

    for c in data['cookies']:
        expires = c.get('expires', -1)
        if expires == -1:
            result['session'].append(c['name'])
        elif expires < now_ts:
            result['expired'].append({
                'name': c['name'],
                'domain': c.get('domain', ''),
                'expired_at': datetime.fromtimestamp(expires).isoformat(),
            })
        else:
            result['valid'].append({
                'name': c['name'],
                'domain': c.get('domain', ''),
                'expires_at': datetime.fromtimestamp(expires).isoformat(),
                'hours_left': (expires - now_ts) / 3600,
            })

    return result


def log_event(message: str, level: str = 'INFO'):
    """Write a timestamped event to the log file."""
    timestamp = datetime.now().isoformat()
    line = f"[{timestamp}] [{level}] {message}"
    print(line)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')


def run_check() -> dict:
    """Run a single health check. Returns result dict."""
    result = {
        'timestamp': datetime.now().isoformat(),
        'is_logged_in': False,
        'detail': '',
        'cookie_status': {},
    }

    # Check cookie file exists
    if not STATE_FILE.exists():
        result['detail'] = 'storage-state.json not found'
        log_event(result['detail'], 'ERROR')
        return result

    # Check cookie expiry
    cookie_status = check_cookie_expiry()
    result['cookie_status'] = cookie_status

    if cookie_status['expired']:
        expired_names = [e['name'] for e in cookie_status['expired']]
        log_event(f"Expired cookies: {expired_names}")

    # Check login via HTTP
    try:
        session = load_session()
        is_logged_in, detail = check_login_status(session)
        result['is_logged_in'] = is_logged_in
        result['detail'] = detail

        if is_logged_in:
            log_event(f"Session ACTIVE: {detail}")
        else:
            log_event(f"Session DEAD: {detail}", 'WARNING')
    except Exception as e:
        result['detail'] = f"Error: {e}"
        log_event(f"Check failed: {e}", 'ERROR')

    return result


def daemon_loop(interval: int = 1800):
    """Run continuous monitoring with specified interval (seconds)."""
    log_event(f"Session monitor daemon started (interval={interval}s)")
    log_event(f"Monitoring: {STATE_FILE}")

    consecutive_failures = 0

    while True:
        try:
            result = run_check()
            if not result['is_logged_in']:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    log_event(
                        f"ALERT: Session expired for {consecutive_failures} "
                        f"consecutive checks. Re-login needed!",
                        'ALERT'
                    )
            else:
                consecutive_failures = 0
        except Exception as e:
            log_event(f"Daemon loop error: {e}", 'ERROR')

        time.sleep(interval)


def main():
    default_state = str(SHARED_DIR / 'storage-state.json')
    parser = argparse.ArgumentParser(description='ZuJuan Session Monitor')
    parser.add_argument('--daemon', action='store_true',
                        help='Run continuously')
    parser.add_argument('--once', action='store_true',
                        help='Run once and exit (suitable for cron)')
    parser.add_argument('--interval', type=int, default=1800,
                        help='Check interval in seconds (default: 1800 = 30min)')
    parser.add_argument('--state', type=str, default=default_state,
                        help='Path to storage-state.json')
    args = parser.parse_args()

    global STATE_FILE
    STATE_FILE = Path(args.state)

    if args.daemon:
        daemon_loop(args.interval)
    else:
        result = run_check()
        print(f"\nStatus: {'ACTIVE' if result['is_logged_in'] else 'EXPIRED'}")
        print(f"Detail: {result['detail']}")
        if result['cookie_status'].get('expired'):
            print(f"Expired: {[e['name'] for e in result['cookie_status']['expired']]}")


if __name__ == '__main__':
    main()
