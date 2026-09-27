import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.convert_to_xlsx import convert


class ExcelSourceSheetTests(unittest.TestCase):
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
