"""Opt-in isolated browser login and macOS Keychain credential storage."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from .workspace import WorkspaceError

SITE = 'https://leetcode.cn'
SERVICE = 'zed-leetcode/leetcode.cn'
ACCOUNT = 'session'
QUERY = 'query CurrentUser { userStatus { isSignedIn username } }'


def backend() -> Any:
    if sys.platform != 'darwin':
        raise WorkspaceError('Keychain login is currently supported only on macOS; use environment variables on other systems.')
    try:
        import keyring
        from keyring.backends.macOS import Keyring
        store = keyring.get_keyring()
    except ImportError:
        raise WorkspaceError('Login dependencies missing. Install zed-leetcode[login].') from None
    if not isinstance(store, Keyring):
        raise WorkspaceError('macOS Keychain backend unavailable; refusing to store credentials in another backend.')
    return store


def get_credentials() -> tuple[str, str]:
    session, csrf = os.environ.get('LEETCODE_SESSION', ''), os.environ.get('LEETCODE_CSRF_TOKEN', '')
    if session or csrf:
        if not session or not csrf:
            raise WorkspaceError('Set both LEETCODE_SESSION and LEETCODE_CSRF_TOKEN, or unset both to use Keychain.')
        return session, csrf
    try:
        raw = backend().get_password(SERVICE, ACCOUNT)
    except WorkspaceError:
        raise
    except Exception:
        raise WorkspaceError('Could not access macOS Keychain.') from None
    if not raw:
        raise WorkspaceError('Not logged in. Run lc login or set LEETCODE_SESSION and LEETCODE_CSRF_TOKEN.')
    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict) or not isinstance(obj.get('session'), str) or not isinstance(obj.get('csrf'), str) or not obj['session'] or not obj['csrf']:
            raise ValueError('invalid credentials')
        return obj['session'], obj['csrf']
    except (ValueError, TypeError):
        raise WorkspaceError('Stored login is invalid; run lc login again.') from None


def save_credentials(session: str, csrf: str) -> None:
    try:
        backend().set_password(SERVICE, ACCOUNT, json.dumps({'session': session, 'csrf': csrf}))
    except WorkspaceError:
        raise
    except Exception:
        raise WorkspaceError('Could not save login to macOS Keychain.') from None


def logout() -> None:
    try:
        store = backend()
        if store.get_password(SERVICE, ACCOUNT):
            store.delete_password(SERVICE, ACCOUNT)
    except WorkspaceError:
        raise
    except Exception:
        raise WorkspaceError('Could not remove login from macOS Keychain.') from None


def verify(session: str, csrf: str) -> bool:
    from .client import NoRedirect
    request = urllib.request.Request(SITE + '/graphql/', data=json.dumps({'query': QUERY, 'operationName': 'CurrentUser', 'variables': {}}).encode(), headers={'Content-Type': 'application/json', 'Cookie': f'LEETCODE_SESSION={session}; csrftoken={csrf}', 'x-csrftoken': csrf, 'Origin': SITE, 'Referer': SITE + '/'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=10) as response:
            result = json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise WorkspaceError('Unable to verify login with LeetCode; no credentials were saved.') from None
    if not isinstance(result, dict) or not isinstance(result.get('data'), dict):
        raise WorkspaceError('Login verification returned an unexpected response; no credentials were saved.')
    status = result['data'].get('userStatus')
    if not isinstance(status, dict) or not isinstance(status.get('isSignedIn'), bool):
        raise WorkspaceError('Login verification returned an unexpected response; no credentials were saved.')
    return status['isSignedIn']


def login(timeout: float = 300) -> None:
    backend()  # Fail before opening a browser if secure storage is unavailable.
    try:
        from playwright.sync_api import Error as PlaywrightError, sync_playwright
    except ImportError:
        raise WorkspaceError('Login dependencies missing. Install zed-leetcode[login].') from None
    print('Opening an isolated browser. Log in to leetcode.cn there; this window has no existing browser profile.', flush=True)
    print('Waiting up to 5 minutes. Close the window or press Ctrl-C to cancel.', flush=True)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chrome', headless=False)
            try:
                context = browser.new_context(accept_downloads=False)
                page = context.new_page()
                page.goto(SITE + '/accounts/login/', wait_until='domcontentloaded', timeout=30000)
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    if page.is_closed():
                        raise WorkspaceError('Login cancelled; no credentials were saved.')
                    cookies = context.cookies([SITE])
                    values = {c['name']: c['value'] for c in cookies if c.get('name') in ('LEETCODE_SESSION', 'csrftoken') and c.get('domain', '').lstrip('.') == 'leetcode.cn'}
                    session, csrf = values.get('LEETCODE_SESSION'), values.get('csrftoken')
                    if session and csrf and verify(session, csrf):
                        save_credentials(session, csrf)
                        print('Login verified and saved to macOS Keychain.')
                        return
                    page.wait_for_timeout(2000)
                raise WorkspaceError('Login timed out; no credentials were saved.')
            finally:
                browser.close()
    except PlaywrightError:
        raise WorkspaceError('Browser launch or login failed. Install Google Chrome and check display access; no credentials were saved.') from None
