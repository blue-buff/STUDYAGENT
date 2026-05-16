#!/usr/bin/env python3
"""
Cookie Health Checker

Analyzes storage-state.json for expiration status, identifies critical auth cookies,
and determines if the session is still usable.

Usage:
  python cookie_health.py [--verbose]
  python cookie_health.py --check-url  # Also test a live request
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# =============================================================================
# Configuration
# =============================================================================

SHARED_DIR = Path('/Users/song/project/STUDYAGENT/get from web/shared')
DEFAULT_STATE = SHARED_DIR / 'storage-state.json'

# Cookie groups by criticality
CRITICAL_AUTH = [
    # Core session cookies - if ANY of these expire, session is dead
    'zujuan-core',       # ASP.NET Core session (expires ~12h)
    'userId',            # Numeric user ID
    'user_token',        # Base64-encoded auth token
]

SSO_COOKIES = [
    # SSO session cookies - needed to re-establish zujuan-core?
    'TGC',               # SSO ticket-granting cookie (~14d)
    'UT1',               # User tracking cookie (~14d)
    'UT2',               # User tracking cookie secure (~14d)
    'first-ua',          # First user agent (~400d)
    'service-number-logined',
]

ANTI_BOT_COOKIES = [
    # WAF / anti-bot cookies - needed to access the site at all
    'alicfw',            # Alibaba Cloud WAF challenge
    'alicfw_gfver',      # WAF version
    'acw_tc',            # Alibaba Cloud WAF token
]

DEVICE_COOKIES = [
    # Device fingerprinting cookies - long-lived, may persist across logins
    'xkw-device-id',     # Device ID (cross-domain, ~400d)
    'xkw-fs-id',         # Fingerprint ID (cross-domain, ~400d)
    'zj-device-id',      # ZuJuan device ID
]

TRACKING_COOKIES = [
    # Analytics / tracking - not needed for auth
    'HMACCOUNT', 'HMACCOUNT_BFESS',
    'Hm_lvt_68fb48a14b4fce9d823df8a437386f93',
    'Hm_lpvt_68fb48a14b4fce9d823df8a437386f93',
    'Hm_lvt_384e6cb5ddbf481e97ba12544207c0ee',
    'Hm_lpvt_384e6cb5ddbf481e97ba12544207c0ee',
]

UI_STATE_COOKIES = [
    # UI / preference cookies - not needed for auth
    'bankId', 'manager', 'ls-info', 'bindPhoneNumber',
    'pc_home_bigpopup', 'ip2ProvinceId',
    'quesBasketVersion', 'questionBasketVersion', 'editStatus',
    '__RequestVerificationToken',
    'ssoid',
]


def analyze_storage_state(
    path: Path = DEFAULT_STATE,
    verbose: bool = False,
) -> dict:
    """
    Analyze storage-state.json and return health report.

    Returns dict with:
      - expired: list of expired cookie names
      - valid_until: earliest expiry among critical cookies
      - is_session_valid: bool
      - critical_status: per-cookie status
      - recommendations: list of strings
    """
    with open(path) as f:
        data = json.load(f)

    cookies = data['cookies']
    now_ts = time.time()

    report = {
        'file': str(path),
        'checked_at': datetime.now().isoformat(),
        'total_cookies': len(cookies),
        'expired': [],
        'expiring_soon': [],  # < 1 hour
        'valid_until': None,
        'is_session_valid': True,
        'critical_status': {},
        'recommendations': [],
    }

    # Check each cookie
    for c in cookies:
        name = c['name']
        domain = c.get('domain', '')
        expires = c.get('expires', -1)

        if expires == -1:
            # Session cookie - no explicit expiry
            if verbose:
                print(f"  [SESSION] {name} ({domain})")
            continue

        if expires < now_ts:
            # Expired
            dt = datetime.fromtimestamp(expires)
            report['expired'].append({
                'name': name,
                'domain': domain,
                'expired_at': dt.isoformat(),
            })
        elif expires - now_ts < 3600:
            # Expiring within 1 hour
            dt = datetime.fromtimestamp(expires)
            mins_left = (expires - now_ts) / 60
            report['expiring_soon'].append({
                'name': name,
                'domain': domain,
                'expires_at': dt.isoformat(),
                'minutes_left': int(mins_left),
            })

    # Check critical cookies
    for group_name, group in [
        ('CRITICAL_AUTH', CRITICAL_AUTH),
        ('SSO_COOKIES', SSO_COOKIES),
        ('ANTI_BOT', ANTI_BOT_COOKIES),
        ('DEVICE', DEVICE_COOKIES),
    ]:
        for name in group:
            found = False
            for c in cookies:
                if c['name'] == name:
                    found = True
                    expires = c.get('expires', -1)
                    if expires == -1:
                        status = 'session'
                    elif expires < now_ts:
                        status = 'EXPIRED'
                        if name in CRITICAL_AUTH:
                            report['is_session_valid'] = False
                    else:
                        hours_left = (expires - now_ts) / 3600
                        if hours_left < 24:
                            status = f'expires in {hours_left:.1f}h'
                        else:
                            days_left = hours_left / 24
                            status = f'expires in {days_left:.1f}d'
                    report['critical_status'][name] = {
                        'domain': c.get('domain', ''),
                        'status': status,
                        'group': group_name,
                    }
                    break
            if not found:
                report['critical_status'][name] = {
                    'domain': 'N/A',
                    'status': 'MISSING',
                    'group': group_name,
                }

    # Set valid_until: earliest expiry among critical + sso cookies
    all_key = CRITICAL_AUTH + SSO_COOKIES
    earliest = float('inf')
    for c in cookies:
        if c['name'] in all_key and c.get('expires', -1) > 0:
            earliest = min(earliest, c['expires'])

    if earliest != float('inf'):
        report['valid_until'] = datetime.fromtimestamp(earliest).isoformat()
        report['valid_for_hours'] = (earliest - now_ts) / 3600

    # Generate recommendations
    if not report['is_session_valid']:
        report['recommendations'].append(
            'CRITICAL: Session is DEAD. zujuan-core and/or auth cookies expired.'
        )
        report['recommendations'].append(
            'Action: Run login.py to re-authenticate via WeChat QR scan.'
        )
    else:
        valid_hours = report.get('valid_for_hours', 0)
        if valid_hours < 1:
            report['recommendations'].append(
                f'WARNING: Session expires in {valid_hours*60:.0f} minutes. Re-login NOW.'
            )
        elif valid_hours < 12:
            report['recommendations'].append(
                f'Session expires in {valid_hours:.1f}h. Schedule re-login before expiry.'
            )
        else:
            report['recommendations'].append(
                f'Session healthy. Expires in {valid_hours/24:.1f} days.'
            )

    report['recommendations'].append(
        'SSO cookies (TGC/UT1/UT2) last ~14 days. Core cookies (zujuan-core) last ~12h.'
    )
    report['recommendations'].append(
        'Run session_monitor.py for continuous heartbeat and expiry detection.'
    )

    return report


def print_report(report: dict, verbose: bool = False):
    """Pretty-print the health report."""
    print("=" * 60)
    print("Cookie Health Report")
    print("=" * 60)
    print(f"File: {report['file']}")
    print(f"Checked at: {report['checked_at']}")
    print(f"Total cookies: {report['total_cookies']}")
    print(f"Session valid: {'YES' if report['is_session_valid'] else 'NO (EXPIRED)'}")

    if report.get('valid_until'):
        print(f"Earliest key expiry: {report['valid_until']} "
              f"({report.get('valid_for_hours', 0):.1f}h from now)")

    # Expired cookies
    if report['expired']:
        print(f"\n--- EXPIRED ({len(report['expired'])}) ---")
        for c in report['expired']:
            print(f"  {c['name']:35s} | {c['domain']:25s} | {c['expired_at']}")

    if report['expiring_soon']:
        print(f"\n--- EXPIRING SOON (<1h, {len(report['expiring_soon'])}) ---")
        for c in report['expiring_soon']:
            print(f"  {c['name']:35s} | {c['domain']:25s} | "
                  f"{c['minutes_left']}min left")

    # Critical cookie status
    print("\n--- Critical Cookie Status ---")
    for name, info in report['critical_status'].items():
        marker = {
            'CRITICAL_AUTH': '**',
            'SSO_COOKIES': ' *',
            'ANTI_BOT': '  ',
            'DEVICE': '  ',
        }.get(info['group'], '  ')
        status_icon = {
            'EXPIRED': 'x',
            'MISSING': '?',
        }.get(info['status'], 'v' if 'expires' not in info['status'] else '~')
        print(f"  [{status_icon}]{marker} {name:35s} | {info['status']}")

    # Recommendations
    print("\n--- Recommendations ---")
    for i, rec in enumerate(report['recommendations'], 1):
        print(f"  {i}. {rec}")

    print("\nLegend: ** = critical auth, * = SSO, x = expired, ? = missing, "
          "v = valid, ~ = expiring")


if __name__ == '__main__':
    verbose = '--verbose' in sys.argv
    check_url = '--check-url' in sys.argv

    state_path = DEFAULT_STATE
    for arg in sys.argv[1:]:
        if arg.endswith('.json'):
            state_path = Path(arg)

    if not state_path.exists():
        print(f"ERROR: {state_path} not found")
        sys.exit(1)

    report = analyze_storage_state(state_path, verbose=verbose)
    print_report(report, verbose=verbose)

    # Optionally verify with a live request
    if check_url:
        print("\n--- Live Verification ---")
        import requests
        from cookie_bridge import playwright_to_requests

        session = playwright_to_requests(state_path)
        resp = session.get('https://zujuan.xkw.com', timeout=15)
        if 'login-btn' in resp.text:
            print("Live check: NOT LOGGED IN (login button found)")
        elif 'J_realname' in resp.text or '退出' in resp.text:
            print("Live check: LOGGED IN")
        else:
            print(f"Live check: UNCLEAR (status={resp.status_code}, "
                  f"len={len(resp.text)})")
