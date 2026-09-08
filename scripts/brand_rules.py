"""Conservative title matching: brand mentions, not subscriber market share."""
import re

BRANDS = {
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
    '핀다이렉트' : ['핀다이렉트','핀다'],
    '도시락모바일' : ['도시락','도시락모바일'],
        '모나모바일': ['모나', '모나모바일'],
'조이텔': ['조이텔'],
'알닷': ['알닷'],
}

# Ambiguous everyday words require an explicit brand name.
BRANDS['이야기모바일'] = ['이야기모바일', '이야기 모바일', '큰사람']
BRANDS['이지모바일'] = ['이지모바일', '이지 모바일', '이지 모']
BRANDS['KG모바일'] = ['kg모바일', 'kg 모바일', '케이지모바일', 'kg']


def matches_brand(title, brand):
    text = title.lower()
    if brand == '세븐모바일':
        text = re.sub(r'세븐\s*일레븐', '', text)
    if brand == 'SKT_Air':
        text = re.sub(r'(?:아이폰|아이패드|맥북|iphone|ipad|macbook)\s*(?:에어|air)', '', text)
    for alias in BRANDS[brand]:
        # A long, explicit name is safe inside a sentence; short aliases need a boundary.
        prefix = r'(?<![가-힣a-z0-9])' if len(alias) <= 3 else ''
        if re.search(prefix + re.escape(alias.lower()) + r'(?![a-z0-9])', text):
            return True
    return False
