import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from scripts.convert_to_xlsx import convert


class ExcelSourceSheetTests(unittest.TestCase):
    def test_collected_text_round_trips_without_formulas_or_errors(self):
        texts = [
            '=1+1', '+요금제 행사', '-할인 안내', '@사용자 문의',
            '  =SUM(1,2)', '\t+행사', '\n-본문', ' \t@댓글',
            '=HYPERLINK("https://example.com", "링크")',
            '#N/A', '#REF!', '일반 게시글',
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / 'history.json'
            output_path = Path(temp_dir) / 'history.xlsx'
            history_path.write_text(json.dumps([{
                'date': '2026-11-22',
                'total_volume': {'ppomppu': 1, 'dc': len(texts)},
                'brand_sov': {'=브랜드': 2},
                'top_keywords': {text: 1 for text in texts},
                'brand_sov_by_source': {'dc': {'=브랜드': 2}},
                'top_keywords_by_source': {'dc': {text: 1 for text in texts}},
                'top_posts': {'dc': [{
                    'title': text, 'content': text,
                    'top_comments': [text, '다음 댓글'],
                    'link': 'https://example.com/post',
                    'views': 17, 'comments': 2,
                } for text in texts]},
            }], ensure_ascii=False), encoding='utf-8')
            original_json = history_path.read_bytes()

            convert(str(history_path), str(output_path))

            for data_only in (False, True):
                book = load_workbook(output_path, data_only=data_only)
                try:
                    posts = book['Top_Posts']
                    columns = {cell.value: cell.column for cell in posts[1]}
                    for row, text in enumerate(texts, start=2):
                        for name, expected in (
                            ('title', text), ('content', text),
                            ('top_comments', text + ' | 다음 댓글'),
                        ):
                            with self.subTest(data_only=data_only, text=text, column=name):
                                cell = posts.cell(row, columns[name])
                                self.assertEqual(expected, cell.value)
                                self.assertEqual('s', cell.data_type)
                                self.assertEqual(
                                    text.lstrip().startswith(('=', '+', '-', '@')),
                                    cell.quotePrefix,
                                )
                        self.assertEqual(17, posts.cell(row, columns['views']).value)
                        self.assertEqual('n', posts.cell(row, columns['views']).data_type)
                    for sheet in book:
                        for row in sheet:
                            for cell in row:
                                self.assertNotIn(cell.data_type, ('f', 'e'))
                    keywords = {row[1].value for row in book['Keywords_Raw'].iter_rows(min_row=2)}
                    self.assertEqual(set(texts), keywords)
                    self.assertIn('=브랜드', [cell.value for cell in book['Brand_SOV_Pivot'][1]])
                finally:
                    book.close()
            self.assertEqual(original_json, history_path.read_bytes())

    def test_existing_sheets_remain_and_source_sheets_are_added(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            data_dir = temp / 'data'
            raw_dir = data_dir / 'monitoring'
            raw_dir.mkdir(parents=True)
            history_path = data_dir / 'dashboard_history.json'
            output_path = data_dir / 'dashboard_history.xlsx'

            history_path.write_text(json.dumps([{
                'date': '2026-09-26',
                'total_volume': {'ppomppu': 1, 'dc': 2},
                'brand_sov': {'유모바일': 2, '프리티': 1},
                'top_keywords': {'유모바일': 2, '프리티': 1},
                'top_posts': {'ppomppu': [], 'dc': []},
            }], ensure_ascii=False), encoding='utf-8')
            (raw_dir / 'data_2026-09-26.json').write_text(json.dumps([
                {'source': 'ppomppu', 'title': '유모바일 추천인', 'link': 'p', 'views': 1, 'comments': 0},
                {'source': 'dc', 'title': '유모바일 문의', 'link': 'd1', 'views': 2, 'comments': 0},
                {'source': 'dc', 'title': '프리티 가입', 'link': 'd2', 'views': 3, 'comments': 0},
            ], ensure_ascii=False), encoding='utf-8')

            convert(str(history_path), str(output_path))
            sheets = pd.read_excel(output_path, sheet_name=None)

            existing = {
                'Volume', 'Brand_SOV_Long', 'Brand_SOV_Pivot', 'Keywords_Raw',
                'Keywords_Normalized', 'Top_Posts', 'Monthly_Summary',
                'Brand_Ranking', 'Weekly_Trend', 'Keyword_Spike',
            }
            added = {
                'Brand_SOV_Source_Long', 'Keywords_Source_Raw',
                'Keywords_Source_Normalized',
            }
            self.assertTrue(existing.issubset(sheets))
            self.assertTrue(added.issubset(sheets))

            source_sov = sheets['Brand_SOV_Source_Long']
            umo = source_sov[source_sov['brand'] == '유모바일']
            self.assertEqual(2, int(umo['mentions'].sum()))
            self.assertEqual({'ppomppu', 'dc'}, set(umo['source']))


if __name__ == '__main__':
    unittest.main()
