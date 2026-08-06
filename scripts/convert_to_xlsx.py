"""
dashboard_history.json -> dashboard_history.xlsx 변환 스크립트

시트 구성:
- Volume: 날짜별 ppomppu/dc 게시글 수
- Brand_SOV_Long: 날짜 x 브랜드 x 언급량 (긴 형태, 필터링/피벗 자유도 높음)
- Brand_SOV_Pivot: 날짜 x 브랜드 매트릭스 (Copilot이 바로 표로 읽기 좋은 형태)
- Keywords: 날짜별 top_keywords
- Top_Posts: 날짜별 화제 게시글 (제목/조회수/댓글수)

사용법:
    python convert_to_xlsx.py <입력_json_경로> <출력_xlsx_경로>
"""
import json
import sys
import pandas as pd


def convert(json_path: str, xlsx_path: str):
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    volume_rows = []
    sov_rows = []
    keyword_rows = []
    post_rows = []

    for entry in data:
        date = entry.get("date")

        vol = entry.get("total_volume", {})
        volume_rows.append({
            "date": date,
            "ppomppu": vol.get("ppomppu", 0),
            "dc": vol.get("dc", 0),
        })

        for brand, count in entry.get("brand_sov", {}).items():
            sov_rows.append({"date": date, "brand": brand, "mentions": count})

        for kw, count in entry.get("top_keywords", {}).items():
            keyword_rows.append({"date": date, "keyword": kw, "count": count})

        for source, posts in entry.get("top_posts", {}).items():
            for p in posts:
                post_rows.append({
                    "date": date,
                    "source": source,
                    "title": p.get("title"),
                    "link": p.get("link"),
                    "views": p.get("views"),
                    "comments": p.get("comments"),
                })

    df_volume = pd.DataFrame(volume_rows)
    df_sov = pd.DataFrame(sov_rows)
    df_keywords = pd.DataFrame(keyword_rows)
    df_posts = pd.DataFrame(post_rows)

    df_sov_pivot = df_sov.pivot_table(
        index="date", columns="brand", values="mentions", fill_value=0
    ).reset_index()

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df_volume.to_excel(writer, sheet_name="Volume", index=False)
        df_sov.to_excel(writer, sheet_name="Brand_SOV_Long", index=False)
        df_sov_pivot.to_excel(writer, sheet_name="Brand_SOV_Pivot", index=False)
        df_keywords.to_excel(writer, sheet_name="Keywords", index=False)
        df_posts.to_excel(writer, sheet_name="Top_Posts", index=False)

    print(f"완료: {len(data)}개 날짜 -> {xlsx_path}")


if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else "data/dashboard_history.json"
    xlsx_path = sys.argv[2] if len(sys.argv) > 2 else "data/dashboard_history.xlsx"
    convert(json_path, xlsx_path)
