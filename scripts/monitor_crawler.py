import os
from urllib.parse import urljoin
try:
    from scripts.brand_rules import BRANDS, matches_brand
except ModuleNotFoundError:
    from brand_rules import BRANDS, matches_brand
import sys
import json
import time
import random
import datetime
import pytz
import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
from collections import Counter

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

DESKTOP_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
# 2026-08-29부터 뽐뿌가 User-Agent만 있는 요청(순수 requests)까지 403으로 막기 시작함.
# 실제 브라우저가 항상 같이 보내는 나머지 헤더가 없는 것만으로 봇 판정하는 WAF 룰을 의심해
# 아래처럼 완전한 헤더셋을 갖춰서 보낸다.
PPOMPPU_HEADERS = {
    "User-Agent": DESKTOP_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.ppomppu.co.kr/zboard/zboard.php?id=phone",
    "Connection": "keep-alive",
}

# --- [설정 및 입력값 처리] ---
COPILOT_WEBHOOK_URL = os.environ.get("COPILOT_WEBHOOK_URL")
TEST_MODE = os.environ.get("TEST_MODE", "false").lower() == "true"

TZ_KST = pytz.timezone('Asia/Seoul')
NOW = datetime.datetime.now(TZ_KST)

# [날짜 설정 로직]
if len(sys.argv) > 1 and sys.argv[1]:
    target_date_str = sys.argv[1]
    print(f"🛠️ 사용자 지정 날짜 수집: {target_date_str}")
else:
    target_date_obj = NOW - datetime.timedelta(days=1)
    target_date_str = target_date_obj.strftime('%Y-%m-%d')
    print(f"📅 자동 설정 (어제 날짜): {target_date_str}")

# Reject malformed/future dates before requests or file writes.
target_date = datetime.datetime.strptime(target_date_str, '%Y-%m-%d').date()
if target_date > NOW.date():
    raise ValueError('미래 날짜는 수집할 수 없습니다.')
TARGET_DATE = target_date.isoformat()
MAX_PAGES = int(os.environ.get('MAX_PAGES', '300'))
if MAX_PAGES < 1:
    raise ValueError('MAX_PAGES must be positive')

# --- [1. 브라우저 설정] ---
def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--lang=ko_KR")
    chrome_options.add_argument(f"user-agent={DESKTOP_UA}")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(30)
    return driver

# --- Complete date-bounded collection; failure never becomes a zero count. ---
def _number(text):
    match = re.search(r'\d[\d,]*', text or '')
    return int(match.group().replace(',', '')) if match else 0


def _get_html(url):
    for attempt in range(3):
        try:
            response = requests.get(url, headers=PPOMPPU_HEADERS, timeout=15)
            response.raise_for_status()
            return response.text
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def _list_rows(html, source):
    soup = BeautifulSoup(html, 'html.parser')
    result = []
    rows = soup.select('tr.ub-content.us-post') if source == 'dc' else soup.find_all('tr')
    for row in rows:
        # Ignore layout wrapper rows and pinned announcements, which recur on every page.
        if row.find('tr') is not None:
            continue
        row_classes = ' '.join(row.get('class', []))
        if re.search(r'notice|announcement', row_classes, re.I):
            continue
        if row.get('data-type') == 'icon_notice':
            continue
        subject = row.select_one('.gall_subject')
        if subject and subject.get_text(strip=True) in {'AD', '설문', '공지', '이벤트'}:
            continue
        link = row.select_one('.gall_tit > a') if source == 'dc' else row.select_one('a[href*="view.php"]')
        if not link or not link.get('href'):
            continue
        if source == 'dc':
            date_tag = row.select_one('.gall_date')
            date_text = date_tag.get('title', '') if date_tag else ''
            match = re.search(r'\d{4}-\d{2}-\d{2}', date_text)
            date = match.group() if match else ''
            title_tag = link
            views_tag, comments_tag = row.select_one('.gall_count'), row.select_one('.reply_num')
            base = 'https://gall.dcinside.com'
        else:
            date_tag = row.find('td', title=re.compile(r'\d{2}[./]\d{2}[./]\d{2}'))
            date_text = date_tag.get('title', '') if date_tag else row.get_text(' ', strip=True)
            match = re.search(r'(\d{2})[./](\d{2})[./](\d{2})', date_text)
            date = f'20{match[1]}-{match[2]}-{match[3]}' if match else ''
            if not date and re.search(r'\b\d{2}:\d{2}\b', date_text):
                date = NOW.date().isoformat()
            title_tag = row.select_one('font.list_title') or link
            views_tag = row.select_one('.baseList-views')
            comments_tag = row.select_one('.baseList-c') or row.select_one('.list_comment2')
            base = 'https://www.ppomppu.co.kr/zboard/'
        if not date:
            raise RuntimeError(f'{source}: 게시글 날짜를 읽지 못했습니다.')
        title = title_tag.get_text(' ', strip=True)
        views = _number(views_tag.get_text()) if views_tag else 0
        if source == 'ppomppu' and views_tag is None:
            cells = row.find_all('td', recursive=False)
            views = _number(cells[-1].get_text()) if cells else 0
        result.append({'date': date, 'source': source, 'title': title,
                       'link': urljoin(base, link['href']), 'views': views,
                       'comments': _number(comments_tag.get_text()) if comments_tag else 0})
    return result


def _collect_posts(driver, source):
    base = ('https://www.ppomppu.co.kr/zboard/zboard.php?id=phone&page={}'
            if source == 'ppomppu' else
            'https://gall.dcinside.com/mgallery/board/lists/?id=mvnogallery&page={}')
    posts, seen_pages = {}, set()
    for page in range(1, MAX_PAGES + 1):
        url = base.format(page)
        if source == 'ppomppu':
            html = _get_html(url)
        else:
            driver.get(url)
            time.sleep(1.5)
            html = driver.page_source
        rows = _list_rows(html, source)
        if not rows:
            # Empty HTML, blocked pages and selector failures are not evidence of zero activity.
            raise RuntimeError(f'{source} p{page}: 목록 없음/구조 변경/차단. 결과 저장 중단.')
        page_key = tuple(sorted({row['link'] for row in rows}))
        if page_key in seen_pages:
            raise RuntimeError(f'{source}: 페이지 반복으로 수집 완전성을 확인할 수 없습니다.')
        seen_pages.add(page_key)
        for row in rows:
            if row['date'] == TARGET_DATE:
                posts[row['link']] = {k: v for k, v in row.items() if k != 'date'}
        # All dated rows precede the requested day. Do not stop on an old pinned notice.
        if max(row['date'] for row in rows) < TARGET_DATE:
            print(f'{source}: {len(posts)}건, 대상 날짜 끝 확인 (p{page})')
            return list(posts.values())
        time.sleep(0.5)
    raise RuntimeError(f'{source}: {MAX_PAGES}페이지 한도 도달, 불완전 수집. 기존 데이터 보존.')


def get_ppomppu_posts(driver):
    return _collect_posts(driver, 'ppomppu')


def get_dc_posts(driver):
    return _collect_posts(driver, 'dc')


# --- [4. 상세 페이지 크롤러: 본문/댓글] ---
def _clean_text(elem):
    """BeautifulSoup 엘리먼트에서 script/style 제거 후 텍스트만 정리해서 반환."""
    if not elem:
        return ""
    for tag in elem.select('script, style'):
        tag.decompose()
    return re.sub(r'\s+', ' ', elem.get_text(separator=' ', strip=True)).strip()


_JUNK_TEXT_RE = re.compile(r'dc\s*(official\s*)?app', re.IGNORECASE)


def _fallback_largest_block(soup, min_len=100):
    """알려진 셀렉터가 안 맞을 때 텍스트가 가장 많은 td/div를 본문으로 추정하는 최후 수단.
    '- dc App' 같은 앱 서명/배지처럼 뻔한 잡음 텍스트는 후보에서 제외한다."""
    best, best_len = None, min_len
    for c in soup.select('td, div'):
        if c.find(['td', 'div']):  # 자식에 td/div가 있으면 컨테이너일 확률이 높아 스킵
            continue
        text = c.get_text(strip=True)
        if _JUNK_TEXT_RE.search(text):
            continue
        if len(text) > best_len:
            best, best_len = c, len(text)
    return best


def _extract_ppomppu_comments(page_source, limit=10):
    """
    뽐뿌는 댓글을 DOM에 바로 안 심어두고, 페이지 안 <script>의
    `var initialCommentData = {...};` JS 변수(JSON)로 내려준다.
    (실제 저장된 게시글 HTML로 확인함 - DOM 셀렉터로는 애초에 못 찾는 구조였음)
    각 댓글의 본문은 'memo' 필드에 HTML(<p>...)로 들어있어서 태그를 벗겨내고,
    대댓글은 'sub_cmt'에 재귀적으로 중첩되어 있어서 같이 순회한다.
    """
    m = re.search(r'var initialCommentData\s*=\s*(\{.*?\});', page_source, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return []

    comments = []

    def walk(nodes):
        for c in nodes:
            memo_html = c.get('memo', '')
            text = BeautifulSoup(memo_html, 'html.parser').get_text(separator=' ', strip=True)
            if text:
                comments.append(text[:200])
            if c.get('sub_cmt'):
                walk(c['sub_cmt'])

    walk(data.get('comments', []))
    return comments[:limit]


def get_ppomppu_detail(driver, url):
    """
    뽐뿌 게시글 상세 페이지에서 본문/댓글을 가져온다.
    - 본문: td.han (실제 저장된 게시글 HTML로 검증 완료)
    - 댓글: DOM이 아니라 initialCommentData JS 변수(JSON)에서 파싱 (_extract_ppomppu_comments 참고)
    """
    content, comments = "", []
    try:
        resp = requests.get(url, headers=PPOMPPU_HEADERS, timeout=15)
        resp.raise_for_status()
        time.sleep(random.uniform(0.5, 1.0))
        page_source = resp.text
        soup = BeautifulSoup(page_source, 'html.parser')

        body_elem = soup.select_one('td.han') or _fallback_largest_block(soup)
        content = _clean_text(body_elem)[:1500]

        comments = _extract_ppomppu_comments(page_source)

        if not content:
            print(f"  ⚠️ [ppomppu] 본문 추출 실패 (셀렉터 확인 필요): {url}")
        # 댓글 0건은 실제로 무플인 경우도 있으니 진짜 댓글수(list 페이지에서 이미 알고 있음)와
        # 비교해서 호출부에서 이상 여부를 판단하는 게 정확함. 여기서는 파싱 실패 여부만 로그.
        if not comments and 'initialCommentData' not in page_source:
            print(f"  ⚠️ [ppomppu] initialCommentData 자체가 없음 (페이지 구조 변경 의심): {url}")
    except Exception as e:
        print(f"Err Ppomppu detail {url}: {e}")
    return content, comments


def get_dc_detail(driver, url):
    """
    디시인사이드 게시글 상세 페이지에서 본문/댓글을 가져온다.
    - 본문: div.write_div (실제 저장된 게시글 HTML로 검증 완료).
      이미지만 있는 글은 write_div는 있어도 텍스트가 없는 게 정상이라 content가 빈 문자열일 수 있음 -> 버그 아님.
    - 댓글: ul.cmt_list p.usertxt (실제 저장된 게시글 HTML로 16개 정상 추출 확인)
    """
    content, comments = "", []
    try:
        driver.get(url)
        time.sleep(random.uniform(2.0, 3.0))
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        body_elem = soup.select_one('div.write_div') or soup.select_one('.writing_view_box .write_div')
        if body_elem is not None:
            content = _clean_text(body_elem)[:1500]
        else:
            # 알려진 셀렉터가 아예 안 걸린 경우에만 최후 수단으로 폴백 (이미지 전용 글과 구분하기 위함)
            content = _clean_text(_fallback_largest_block(soup))[:1500]
            if not content:
                print(f"  ⚠️ [dc] 본문 추출 실패 (셀렉터 확인 필요): {url}")

        comment_nodes = (soup.select('ul.cmt_list p.usertxt')
                          or soup.select('.cmt_txtbox')
                          or soup.select('.reply_info .usertxt'))
        for node in comment_nodes[:10]:
            text = _clean_text(node)[:200]
            if text:
                comments.append(text)

        if not comments:
            print(f"  ⚠️ [dc] 댓글 추출 실패 (0건이거나 셀렉터 확인 필요): {url}")
    except Exception as e:
        print(f"Err DC detail {url}: {e}")
    return content, comments


# --- [5. 분석 및 알림 로직] ---
def extract_top_keywords(df):
    if df.empty: return []
    all_titles = " ".join(df['title'].tolist())
    all_titles = re.sub(r'[^\w\s]', ' ', all_titles)
    words = all_titles.split()
    
    stopwords = set([
        '질문', '후기', '정보', '요금제', '알뜰폰', '추천', '있나요', '나요', '가요', '건가요',
        '오늘', '내일', '이번달', '2월', '1월', '근데', '진짜', '혹시', '아니', '너무', '번호이동', '기변', '신규', '개통', '모바일', '사람', '생각', '지금', '어제',
        '약정', '결합', '할인', '카드', '데이터', '평생', '개월', '년',
                'vs', '이거', '저거', '그거', '뭐야', '시발', '존나', 'ㅋㅋ', 'ㅎㅎ', 'ㅠㅠ',
        '문의', '질문좀', '대해', '관련', '어떤가요', '무슨', '어디', '어떻게',
        '선택', '위약금', '정책', '비교', '변경', '이동', '사용', '가입', '해지',
        '있음', '알뜰', '요금', '번호', '통신사', '요금', '도와주세요'
    ])
    filtered_words = [w for w in words if len(w) >= 2 and w.lower() not in stopwords]
    return Counter(filtered_words).most_common(10)

def send_slack_message(message):
    """테스트 모드 확인 후 팀즈(Adaptive Card) 전송 또는 출력"""
    webhook_url = os.environ.get('COPILOT_WEBHOOK_URL')
    
    # 💡 [핵심 추가] 팀즈 마크다운은 엔터 하나(\n)를 무시하므로, 두 개(\n\n)로 강제 변환하여 줄바꿈 해결!
    teams_message = message.replace('\n', '\n\n')
    
    if TEST_MODE:
        print("\n" + "="*40)
        print(f"📢 [TEST MODE] 알림 발송 생략 (Target: {TARGET_DATE})")
        print("="*40)
        print(teams_message)
        print("="*40 + "\n")
        return

    if webhook_url:
        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.2",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": teams_message,  # 변환된 메시지 삽입
                                "wrap": True
                            }
                        ]
                    }
                }
            ]
        }
        
        try:
            response = requests.post(webhook_url, json=payload, timeout=20)
            response.raise_for_status()
            print("✅ 팀즈(Copilot) 전송 완료")
        except requests.exceptions.RequestException as e:
            raise RuntimeError('팀즈 알림 전송 실패') from e
    else:
        raise RuntimeError('COPILOT_WEBHOOK_URL이 설정되지 않았습니다.')


def analyze_and_notify(p_posts, d_posts, driver):
    total_posts = p_posts + d_posts
    df = pd.DataFrame(total_posts, columns=['source', 'title', 'link', 'views', 'comments'])
    p_cnt = len(p_posts)
    d_cnt = len(d_posts)
    
    p_status = "🔴 과열" if p_cnt >= 180 else ("🟢 평온" if p_cnt < 80 else "🟡 활발")
    d_status = "🔴 과열" if d_cnt >= 600 else ("🟢 평온" if d_cnt < 300 else "🟡 활발")

    brands = BRANDS

    brand_counts = {}
    seven_links = []

    for b_name, keywords in brands.items():
        filtered = df[df['title'].apply(lambda x: matches_brand(x, b_name))]
        brand_counts[b_name] = int(len(filtered))
        
        if b_name == '세븐모바일' and len(filtered) > 0:
            for _, row in filtered.iterrows():
                # 팀즈 마크다운 포맷 적용 [텍스트](URL)
                seven_links.append(f"  └ [{row['title']}]({row['link']})")

    sov_lines = []
    seven_cnt = brand_counts.get('세븐모바일', 0)
    sov_lines.append(f"• 세븐모바일: {seven_cnt}건")
    
    sorted_brands = sorted(brand_counts.items(), key=lambda x: x[1], reverse=True)
    for b_name, cnt in sorted_brands:
        if b_name == '세븐모바일': continue
        if cnt > 0:
            sov_lines.append(f"• {b_name}: {cnt}건")

    sov_msg = "\n".join(sov_lines)
    seven_block = ""
    if seven_links:
        # 팀즈 볼드체 포맷 적용 **텍스트**
        seven_block = f"\n**📌 세븐모바일 언급 ({len(seven_links)}건)**\n" + "\n".join(seven_links)

    top_keywords = extract_top_keywords(df)
    keyword_msg = ""
    for word, count in top_keywords:
        keyword_msg += f"• {word}: {count}건\n"
    if not keyword_msg: keyword_msg = "• 특이사항 없음"

    DATA_TOP_N = 10  # 본문/댓글을 실제로 긁어와서 dashboard_history/xlsx에 저장할 게시글 수
    MSG_TOP_N = 5    # 팀즈 알림 메시지에 실제로 나열할 게시글 수 (기존과 동일하게 5개 유지)

    def format_list(sub_df, detail_fetcher):
        if sub_df.empty: return "없음", []
        top_df = sub_df.sort_values(by='views', ascending=False).head(DATA_TOP_N)
        lines = []
        top_data = []
        for rank, (idx, row) in enumerate(top_df.iterrows()):
            title = row['title']
            icon = ""
            if any(k in title for k in ['0원', '무제한', '평생', '대란', '공짜']): icon = " 💰"

            # 팀즈 메시지에는 상위 MSG_TOP_N개까지만 표시 (기존처럼 Top 5 유지)
            if rank < MSG_TOP_N:
                # 팀즈 마크다운 포맷 적용 [텍스트](URL)
                lines.append(f"• [{title}]({row['link']}){icon} (👁️ {row['views']:,} / 💬 {row['comments']})")

            # 저장용 데이터는 DATA_TOP_N개까지 상세 페이지(본문+댓글) 추가 크롤링 -> 요청량을 통제
            content, top_comments = detail_fetcher(driver, row['link'])
            top_data.append({
                'title': row['title'],
                'link': row['link'],
                'views': int(row['views']),
                'comments': int(row['comments']),
                'content': content,
                'top_comments': top_comments,
            })
        return "\n".join(lines), top_data

    p_msg, p_top10 = format_list(pd.DataFrame(p_posts), get_ppomppu_detail)
    d_msg, d_top10 = format_list(pd.DataFrame(d_posts), get_dc_detail)

    history_file = 'data/dashboard_history.json'
    history_data = []
    if os.path.exists(history_file):
        with open(history_file, 'r', encoding='utf-8') as f:
            history_data = json.load(f)
        if not isinstance(history_data, list):
            raise ValueError('기존 이력 형식 오류: 덮어쓰지 않습니다.')
    
    today_entry = {
        "date": TARGET_DATE,
        "total_volume": { "ppomppu": p_cnt, "dc": d_cnt },
        "brand_sov": brand_counts,
        "top_keywords": dict(top_keywords),
        "top_posts": { "ppomppu": p_top10, "dc": d_top10 }
    }
    
    history_data = [d for d in history_data if d['date'] != TARGET_DATE]
    history_data.append(today_entry)
    history_data.sort(key=lambda x: x['date'])
    
    if not TEST_MODE:
        os.makedirs('data/monitoring', exist_ok=True)
        for path, value in [(history_file, history_data),
                            (f'data/monitoring/data_{TARGET_DATE}.json', total_posts)]:
            temporary = path + '.tmp'
            with open(temporary, 'w', encoding='utf-8') as f:
                json.dump(value, f, ensure_ascii=False, indent=4)
            os.replace(temporary, path)

    # 전체 마크다운을 팀즈 규격(**볼드**, [링크](URL))으로 싹 바꿈
    slack_text = f"""
**[📊 {TARGET_DATE} 알뜰폰 커뮤니티 모니터링]**

**🌡️ 커뮤니티 활성도**
• 뽐뿌: {p_status} ({p_cnt}개)
• 디시: {d_status} ({d_cnt}개)

**📈 브랜드 언급량 (SOV)**
{sov_msg}{seven_block}

**🔥 핫 키워드 (Top 10)**
{keyword_msg}

**1️⃣ 뽐뿌 휴대폰포럼 (Top 5)**
{p_msg}

**2️⃣ 디시 알뜰폰 갤러리 (Top 5)**
{d_msg}

👉 [웹 대시보드 확인하기](https://mvno-market-monitor-pdbgy5y4mzsjsjwf3rgqfs.streamlit.app/)
    """
    
    send_slack_message(slack_text)

if __name__ == "__main__":
    driver = get_driver()
    try:
        p_data = get_ppomppu_posts(driver)
        d_data = get_dc_posts(driver)
        analyze_and_notify(p_data, d_data, driver)
        print("✅ 작업 완료")
    except Exception as e:
        raise RuntimeError("시장 조사 실패: 정상 데이터 갱신을 중단합니다.") from e
    finally:
        driver.quit()

