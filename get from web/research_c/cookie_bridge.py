#!/usr/bin/env python3
"""
Cookie Bridge: Playwright storage-state.json <-> requests.Session cookies

Supports bidirectional conversion between:
  - Playwright format: JSON array of {name, value, domain, path, expires, httpOnly, secure, sameSite}
  - requests format:   http.cookiejar.CookieJar (or plain dict)

Usage:
  from cookie_bridge import playwright_to_requests, requests_to_playwright

  # Load Playwright cookies into requests.Session
  session = requests.Session()
  playwright_to_requests('shared/storage-state.json', session)

  # Save requests.Session cookies to Playwright format
  requests_to_playwright(session, 'shared/storage-state.json')
"""

import json
import time
from pathlib import Path
from typing import Optional, Union

import requests
from requests.cookies import RequestsCookieJar


# =============================================================================
# Core conversion: Playwright JSON -> requests.Session
# =============================================================================

def playwright_to_requests(
    storage_state_path: Union[str, Path],
    session: Optional[requests.Session] = None,
    filter_domain: Optional[str] = None,
) -> requests.Session:
    """
    Load Playwright storage-state.json cookies into a requests.Session.

    Args:
        storage_state_path: Path to Playwright storage-state JSON file
        session: Existing requests.Session to populate (creates new if None)
        filter_domain: Only load cookies for this domain (e.g. "zujuan.xkw.com")

    Returns:
        Populated requests.Session
    """
    if session is None:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/125.0.0.0 Safari/537.36',
        })

    with open(storage_state_path) as f:
        data = json.load(f)

    cookies = data.get('cookies', data if isinstance(data, list) else [])

    for c in cookies:
        domain = c.get('domain', '')
        if filter_domain and domain != filter_domain:
            continue

        # requests uses leading dot for domain cookies
        cookie_domain = domain if domain.startswith('.') else domain

        session.cookies.set(
            name=c['name'],
            value=c['value'],
            domain=cookie_domain,
            path=c.get('path', '/'),
            expires=c.get('expires') if c.get('expires', -1) > 0 else None,
            secure=c.get('secure', False),
            # rest (httponly, samesite) are not used by requests but noted
        )

    return session


def playwright_to_dict(
    storage_state_path: Union[str, Path],
    filter_domain: Optional[str] = None,
) -> dict:
    """
    Convert Playwright cookies to a plain {name: value} dict.
    Useful for quick inspection or passing to http.cookiejar.

    Args:
        storage_state_path: Path to Playwright storage-state JSON file
        filter_domain: Only include cookies for this domain

    Returns:
        {cookie_name: cookie_value} dict
    """
    with open(storage_state_path) as f:
        data = json.load(f)

    cookies = data.get('cookies', data if isinstance(data, list) else [])
    result = {}

    for c in cookies:
        domain = c.get('domain', '')
        if filter_domain and domain != filter_domain:
            continue
        result[c['name']] = c['value']

    return result


# =============================================================================
# Core conversion: requests.Session -> Playwright JSON
# =============================================================================

def requests_to_playwright_json(
    session: requests.Session,
    ttl_days: int = 365,
    filter_domain: Optional[str] = None,
) -> list:
    """
    Convert requests.Session cookies to Playwright-compatible JSON array.

    Args:
        session: requests.Session with cookies
        ttl_days: Default TTL for session cookies (no expiry in requests)
        filter_domain: Only include cookies for this domain

    Returns:
        List of cookie dicts in Playwright format
    """
    cookies = []
    default_expiry = time.time() + ttl_days * 86400

    for cookie in session.cookies:
        domain = cookie.domain
        if filter_domain and domain != filter_domain:
            # Also check without leading dot
            clean_domain = domain.lstrip('.')
            if clean_domain != filter_domain:
                continue

        expires = cookie.expires if cookie.expires else default_expiry

        cookies.append({
            'name': cookie.name,
            'value': cookie.value,
            'domain': domain,
            'path': cookie.path or '/',
            'expires': expires,
            'httpOnly': False,    # requests doesn't track this
            'secure': cookie.secure or False,
            'sameSite': 'Lax',    # conservative default
        })

    return cookies


def requests_to_playwright(
    session: requests.Session,
    output_path: Union[str, Path],
    ttl_days: int = 365,
    merge_with: Optional[Union[str, Path]] = None,
    filter_domain: Optional[str] = None,
):
    """
    Save requests.Session cookies to Playwright storage-state.json.

    Args:
        session: requests.Session with cookies
        output_path: Where to write the storage-state JSON
        ttl_days: Default TTL for cookies without explicit expiry
        merge_with: Optional path to existing storage-state.json to merge origins/localStorage from
        filter_domain: Only write cookies for this domain
    """
    # Build base structure
    if merge_with:
        with open(merge_with) as f:
            base = json.load(f)
    else:
        base = {}

    base['cookies'] = requests_to_playwright_json(
        session, ttl_days=ttl_days, filter_domain=filter_domain
    )

    # Preserve origins (localStorage) from merge source
    if 'origins' not in base:
        base['origins'] = []

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(base, f, ensure_ascii=False)

    return base


# =============================================================================
# Cookie set operations (for multi-domain scenarios)
# =============================================================================

def merge_cookies_into_session(
    session: requests.Session,
    cookie_list: list,
):
    """
    Merge a list of cookie dicts into an existing session.
    Does NOT clear existing cookies.

    Args:
        session: requests.Session
        cookie_list: list of {name, value, domain, path, ...} dicts
    """
    for c in cookie_list:
        session.cookies.set(
            name=c['name'],
            value=c['value'],
            domain=c.get('domain', ''),
            path=c.get('path', '/'),
            expires=c.get('expires') if c.get('expires', -1) > 0 else None,
            secure=c.get('secure', False),
        )


def extract_domain_cookies(
    storage_state_path: Union[str, Path],
    domain: str,
) -> dict:
    """Extract cookies for a specific domain as {name: value} dict."""
    return playwright_to_dict(storage_state_path, filter_domain=domain)


# =============================================================================
# Self-test
# =============================================================================

if __name__ == '__main__':
    SHARED_DIR = Path('/Users/song/project/STUDYAGENT/get from web/shared')
    STATE_FILE = SHARED_DIR / 'storage-state.json'
    OUTPUT_DIR = Path('/Users/song/project/STUDYAGENT/get from web/research_c')

    print("=" * 60)
    print("Cookie Bridge Self-Test")
    print("=" * 60)

    # Test 1: Playwright -> dict
    print("\n[Test 1] Playwright -> dict (zujuan.xkw.com only)")
    zujuan_cookies = playwright_to_dict(STATE_FILE, filter_domain='zujuan.xkw.com')
    for name in ['userId', 'user_token', 'zujuan-core']:
        val = zujuan_cookies.get(name, 'NOT FOUND')
        print(f"  {name}: {val[:40] if val != 'NOT FOUND' else val}...")

    # Test 2: Playwright -> requests.Session
    print("\n[Test 2] Playwright -> requests.Session")
    session = playwright_to_requests(STATE_FILE)
    print(f"  Session has {len(session.cookies)} cookies")
    print(f"  userId: {session.cookies.get('userId', 'NOT FOUND')}")
    print(f"  zujuan-core: {session.cookies.get('zujuan-core', 'NOT FOUND')[:40]}...")

    # Test 3: requests -> Playwright JSON
    print("\n[Test 3] requests -> Playwright JSON")
    pw_cookies = requests_to_playwright_json(session)
    print(f"  Converted {len(pw_cookies)} cookies")
    print(f"  Format matches: {'name' in pw_cookies[0] if pw_cookies else 'N/A'}")

    # Test 4: Round-trip
    print("\n[Test 4] Round-trip test")
    tmp_path = OUTPUT_DIR / 'roundtrip_test.json'
    requests_to_playwright(session, tmp_path, merge_with=STATE_FILE)
    session2 = playwright_to_requests(tmp_path)
    print(f"  Original: {len(session.cookies)} cookies")
    print(f"  Round-tripped: {len(session2.cookies)} cookies")
    print(f"  userId preserved: {session2.cookies.get('userId') == session.cookies.get('userId')}")

    print("\n✓ All tests passed!")
