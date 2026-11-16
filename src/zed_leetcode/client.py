"""Small adapter for the undocumented LeetCode website GraphQL interface."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from typing import Any

from .workspace import WorkspaceError

LIST = '''query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
  problemsetQuestionList(categorySlug: $categorySlug, limit: $limit, skip: $skip, filters: $filters) {
    total questions { questionFrontendId: frontendQuestionId title translatedTitle: titleCn titleSlug difficulty }
  }
}'''
DETAIL = '''query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) { questionId questionFrontendId title translatedTitle titleSlug difficulty
    content translatedContent metaData codeSnippets { langSlug code } sampleTestCase }
}'''


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ('p', 'pre', 'br', 'li', 'h2', 'h3'):
            self.parts.append('\n')

    def handle_endtag(self, tag: str) -> None:
        if tag in ('p', 'pre', 'li'):
            self.parts.append('\n')

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_text(content: str) -> str:
    parser = TextExtractor()
    parser.feed(content)
    return re.sub(r'\n{3,}', '\n\n', ''.join(parser.parts)).strip()


def extract_cases(description: str, params: list[str]) -> list[dict[str, Any]]:
    """Extract only unambiguous single-line JSON input/output examples."""
    cases = []
    for match in re.finditer(r'(?:输入|Input)\s*[:：]\s*([^\n]+)\n\s*(?:输出|Output)\s*[:：]\s*([^\n]+)', description, re.IGNORECASE):
        raw_args, raw_output = match.groups()
        try:
            decoder = json.JSONDecoder()
            values = {}
            pos = 0
            while pos < len(raw_args):
                found = re.match(r'\s*,?\s*([A-Za-z_][A-Za-z_0-9]*)\s*=\s*', raw_args[pos:])
                if not found:
                    raise ValueError('unsupported input')
                pos += found.end()
                value, end = decoder.raw_decode(raw_args, pos)
                values[found.group(1)] = value
                pos = end
            if set(values) != set(params):
                continue
            expected = json.loads(raw_output.strip())
            cases.append({'args': [values[p] for p in params], 'expected': expected})
        except (ValueError, TypeError):
            continue
    return cases


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


class LeetCodeClient:
    def __init__(self, site: str) -> None:
        self.site = site

    def graphql(self, query: str, variables: dict[str, Any], name: str) -> dict[str, Any]:
        body = json.dumps({'query': query, 'variables': variables, 'operationName': name}).encode()
        request = urllib.request.Request(self.site + '/graphql/', data=body, headers={'Content-Type': 'application/json', 'User-Agent': 'zed-leetcode/0.1'})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                result = json.load(response)
        except urllib.error.HTTPError as e:
            raise WorkspaceError(f'LeetCode HTTP {e.code}: request rejected; check access or try again later.') from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            raise WorkspaceError(f'LeetCode request failed ({type(e).__name__}); check network and try again.') from None
        if not isinstance(result, dict) or result.get('errors') or not isinstance(result.get('data'), dict):
            raise WorkspaceError('LeetCode GraphQL rejected the request or changed its response; see docs/api-research.md.')
        return result['data']

    def search(self, keyword: str, difficulty: str | None) -> list[dict[str, Any]]:
        if self.site != 'https://leetcode.cn':
            raise WorkspaceError('Online search is currently supported only on leetcode.cn.')
        filters: dict[str, str] = {}
        if keyword:
            filters['searchKeywords'] = keyword
        if difficulty:
            filters['difficulty'] = difficulty.upper()
        result = self.graphql(LIST, {'categorySlug': '', 'limit': 50, 'skip': 0, 'filters': filters}, 'problemsetQuestionList')
        page = result.get('problemsetQuestionList')
        if not isinstance(page, dict) or not isinstance(page.get('questions'), list):
            raise WorkspaceError('Unexpected question list response.')
        return [{**item, 'questionFrontendId': item.get('questionFrontendId', item.get('frontendQuestionId')), 'translatedTitle': item.get('translatedTitle', item.get('titleCn'))} for item in page['questions']]

    def fetch(self, identifier: str) -> dict[str, Any]:
        slug = identifier
        if identifier.isdigit():
            items = self.search(identifier, None)
            matches = [x for x in items if str(x.get('questionFrontendId')) == identifier]
            if not matches:
                raise WorkspaceError(f'Problem {identifier} not found in search results; try its slug.')
            slug = matches[0]['titleSlug']
        if not re.fullmatch(r'[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*', slug):
            raise WorkspaceError('Invalid problem slug.')
        q = self.graphql(DETAIL, {'titleSlug': slug}, 'questionData').get('question')
        if not q or not (q.get('translatedContent') or q.get('content')):
            raise WorkspaceError('Question unavailable, missing content, or requires access; no bypass attempted.')
        try:
            meta = json.loads(q['metaData'])
            name = meta['name']
            params = [p['name'] for p in meta['params']]
            snippets = q.get('codeSnippets') or []
            template = next((s['code'] for s in snippets if s.get('langSlug') == 'python3'), None)
            description = html_text(q.get('translatedContent') or q['content'])
            return {'id': q['questionFrontendId'], 'slug': q['titleSlug'], 'title': q.get('translatedTitle') or q['title'],
                    'difficulty': q['difficulty'], 'method': name, 'params': params, 'question_id': str(q['questionId']),
                    'description': description,
                    'template': template, 'cases': extract_cases(description, params)}
        except (KeyError, TypeError, ValueError) as e:
            raise WorkspaceError('Question metadata is missing or unsupported (design and interactive problems are not supported).') from e

    def submit(self, slug: str, code: str, question_id: str | None = None, timeout: float = 60) -> dict[str, str]:
        if self.site != 'https://leetcode.cn':
            raise WorkspaceError('Online submission currently supports only leetcode.cn.')
        if not re.fullmatch(r'[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*', slug):
            raise WorkspaceError('Invalid problem slug.')
        from .auth import get_credentials
        session, csrf = get_credentials()
        if any(not re.fullmatch(r'[\x21-\x3a\x3c-\x7e]+', value) for value in (session, csrf)):
            raise WorkspaceError('Invalid authentication environment variables.')
        if not question_id:
            q = self.graphql(DETAIL, {'titleSlug': slug}, 'questionData').get('question')
            question_id = str(q.get('questionId', '')) if isinstance(q, dict) else ''
        if not str(question_id).isdigit():
            raise WorkspaceError('Missing or invalid internal question ID; fetch the problem again.')
        headers = {'Content-Type': 'application/json', 'User-Agent': 'zed-leetcode/0.1',
                   'Cookie': f'LEETCODE_SESSION={session}; csrftoken={csrf}', 'x-csrftoken': csrf,
                   'Origin': self.site, 'Referer': f'{self.site}/problems/{slug}/'}
        opener = urllib.request.build_opener(NoRedirect())

        def request(url: str, body: dict[str, Any] | None, request_timeout: float) -> dict[str, Any]:
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(url, data=data, headers=headers)
            try:
                with opener.open(req, timeout=request_timeout) as response:
                    result = json.load(response)
            except urllib.error.HTTPError as e:
                raise WorkspaceError(f'LeetCode returned HTTP {e.code}; authentication, permissions, or access restrictions may apply.') from None
            except (urllib.error.URLError, TimeoutError, OSError, ValueError):
                raise WorkspaceError('LeetCode request failed or returned invalid JSON; do not retry a submission until its status is checked.') from None
            if not isinstance(result, dict):
                raise WorkspaceError('Unexpected LeetCode response; submission status is unknown.')
            return result

        deadline = time.monotonic() + timeout
        result = request(f'{self.site}/problems/{slug}/submit/',
                         {'lang': 'python3', 'question_id': int(question_id), 'typed_code': code, 'test_mode': False, 'judge_type': 'large'}, min(15, timeout))
        submission_id = str(result.get('submission_id', ''))
        if not submission_id.isdigit():
            raise WorkspaceError('No submission ID returned; submission may have failed or the interface changed. Check the website before retrying.')
        print(f'Submission ID: {submission_id}', flush=True)
        while time.monotonic() < deadline:
            time.sleep(min(2, max(0, deadline - time.monotonic())))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                result = request(f'{self.site}/submissions/detail/{submission_id}/check/', None, min(15, remaining))
            except WorkspaceError as e:
                raise WorkspaceError(f'Could not check submission {submission_id}; its result is unknown. {e}') from None
            if result.get('state') == 'SUCCESS':
                status = result.get('status_msg')
                if not isinstance(status, str) or not re.fullmatch(r'[A-Za-z0-9 _-]{1,80}', status) or session in status or csrf in status:
                    raise WorkspaceError(f'Submission {submission_id} completed but returned an unrecognized status.')
                def safe_metric(value: Any) -> str:
                    value = str(value or '')
                    return value if re.fullmatch(r'[0-9. A-Za-z/%-]{1,40}', value) and session not in value and csrf not in value else ''
                return {'submission_id': submission_id, 'status': status,
                        'runtime': safe_metric(result.get('status_runtime')), 'memory': safe_metric(result.get('status_memory'))}
            if result.get('state') not in ('PENDING', 'STARTED', 'RUNNING'):
                raise WorkspaceError(f'Submission {submission_id} returned an unknown state; check the website.')
        raise WorkspaceError(f'Timed out waiting for submission {submission_id}; its result is unknown. Check the website before retrying.')
