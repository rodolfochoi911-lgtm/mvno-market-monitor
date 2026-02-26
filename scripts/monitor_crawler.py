import os
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

# --- [설정 및 입력값 처리] ---
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
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

TARGET_DATE = target_date_str

# --- [1. 브라우저 설정] ---
def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--lang=ko_KR")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

# --- [2. 크롤러: 뽐뿌] ---
def get_ppomppu_posts(driver):
    print("running ppomppu crawler...")
    posts = []
    base_url = "https://www.ppomppu.co.kr/zboard/zboard.php?id=phone&page={}"
    
    for page in range(1, 21): 
        try:
            driver.get(base_url.format(page))
            time.sleep(random.uniform(1.0, 2.0))
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            rows = soup.find_all('tr') 
            
            valid_cnt_in_page = 0
            
            for row in rows:
                title_elem = row.select_one('font.list_title') or row.select_one('a')
                if not title_elem: continue
                
                post_date = ""
                
                time_span = row.select_one('.baseList-time')
                if time_span:
                    date_td = time_span.find_parent('td')
                    if date_td and date_td.get('title'):
                        raw_date = date_td['title'].split(' ')[0]
                        post_date = "20" + raw_date.replace('.', '-')
                
                if not post_date:
                    date_td = row.find('td', title=re.compile(r'\d{2}\.\d{2}\.\d{2}'))
                    if date_td:
                        raw_date = date_td['title'].split(' ')[0]
                        post_date = "20" + raw_date.replace('.', '-')
                
                if not post_date:
                    date_match = re.search(r'\d{2}\.\d{2}\.\d{2}', row.text)
                    if date_match:
                        post_date = "20" + date_match.group().replace('.', '-')

                if post_date == TARGET_DATE:
                    link_elem = row.select_one('a[href*="view.php"]')
                    if not link_elem: continue
                    
                    title = title_elem.text.strip()
                    link = "https://www.ppomppu.co.kr/zboard/" + link_elem['href']
                    
                    views, comments = 0, 0
                    
                    view_tag = row.select_one('.baseList-views')
                    cmt_tag = row.select_one('.baseList-c') or row.select_one('.list_comment2')
                    
                    if view_tag:
                        views = int(view_tag.text.strip().replace(',', '') or 0)
                    else:
                        views_match = re.findall(r'\d{1,3}(?:,\d{3})*', row.text)
                        if views_match: views = int(views_match[-1].replace(',', ''))
                    
                    if cmt_tag:
                        comments = int(cmt_tag.text.strip().replace(',', '') or 0)

                    posts.append({'source': 'ppomppu', 'title': title, 'link': link, 'views': views, 'comments': comments})
                    valid_cnt_in_page += 1
            
            if valid_cnt_in_page == 0 and page > 10:
                print("  - No more posts found. Stopping.")
                break

        except Exception as e:
            print(f"Err Ppomppu p{page}: {e}")
            
    return posts

# --- [3. 크롤러: 디시] --- requests 기반 (셀레니움 봇 감지 우회)
def get_dc_posts(driver=None):
    print("running dc crawler...")
    posts = []
    base_url = "https://gall.dcinside.com/mgallery/board/lists/?id=mvnogallery&page={}"

    # DC 목록 페이지는 서버사이드 렌더링 → requests로 직접 파싱 가능
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://gall.dcinside.com/mgallery/board/lists/?id=mvnogallery",
        "Connection": "keep-alive",
    })
    # 첫 접속으로 쿠키 획득
    try:
        session.get("https://gall.dcinside.com/mgallery/board/lists/?id=mvnogallery", timeout=10)
    except Exception as e:
        print(f"  - DC 초기 접속 실패: {e}")

    empty_page_count = 0

    for page in range(1, 51):
        try:
            time.sleep(random.uniform(0.8, 1.5))
            resp = session.get(base_url.format(page), timeout=15)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, 'html.parser')
            rows = soup.select('tr.ub-content.us-post')

            if not rows:
                empty_page_count += 1
                print(f"  - DC p{page}: rows 없음 ({empty_page_count}회 연속)")
                if empty_page_count >= 3:
                    print("  - 3회 연속 빈 페이지, 중단")
                    break
                continue

            empty_page_count = 0
            stop_crawling = False
            found_in_page = 0

            for row in rows:
                if row.get('data-type') == 'icon_notice':
                    continue
                date_tag = row.select_one('.gall_date')
                if not date_tag or not date_tag.get('title'):
                    continue

                post_date = date_tag['title'].split(' ')[0]

                if post_date == TARGET_DATE:
                    title_tag = row.select_one('.gall_tit > a')
                    if not title_tag:
                        continue
                    title = title_tag.text.strip()
                    href = title_tag.get('href', '')
                    link = ("https://gall.dcinside.com" + href) if href.startswith('/') else href

                    views_tag = row.select_one('.gall_count')
                    try:
                        views = int(views_tag.text.strip().replace(',', '')) if views_tag else 0
                    except (ValueError, AttributeError):
                        views = 0

                    reply_tag = row.select_one('.reply_num')
                    try:
                        comments = int(reply_tag.text.strip('[]')) if reply_tag else 0
                    except (ValueError, AttributeError):
                        comments = 0

                    posts.append({'source': 'dc', 'title': title, 'link': link, 'views': views, 'comments': comments})
                    found_in_page += 1

                elif post_date < TARGET_DATE:
                    stop_crawling = True

            print(f"  - DC p{page}: {found_in_page}건 수집 (누적 {len(posts)}건)")

            if stop_crawling:
                print(f"  - TARGET_DATE 이전 게시글 발견, 수집 완료")
                break

        except Exception as e:
            print(f"Err DC p{page}: {e}")
            break

    print(f"✅ DC 수집 완료: 총 {len(posts)}건")
    return posts

# --- [4. 분석 및 알림 로직] ---
def extract_top_keywords(df):
    if df.empty: return []
    all_titles = " ".join(df['title'].tolist())
    all_titles = re.sub(r'[^\w\s]', ' ', all_titles)
    words = all_titles.split()
    
    stopwords = set([
        '질문', '후기', '정보', '요금제', '알뜰폰', '추천', '있나요', '나요', '가요', '건가요',
        '오늘', '내일', '이번달', '2월', '1월', '근데', '진짜', '혹시', '아니', '너무',
        '유심', '번호이동', '기변', '신규', '개통', '모바일', '사람', '생각', '지금', '어제',
        '약정', '결합', '할인', '카드', '데이터', '무제한', '평생', '개월', '년',
        'skt', 'kt', 'lg', 'lgu', 'sk', 'kt망', 'lgu+', 'u+', 'sk망', '헬로',
        'vs', '이거', '저거', '그거', '뭐야', '시발', '존나', 'ㅋㅋ', 'ㅎㅎ', 'ㅠㅠ',
        '문의', '질문좀', '대해', '관련', '어떤가요', '무슨', '어디', '어떻게',
        '선택', '위약금', '조건', '정책', '비교', '변경', '이동', '사용', '가입', '해지',
        '있음', '알뜰', '요금', '번호', '통신사', '요금', '도와주세요'
    ])
    filtered_words = [w for w in words if len(w) >= 2 and w.lower() not in stopwords]
    return Counter(filtered_words).most_common(10)

def send_slack_message(message):
    """테스트 모드 확인 후 슬랙 전송 또는 출력"""
    webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
    
    if TEST_MODE:
        print("\n" + "="*40)
        print(f"📢 [TEST MODE] 슬랙 발송 생략 (Target: {TARGET_DATE})")
        print("="*40)
        print(message)
        print("="*40 + "\n")
        return

    if webhook_url:
        try:
            response = requests.post(webhook_url, json={"text": message})
            response.raise_for_status()
            print("✅ 슬랙 전송 완료")
        except Exception as e:
            print(f"❌ 슬랙 전송 실패: {e}")
    else:
        print("⚠️ SLACK_WEBHOOK_URL이 설정되지 않았습니다.")

def analyze_and_notify(p_posts, d_posts):
    total_posts = p_posts + d_posts
    if not total_posts:
        print(f"⚠️ {TARGET_DATE} 수집된 데이터 0건")
        return

    df = pd.DataFrame(total_posts)
    p_cnt = len(p_posts)
    d_cnt = len(d_posts)
    
    p_status = "🔴 과열" if p_cnt >= 180 else ("🟢 평온" if p_cnt < 80 else "🟡 활발")
    d_status = "🔴 과열" if d_cnt >= 600 else ("🟢 평온" if d_cnt < 300 else "🟡 활발")

    brands = {
        '세븐모바일': ['세븐모바일', '7모', 'sk7', 'sk텔링크', '세븐', '세븐모'],
        'KT엠모바일': ['kt엠모바일', '엠모바일', '엠모', 'ktm', '케이티엠'],
        '유모바일': ['유모바일', '유모', 'u모바일', '유알모', '유플러스알뜰'],
        '헬로모바일': ['헬로모바일', '헬모', 'cj헬로', '헬로', 'cj'],
        '스카이라이프': ['스카이라이프', '스카이', 'skylife'],
        '토스모바일': ['토스', '토스모바일', 'toss'],
        '리브엠': ['리브엠', '리브모바일', 'kb', '국민은행', '리브m'],
        '우리원모바일': ['우리원', '우리은행', '우리won', '우리원모바일'],
        '이야기모바일': ['이야기', '이야기모바일', '큰사람'],
        '에이모바일': ['에이모바일', 'a모바일', 'a mobile', '에이모'],
        '프리티': ['프리티', 'freet'],
        '모빙': ['모빙', 'mobing'],
        '스노우맨': ['스노우맨', '세종'],
        '아이즈모바일': ['아이즈', '아이즈모바일', 'eyes'],
        '인스모바일': ['인스', '인스모바일'],
        '이지모바일': ['이지', '이지모바일'],
        '티플러스': ['티플러스', '티플'],
        'KG모바일': ['kg모바일', 'kg', '케이지'],
        '티다이렉트': ['티다이렉트', '티다', 't다이렉트', 't다'],
        'SKT_Air': ['skt에어', 'skt air', '에어'],
        '시월모바일': ['시월', '시월모바일'],
        '핀다이렉트' : ['핀다이렉트','핀다']
    }

    brand_counts = {}
    seven_links = []

    for b_name, keywords in brands.items():
        filtered = df[df['title'].apply(lambda x: any(k in x.lower() for k in keywords))]
        brand_counts[b_name] = int(len(filtered))
        
        if b_name == '세븐모바일' and len(filtered) > 0:
            for _, row in filtered.iterrows():
                seven_links.append(f"  └ <{row['link']}|{row['title']}>")

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
        seven_block = f"\n*📌 세븐모바일 언급 ({len(seven_links)}건)*\n" + "\n".join(seven_links)

    top_keywords = extract_top_keywords(df)
    keyword_msg = ""
    for word, count in top_keywords:
        keyword_msg += f"• {word}: {count}건\n"
    if not keyword_msg: keyword_msg = "• 특이사항 없음"

    def format_list(sub_df):
        if sub_df.empty: return "없음", []
        top5 = sub_df.sort_values(by='views', ascending=False).head(5)
        lines = []
        for idx, row in top5.iterrows():
            title = row['title']
            icon = ""
            if any(k in title for k in ['0원', '무제한', '평생', '대란', '공짜']): icon = " 💰"
            lines.append(f"• <{row['link']}|{title}>{icon} (👁️ {row['views']:,} / 💬 {row['comments']})")
        top5_data = top5[['title', 'link', 'views', 'comments']].to_dict('records')
        return "\n".join(lines), top5_data

    p_msg, p_top5 = format_list(pd.DataFrame(p_posts))
    d_msg, d_top5 = format_list(pd.DataFrame(d_posts))

    history_file = 'data/dashboard_history.json'
    history_data = []
    if os.path.exists(history_file):
        with open(history_file, 'r', encoding='utf-8') as f:
            try: history_data = json.load(f)
            except: pass
    
    today_entry = {
        "date": TARGET_DATE,
        "total_volume": { "ppomppu": p_cnt, "dc": d_cnt },
        "brand_sov": brand_counts,
        "top_keywords": dict(top_keywords),
        "top_posts": { "ppomppu": p_top5, "dc": d_top5 }
    }
    
    history_data = [d for d in history_data if d['date'] != TARGET_DATE]
    history_data.append(today_entry)
    history_data.sort(key=lambda x: x['date'])
    
    os.makedirs('data', exist_ok=True)
    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump(history_data, f, ensure_ascii=False, indent=4)

    os.makedirs('data/monitoring', exist_ok=True)
    with open(f'data/monitoring/data_{TARGET_DATE}.json', 'w', encoding='utf-8') as f:
        json.dump(total_posts, f, ensure_ascii=False, indent=4)

    slack_text = f"""
*[📊 {TARGET_DATE} 알뜰폰 커뮤니티 모니터링]*

*🌡️ 커뮤니티 활성도*
• 뽐뿌: {p_status} ({p_cnt}개)
• 디시: {d_status} ({d_cnt}개)

*📈 브랜드 언급량 (SOV)*
{sov_msg}{seven_block}

*🔥 핫 키워드 (Top 10)*
{keyword_msg}

*1️⃣ 뽐뿌 휴대폰포럼 (Top 5)*
{p_msg}

*2️⃣ 디시 알뜰폰 갤러리 (Top 5)*
{d_msg}

👉 <https://rodolfochoi911-lgtm.github.io/mvno-market-monitor/|웹 대시보드 확인하기>
    """
    
    send_slack_message(slack_text)

if __name__ == "__main__":
    driver = get_driver()
    try:
        p_data = get_ppomppu_posts(driver)
        d_data = get_dc_posts()   # DC는 requests 기반, driver 불필요
        analyze_and_notify(p_data, d_data)
        print("✅ 작업 완료")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        driver.quit()
