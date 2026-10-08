"""Small requests-only event poller. No daily crawler/browser/LLM imports."""
import argparse
import base64
import copy
import json
import os
import re
import time
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from scripts.teams_notifier import send_teams_message
except ModuleNotFoundError:
    from teams_notifier import send_teams_message

LIST_URL = ('https://gall.dcinside.com/mgallery/board/lists/'
            '?id=mvnogallery&sort_type=N&search_head=120&page={}')
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                         'AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
           'Referer': 'https://gall.dcinside.com/mgallery/board/lists/?id=mvnogallery',
           'Accept-Language': 'ko-KR,ko;q=0.9',
           'Accept': 'text/html,application/xhtml+xml'}


def get_html(url):
    for attempt in range(3):
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            return response.text
        except requests.RequestException:
            if attempt == 2:
                raise RuntimeError('디시 크롤링 실패: 상태를 보존합니다.') from None
            time.sleep(2 ** attempt)


def parse_list(html):
    soup = BeautifulSoup(html, 'html.parser')
    # Validate the selected filter, not just the existence of a generic table.
    selected = soup.select_one('select[name="search_head"] option[selected], '
                               '.subject_list .sel a, .subject_list .on a')
    if selected and selected.get('value') and selected['value'] != '120':
        raise RuntimeError('행사 말머리 필터 불일치')
    table = soup.select_one('table.gall_list')
    if table is None:
        raise RuntimeError('디시 목록 없음/차단/구조 변경')
    posts = []
    for row in table.select('tr.ub-content.us-post'):
        number = row.select_one('.gall_num')
        if row.get('data-type') == 'icon_notice' or not number or not number.get_text(strip=True).isdigit():
            continue
        subject = row.select_one('.gall_subject')
        # DC repeats the label in a hidden tooltip and appends a NEW emoji.
        label = ''.join(subject.find_all(string=True, recursive=False)).strip() if subject else ''
        if label in {'공지', 'AD', '설문', '이벤트'}:
            continue
        if not re.fullmatch(r'행사(?:🆕\ufe0f?)?', label):
            raise RuntimeError('행사 목록에 다른 말머리가 포함되었습니다.')
        link = row.select_one('.gall_tit > a[href*="/board/view/"]')
        if not link:
            raise RuntimeError('게시글 링크 구조 변경')
        parsed = urlparse(urljoin('https://gall.dcinside.com', link['href']))
        query = parse_qs(parsed.query)
        post_id = number.get_text(strip=True)
        if (parsed.hostname != 'gall.dcinside.com' or parsed.path != '/mgallery/board/view/'
                or query.get('id') != ['mvnogallery'] or query.get('no') != [post_id]):
            raise RuntimeError('게시글 ID/URL 불일치')
        posts.append({'id': post_id, 'title': link.get_text(' ', strip=True),
                      'url': f'https://gall.dcinside.com/mgallery/board/view/?id=mvnogallery&no={post_id}'})
    # Empty is valid only when DC explicitly renders its empty-list marker.
    if not posts and not table.select_one('.no_data'):
        raise RuntimeError('행사 목록을 확인할 수 없습니다.')
    ids = [int(p['id']) for p in posts]
    if ids != sorted(ids, reverse=True) or len(ids) != len(set(ids)):
        raise RuntimeError('목록 정렬/중복 이상')
    return posts


def summarize(html):
    soup = BeautifulSoup(html, 'html.parser')
    body = soup.select_one('div.write_div')
    if body is None:
        raise RuntimeError('본문 없음/차단/삭제/구조 변경')
    for node in body.select('script, style'):
        node.decompose()
    lines = [re.sub(r'\s+', ' ', line).strip() for line in body.get_text('\n', strip=True).splitlines()]
    lines = [line for line in lines if line and not re.fullmatch(r'-?\s*dc\s+(official\s+)?app', line, re.I)]
    if not lines:
        return '이미지 중심 게시글입니다. 행사 조건은 원문 이미지를 확인하세요.' if body.find('img') else '텍스트 본문이 없습니다. 원문을 확인하세요.'
    # Extractive summary: retain original price/duration/benefit facts, no invention.
    important = [i for i, line in enumerate(lines) if re.search(r'\d|요금|할인|증정|사은|기간|조건|개통|혜택', line)]
    chosen = sorted(set([0] + important[:3]))
    return ' / '.join(lines[i][:180] for i in chosen)[:600]


def validate_state(state):
    if (not isinstance(state, dict) or state.get('version') != 1
            or type(state.get('high_water')) is not int or state['high_water'] < 0
            or not isinstance(state.get('seen_ids'), list)
            or any(not isinstance(i, str) or not i.isdigit() for i in state['seen_ids'])):
        raise RuntimeError('중복 방지 상태 손상: 덮어쓰지 않습니다.')
    return state


class GitHubState:
    """Durable state in a dedicated branch; contents SHA provides optimistic locking."""
    branch = 'dc-event-state'
    path = 'state/dc_events.json'

    def __init__(self):
        repo = os.environ['GITHUB_REPOSITORY']
        self.api = f'https://api.github.com/repos/{repo}'
        self.headers = {'Authorization': 'Bearer ' + os.environ['GITHUB_TOKEN'],
                        'Accept': 'application/vnd.github+json'}
        self.sha = None

    def request(self, method, path, **kwargs):
        # Do not print raw errors: they can include authorization/webhook details.
        try:
            return requests.request(method, self.api + path, headers=self.headers,
                                    timeout=20, **kwargs)
        except requests.RequestException:
            raise RuntimeError('GitHub 상태 저장소 연결 실패') from None

    def load(self):
        response = self.request('GET', f'/contents/{self.path}', params={'ref': self.branch})
        if response.status_code == 404:
            branch = self.request('GET', f'/git/ref/heads/{self.branch}')
            if branch.status_code not in (200, 404):
                raise RuntimeError('상태 브랜치 확인 실패')
            return None  # Missing state always re-baselines without historical alerts.
        if response.status_code != 200:
            raise RuntimeError('중복 방지 상태 읽기 실패')
        try:
            data = response.json()
            self.sha = data['sha']
            return validate_state(json.loads(base64.b64decode(data['content'])))
        except (ValueError, KeyError, TypeError):
            raise RuntimeError('중복 방지 상태 손상') from None

    def save(self, state):
        validate_state(state)
        if self.sha is None:
            branch = self.request('GET', f'/git/ref/heads/{self.branch}')
            if branch.status_code == 404:
                result = self.request('POST', '/git/refs', json={
                    'ref': f'refs/heads/{self.branch}', 'sha': os.environ['GITHUB_SHA']})
                if result.status_code != 201:
                    raise RuntimeError('상태 브랜치 생성 실패')
            elif branch.status_code != 200:
                raise RuntimeError('상태 브랜치 확인 실패')
        payload = {'message': 'chore: checkpoint DC event notifications', 'branch': self.branch,
                   'content': base64.b64encode(json.dumps(state, ensure_ascii=False).encode()).decode()}
        if self.sha:
            payload['sha'] = self.sha
        result = self.request('PUT', f'/contents/{self.path}', json=payload)
        if result.status_code not in (200, 201):
            raise RuntimeError('상태 저장 실패: 재실행 시 중복 가능, 실행 로그 확인 필요')
        self.sha = result.json()['content']['sha']


def escape(text):
    return re.sub(r'([\\\[\]*_`<>])', r'\\\1', text)


def run(store, fetch=get_html, send=send_teams_message, dry_run=False, max_pages=10):
    original = store.load()
    first = parse_list(fetch(LIST_URL.format(1)))
    if original is None:
        baseline = {'version': 1, 'high_water': max((int(p['id']) for p in first), default=0), 'seen_ids': []}
        if not dry_run:
            store.save(baseline)
        print('첫 실행: 현재 게시글을 기준선으로 기록, 과거글 알림 생략')
        return
    state = copy.deepcopy(validate_state(original))
    posts, page_ids = {}, set()
    rows = first
    for page in range(1, max_pages + 1):
        key = tuple(p['id'] for p in rows)
        if key in page_ids:
            raise RuntimeError('목록 페이지 반복: 상태 보존')
        page_ids.add(key)
        for post in rows:
            if int(post['id']) > state['high_water']:
                posts[post['id']] = post
        if not rows or any(int(p['id']) <= state['high_water'] for p in rows):
            break
        if page == max_pages:
            raise RuntimeError('목록 페이지 한도 초과: 상태 보존')
        rows = parse_list(fetch(LIST_URL.format(page + 1)))
    pending = sorted((p for p in posts.values() if p['id'] not in state['seen_ids']),
                     key=lambda p: int(p['id']))
    # Fetch ALL details first: any crawl failure leaves seen state untouched.
    for post in pending:
        post['summary'] = summarize(fetch(post['url']))
    for start in range(0, len(pending), 5):
        batch = pending[start:start + 5]
        message = '**[디시 알뜰폰 갤러리 새 행사글]**\n' + '\n\n'.join(
            f"**{escape(p['title'][:200])}**\n{escape(p['summary'])}\n[원문]({p['url']})" for p in batch)
        if dry_run:
            print(message)
            continue
        if send(message, attempts=3) is not True:
            raise RuntimeError('Teams 전송 성공을 확인하지 못했습니다.')
        state['seen_ids'].extend(p['id'] for p in batch)
        store.save(state)  # Confirmed earlier batches survive later send failures.
    if not dry_run and posts:
        state['high_water'] = max(int(i) for i in posts)
        state['seen_ids'] = []  # IDs <= high_water remain permanently suppressed.
        store.save(state)
    print(f'새 행사글 {len(pending)}건 처리' + (' (dry run: 전송/저장 생략)' if dry_run else ''))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        run(GitHubState(), dry_run=args.dry_run)
    except Exception as error:
        # Print only our sanitized errors. Never raw requests exceptions.
        print(str(error) if isinstance(error, RuntimeError) else '행사 모니터링 실패: 상태 보존')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
