"""
QR code WeChat login flow for zujuan.xkw.com

Flow:
1. GET passport.zujuan.com/login → session cookie
2. GET passport.zujuan.com/connect/weixin-qrcode → QR code URL + ticket
3. Display/save QR code image
4. Poll passport.zujuan.com/connect/issubscribe → check scan status
5. GET passport.zujuan.com/connect/wxlogin → complete login
6. Verify login by checking www.zujuan.com/u/index
"""

import json
import os
import pickle
import random
import time
from urllib import parse

import requests
from requests.cookies import RequestsCookieJar

# -------- URL Constants --------
LOGIN_URL = 'https://passport.zujuan.com/login'
QRCODE_URL = 'https://passport.zujuan.com/connect/weixin-qrcode?iframe=1&width=220&height=220'
ISSUBSCRIBE_URL = 'https://passport.zujuan.com/connect/issubscribe'
WXLOGIN_URL = 'https://passport.zujuan.com/connect/wxlogin'
USER_URL = 'https://www.zujuan.com/u/index'
JUMP_URL = 'https://www.zujuan.com'

# -------- Cookie persistence --------
DEFAULT_COOKIE_FILE = os.path.join(os.path.dirname(__file__), 'config', 'cookies.pkl')


def save_cookies(cookies, path=None):
    """Save cookies to a pickle file."""
    path = path or DEFAULT_COOKIE_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        pickle.dump(cookies.get_dict(), f)
    print(f"[Login] Cookies saved to {path}")


def load_cookies(path=None):
    """Load cookies from a pickle file."""
    path = path or DEFAULT_COOKIE_FILE
    try:
        with open(path, 'rb') as f:
            data = pickle.load(f)
        return requests.utils.cookiejar_from_dict(data)
    except FileNotFoundError:
        return RequestsCookieJar()
    except Exception as e:
        print(f"[Login] Error loading cookies: {e}")
        return RequestsCookieJar()


def _save_qrcode_image(session, qrcode_url, path=None):
    """Download and save QR code image."""
    path = path or os.path.join(os.path.dirname(__file__), 'qrcode', 'wx_qrcode.png')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    resp = session.get(qrcode_url)
    with open(path, 'wb') as f:
        f.write(resp.content)
    print(f"[Login] QR code saved to {path}")
    return path


def get_qrcode(session):
    """
    Get the QR code URL and ticket for WeChat scan login.

    Returns:
        (qrcode_url, ticket) or (None, None) on failure
    """
    try:
        # Step 1: Get login page for initial cookies
        session.get(LOGIN_URL, timeout=10)

        # Step 2: Get QR code page
        resp = session.get(QRCODE_URL, timeout=10)
        # Parse QR code URL from the page
        import re
        match = re.search(r'<img[^>]*src="([^"]*showqrcode[^"]*)"', resp.text)
        if not match:
            print("[Login] Could not find QR code URL in page")
            return None, None

        qrcode_url = match.group(1)

        # Step 3: Extract ticket from QR code URL
        parsed = parse.urlparse(qrcode_url)
        params = dict(parse.parse_qsl(parsed.query))
        ticket = params.get('ticket')
        if not ticket:
            print("[Login] Could not extract ticket from QR code URL")
            return None, None

        return qrcode_url, ticket

    except Exception as e:
        print(f"[Login] Error getting QR code: {e}")
        return None, None


def wait_for_scan(session, ticket, timeout=300, poll_interval=2):
    """
    Poll to check if the QR code has been scanned.

    Args:
        session: requests.Session
        ticket: QR code ticket string
        timeout: Max wait time in seconds
        poll_interval: Seconds between polls

    Returns:
        True if scanned, False if timed out
    """
    print(f"[Login] Waiting for QR code scan (ticket: {ticket[:20]}...)")
    print(f"[Login] Timeout: {timeout}s")

    check_cnt = 0
    max_checks = timeout // poll_interval

    while check_cnt < max_checks:
        query = {
            'ticket': ticket,
            'jump_url': JUMP_URL,
            'r': random.random(),
        }
        check_url = ISSUBSCRIBE_URL + '?' + parse.urlencode(query)

        try:
            resp = session.get(check_url, timeout=10)
            data = json.loads(resp.text)
            code = data.get('code', -1)

            if code == 1:
                print("[Login] QR code scanned!")
                return True
            elif code == 0:
                if check_cnt % 5 == 0:
                    print(f"[Login] Waiting... ({check_cnt * poll_interval}s elapsed)")
            else:
                print(f"[Login] Unexpected response code: {code}, data: {data}")

        except Exception as e:
            print(f"[Login] Poll error: {e}")

        time.sleep(poll_interval)
        check_cnt += 1

    print("[Login] Scan timed out")
    return False


def complete_login(session, ticket):
    """
    Complete the WeChat scan login.

    Args:
        session: requests.Session
        ticket: QR code ticket string

    Returns:
        True if login successful
    """
    try:
        query = {
            'ticket': ticket,
            'jump_url': JUMP_URL,
        }
        resp = session.get(WXLOGIN_URL + '?' + parse.urlencode(query),
                           verify=False, timeout=15)
        if resp.status_code == 200:
            print("[Login] WeChat login completed successfully")
            return True
        else:
            print(f"[Login] WeChat login failed with status {resp.status_code}")
            return False
    except Exception as e:
        print(f"[Login] Error completing login: {e}")
        return False


def check_login_status(session):
    """
    Check if the session is currently logged in.

    Returns:
        (is_logged_in, username)
    """
    try:
        resp = session.get(USER_URL, timeout=10)
        import re
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(resp.text, 'html.parser')

        # Check for login failure indicators
        fail = soup.find('div', class_='mistack-content')
        if fail and '未登录' in fail.text:
            return False, None

        # Check for login success indicator
        success = soup.find('legend', class_='form-title')
        if success and '第三方账号绑定' in success.text:
            # Try to get username
            realname = soup.find('div', id='J_realname')
            username = realname.text.strip() if realname else 'unknown'
            return True, username

        # Alternative: check for username in the page
        realname = soup.find('div', id='J_realname')
        if realname:
            return True, realname.text.strip()

        return False, None

    except Exception as e:
        print(f"[Login] Error checking login status: {e}")
        return False, None


def login_interactive(session=None, cookie_path=None, qrcode_path=None):
    """
    Interactive QR code login flow.

    1. Check if valid cookies exist
    2. If not, show QR code and wait for scan
    3. Save cookies on success

    Returns:
        (session, is_logged_in)
    """
    if session is None:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        })
        session.verify = False

    # Suppress SSL warnings
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # Try existing cookies first
    existing = load_cookies(cookie_path)
    if existing:
        session.cookies = existing
        logged_in, username = check_login_status(session)
        if logged_in:
            print(f"[Login] Already logged in as: {username}")
            return session, True
        else:
            print("[Login] Existing cookies expired, re-logging in...")

    # Start QR code login
    qrcode_url, ticket = get_qrcode(session)
    if not qrcode_url or not ticket:
        print("[Login] Failed to get QR code")
        return session, False

    # Save QR code image
    _save_qrcode_image(session, qrcode_url, qrcode_path)

    # Display
    print("\n" + "=" * 50)
    print("[Login] Please scan the QR code with WeChat")
    print(f"[Login] QR code image: {qrcode_path or 'qrcode/wx_qrcode.png'}")
    print("=" * 50 + "\n")

    # Wait for scan
    if not wait_for_scan(session, ticket):
        return session, False

    # Complete login
    if not complete_login(session, ticket):
        return session, False

    # Verify login
    logged_in, username = check_login_status(session)
    if logged_in:
        print(f"[Login] Successfully logged in as: {username}")
        save_cookies(session.cookies, cookie_path)
    else:
        print("[Login] Login verification failed")

    return session, logged_in


if __name__ == '__main__':
    import urllib3
    urllib3.disable_warnings()

    sess = requests.Session()
    sess.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    })
    sess.verify = False

    sess, ok = login_interactive(sess)
    if ok:
        print("Login successful!")
        print(f"Cookies: {dict(sess.cookies)}")
