"""Shared MVNO market metrics used by collection and Excel export."""

import re
from collections import Counter

try:
    from scripts.brand_rules import BRANDS, matches_brand
except ModuleNotFoundError:
    from brand_rules import BRANDS, matches_brand


STOPWORDS = {
    '질문', '후기', '정보', '요금제', '알뜰폰', '추천', '있나요', '나요', '가요', '건가요',
    '오늘', '내일', '이번달', '2월', '1월', '근데', '진짜', '혹시', '아니', '너무',
    '번호이동', '기변', '신규', '개통', '모바일', '사람', '생각', '지금', '어제',
    '약정', '결합', '할인', '카드', '데이터', '평생', '개월', '년',
    'vs', '이거', '저거', '그거', '뭐야', '시발', '존나', 'ㅋㅋ', 'ㅎㅎ', 'ㅠㅠ',
    '문의', '질문좀', '대해', '관련', '어떤가요', '무슨', '어디', '어떻게',
    '선택', '위약금', '정책', '비교', '변경', '이동', '사용', '가입', '해지',
    '있음', '알뜰', '요금', '번호', '통신사', '도와주세요',
}


def extract_keyword_counts(df):
    if df.empty:
        return Counter()
    all_titles = ' '.join(df['title'].fillna('').astype(str).tolist())
    words = re.sub(r'[^\w\s]', ' ', all_titles).split()
    return Counter(word for word in words if len(word) >= 2 and word.lower() not in STOPWORDS)


def extract_top_keywords(df, limit=10):
    return extract_keyword_counts(df).most_common(limit)


def count_brand_mentions(df):
    counts = {}
    for brand in BRANDS:
        if df.empty:
            counts[brand] = 0
        else:
            counts[brand] = int(df['title'].apply(lambda title: matches_brand(str(title), brand)).sum())
    return counts


def build_source_breakdowns(df, keyword_terms=None):
    """Return source-level counts that reconcile to the existing combined metrics."""
    brand_by_source = {}
    keywords_by_source = {}

    for source in ('ppomppu', 'dc'):
        source_df = df[df['source'] == source]
        brand_by_source[source] = count_brand_mentions(source_df)
        source_keywords = extract_keyword_counts(source_df)
        terms = keyword_terms if keyword_terms is not None else source_keywords.keys()
        keywords_by_source[source] = {term: int(source_keywords.get(term, 0)) for term in terms}

    return brand_by_source, keywords_by_source
