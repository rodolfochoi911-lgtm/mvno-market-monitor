import os
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import sys

with patch.object(sys, 'argv', ['monitor_crawler.py']):
    from scripts import monitor_crawler as crawler
from scripts.brand_rules import matches_brand


def page(date, number, title='알뜰폰 요금 질문', views='1,234'):
    return f'<table><tr><td><a href="view.php?id=phone&no={number}"><font class="list_title">{title}</font></a></td><td title="{date} 12:00:00">{date}</td><td class="baseList-views">{views}</td></tr></table>'


class MarketRegressionTests(unittest.TestCase):
    def test_non_brand_mentions_are_excluded(self):
        for text, brand in [('세븐일레븐 우주패스 쓰레기봉투', '세븐모바일'), ('아이폰 에어 skt 기변 64', 'SKT_Air'), ('3사 관련된 이야기는 괜찮네', '이야기모바일'), ('다음 페이지 어디 있나요', '이지모바일')]:
            with self.subTest(text=text):
                self.assertFalse(matches_brand(text, brand))

    def test_real_brand_mentions_are_kept(self):
        for text, brand in [('세븐모바일 요금제', '세븐모바일'), ('7모 가입', '세븐모바일'), ('에어 무제한으로 사용', 'SKT_Air'), ('이야기모바일 가입', '이야기모바일'), ('KG는 슬슬 다시 열자', 'KG모바일')]:
            with self.subTest(text=text):
                self.assertTrue(matches_brand(text, brand))

    def test_backfill_reaches_beyond_page_eleven(self):
        pages = [page('26.09.08', i) for i in range(12)] + [page('26.09.07', 12), page('26.09.06', 13)]
        with patch.object(crawler, 'TARGET_DATE', '2026-09-07'), patch.object(crawler, '_get_html', side_effect=pages), patch.object(crawler.time, 'sleep'):
            result = crawler.get_ppomppu_posts(None)
        self.assertEqual(1, len(result))
        self.assertIn('no=12', result[0]['link'])

    def test_block_page_is_failure_not_zero(self):
        with patch.object(crawler, '_get_html', return_value='<h1>403 Forbidden</h1>'):
            with self.assertRaises(RuntimeError):
                crawler.get_ppomppu_posts(None)

    def test_page_limit_is_failure(self):
        with patch.object(crawler, 'TARGET_DATE', '2026-09-07'), patch.object(crawler, 'MAX_PAGES', 1), patch.object(crawler, '_get_html', return_value=page('26.09.08', 1)), patch.object(crawler.time, 'sleep'):
            with self.assertRaises(RuntimeError):
                crawler.get_ppomppu_posts(None)

    def test_verified_zero_is_valid(self):
        with patch.object(crawler, 'TARGET_DATE', '2026-09-07'), patch.object(crawler, '_get_html', return_value=page('26.09.06', 1)):
            self.assertEqual([], crawler.get_ppomppu_posts(None))

    def test_repeated_page_is_rejected(self):
        with patch.object(crawler, 'TARGET_DATE', '2026-09-07'), patch.object(crawler, '_get_html', return_value=page('26.09.07', 1)), patch.object(crawler.time, 'sleep'):
            with self.assertRaises(RuntimeError):
                crawler.get_ppomppu_posts(None)

    def test_posts_are_deduplicated_across_pages(self):
        pages = [page('26.09.07', 1), page('26.09.07', 1) + page('26.09.07', 2), page('26.09.06', 3)]
        with patch.object(crawler, 'TARGET_DATE', '2026-09-07'), patch.object(crawler, '_get_html', side_effect=pages), patch.object(crawler.time, 'sleep'):
            self.assertEqual(2, len(crawler.get_ppomppu_posts(None)))

    def test_dc_comma_view_count(self):
        html = '<tr class="ub-content us-post"><td class="gall_tit"><a href="/x">글</a></td><td class="gall_date" title="2026-09-07 12:00"></td><td class="gall_count">1,234</td></tr>'
        self.assertEqual(1234, crawler._list_rows(html, 'dc')[0]['views'])

    def test_test_mode_has_no_writes_or_notification(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp:
            try:
                os.chdir(temp)
                with patch.object(crawler, 'TEST_MODE', True), patch.object(crawler.requests, 'post') as post:
                    crawler.analyze_and_notify([], [], None)
                    post.assert_not_called()
                    self.assertEqual([], list(Path(temp).iterdir()))
            finally:
                os.chdir(old_cwd)

    def test_corrupt_history_is_not_overwritten(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp:
            try:
                os.chdir(temp)
                Path('data').mkdir()
                path = Path('data/dashboard_history.json')
                path.write_text('broken', encoding='utf-8')
                with self.assertRaises(json.JSONDecodeError):
                    crawler.analyze_and_notify([], [], None)
                self.assertEqual('broken', path.read_text(encoding='utf-8'))
            finally:
                os.chdir(old_cwd)


if __name__ == '__main__':
    unittest.main()
