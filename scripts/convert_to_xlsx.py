"""
dashboard_history.json -> dashboard_history.xlsx 변환 스크립트 (v2)

시트 구성:
- Volume: 날짜별 ppomppu/dc 게시글 수
- Brand_SOV_Long: 날짜 x 브랜드 x 언급량 (긴 형태)
- Brand_SOV_Pivot: 날짜 x 브랜드 매트릭스
- Keywords_Raw: 원본 top_keywords (별칭 미통합, 참고용)
- Keywords_Normalized: 브랜드 사전으로 별칭 통합한 키워드/브랜드 집계 (Copilot이 참조하기 좋은 형태)
- Top_Posts: 날짜별 화제 게시글
- Monthly_Summary: 월별 볼륨 합계 + 전월 대비 증감률 (Copilot이 직접 계산 안 해도 되게 미리 산출)
- Brand_Ranking: 브랜드별 누적/최근 30일 언급량 + 순위 + 최근 30일 증감률
- Weekly_Trend: 주별 총 볼륨 + 그 주 최다 언급 브랜드 + 전주 대비 증감률
- Keyword_Spike: 최근 7일 평균 대비 이전 30일 평균이 급등한 키워드/브랜드 (이슈 감지용)

사용법:
    python convert_to_xlsx.py <입력_json_경로> <출력_xlsx_경로>
"""
import json
import sys
from datetime import datetime, timedelta

import pandas as pd

# 크롤러(monitor_crawler.py)에서 쓰는 브랜드 별칭 사전과 동일하게 유지할 것.
# 크롤러 쪽 사전이 바뀌면 여기도 같이 업데이트 필요.
BRAND_ALIASES = {
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
    '핀다이렉트': ['핀다이렉트', '핀다'],
    '도시락모바일': ['도시락', '도시락모바일'],
    '모나모바일': ['모나', '모나모바일'],
    '조이텔': ['조이텔'],
    '알닷': ['알닷'],
}
ALIAS_TO_BRAND = {
    alias.lower(): brand for brand, aliases in BRAND_ALIASES.items() for alias in aliases
}


def normalize_term(keyword: str):
    """키워드를 브랜드명으로 정규화. 매칭 안 되면 원본 키워드 그대로 반환."""
    brand = ALIAS_TO_BRAND.get(keyword.lower())
    if brand:
        return brand, "brand"
    return keyword, "keyword"


def convert(json_path: str, xlsx_path: str):
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    volume_rows, sov_rows, keyword_raw_rows, post_rows = [], [], [], []

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
            keyword_raw_rows.append({"date": date, "keyword": kw, "count": count})

        for source, posts in entry.get("top_posts", {}).items():
            for p in posts:
                top_comments = p.get("top_comments") or []
                post_rows.append({
                    "date": date,
                    "source": source,
                    "title": p.get("title"),
                    "link": p.get("link"),
                    "views": p.get("views"),
                    "comments": p.get("comments"),
                    "content": p.get("content", ""),
                    "top_comments": " | ".join(top_comments),
                })

    df_volume = pd.DataFrame(volume_rows)
    df_volume["date"] = pd.to_datetime(df_volume["date"])
    df_volume["total"] = df_volume["ppomppu"] + df_volume["dc"]

    df_sov = pd.DataFrame(sov_rows)
    df_keywords_raw = pd.DataFrame(keyword_raw_rows)
    df_posts = pd.DataFrame(post_rows)

    df_sov_pivot = df_sov.pivot_table(
        index="date", columns="brand", values="mentions", fill_value=0
    ).reset_index()

    # ---------- Keywords_Normalized ----------
    norm_rows = []
    for _, row in df_keywords_raw.iterrows():
        term, term_type = normalize_term(row["keyword"])
        norm_rows.append({
            "date": row["date"], "term": term, "type": term_type, "count": row["count"],
        })
    df_norm = pd.DataFrame(norm_rows)
    df_norm_agg = (
        df_norm.groupby(["date", "term", "type"], as_index=False)["count"].sum()
    )

    # ---------- Monthly_Summary ----------
    df_monthly = df_volume.copy()
    df_monthly["month"] = df_monthly["date"].dt.to_period("M").astype(str)
    monthly = df_monthly.groupby("month", as_index=False)[["ppomppu", "dc", "total"]].sum()
    monthly = monthly.sort_values("month").reset_index(drop=True)
    monthly["mom_change_pct"] = (monthly["total"].pct_change() * 100).round(1)

    # ---------- Brand_Ranking ----------
    max_date = df_sov["date"].max()
    max_date_dt = pd.to_datetime(max_date)
    df_sov_dt = df_sov.copy()
    df_sov_dt["date"] = pd.to_datetime(df_sov_dt["date"])

    last30_start = max_date_dt - timedelta(days=29)
    prior30_start = max_date_dt - timedelta(days=59)
    prior30_end = max_date_dt - timedelta(days=30)

    total_by_brand = df_sov_dt.groupby("brand")["mentions"].sum().rename("total_mentions")
    last30 = (
        df_sov_dt[df_sov_dt["date"] >= last30_start]
        .groupby("brand")["mentions"].sum().rename("last30d_mentions")
    )
    prior30 = (
        df_sov_dt[(df_sov_dt["date"] >= prior30_start) & (df_sov_dt["date"] <= prior30_end)]
        .groupby("brand")["mentions"].sum().rename("prior30d_mentions")
    )

    df_ranking = pd.concat([total_by_brand, last30, prior30], axis=1).fillna(0).reset_index()
    import numpy as np
    df_ranking["change_pct_30d"] = (
        (df_ranking["last30d_mentions"] - df_ranking["prior30d_mentions"])
        / df_ranking["prior30d_mentions"].replace(0, np.nan) * 100
    ).round(1)
    df_ranking["rank_total"] = df_ranking["total_mentions"].rank(ascending=False, method="min").astype(int)
    df_ranking["rank_last30d"] = df_ranking["last30d_mentions"].rank(ascending=False, method="min").astype(int)
    df_ranking = df_ranking.sort_values("rank_total").reset_index(drop=True)

    # ---------- Weekly_Trend ----------
    df_weekly_base = df_volume.copy()
    df_weekly_base["week_start"] = df_weekly_base["date"] - pd.to_timedelta(
        df_weekly_base["date"].dt.weekday, unit="D"
    )
    weekly_vol = df_weekly_base.groupby("week_start", as_index=False)["total"].sum()
    weekly_vol = weekly_vol.sort_values("week_start").reset_index(drop=True)
    weekly_vol["wow_change_pct"] = (weekly_vol["total"].pct_change() * 100).round(1)

    df_sov_weekly = df_sov_dt.copy()
    df_sov_weekly["week_start"] = df_sov_weekly["date"] - pd.to_timedelta(
        df_sov_weekly["date"].dt.weekday, unit="D"
    )
    weekly_brand = (
        df_sov_weekly.groupby(["week_start", "brand"], as_index=False)["mentions"].sum()
    )
    top_brand_per_week = (
        weekly_brand.sort_values("mentions", ascending=False)
        .groupby("week_start").first().reset_index()
        .rename(columns={"brand": "top_brand", "mentions": "top_brand_mentions"})
    )
    df_weekly = weekly_vol.merge(top_brand_per_week, on="week_start", how="left")
    df_weekly = df_weekly.rename(columns={"total": "total_volume"})
    df_weekly["week_start"] = df_weekly["week_start"].dt.strftime("%Y-%m-%d")

    # ---------- Keyword_Spike ----------
    df_norm_dt = df_norm_agg.copy()
    df_norm_dt["date"] = pd.to_datetime(df_norm_dt["date"])
    recent7_start = max_date_dt - timedelta(days=6)
    spike_prior_start = max_date_dt - timedelta(days=36)
    spike_prior_end = max_date_dt - timedelta(days=7)

    recent7 = (
        df_norm_dt[df_norm_dt["date"] >= recent7_start]
        .groupby(["term", "type"])["count"].sum() / 7
    ).rename("recent7d_avg_daily")
    prior30 = (
        df_norm_dt[(df_norm_dt["date"] >= spike_prior_start) & (df_norm_dt["date"] <= spike_prior_end)]
        .groupby(["term", "type"])["count"].sum() / 30
    ).rename("prior30d_avg_daily")

    df_spike = pd.concat([recent7, prior30], axis=1).fillna(0).reset_index()
    df_spike = df_spike[df_spike["recent7d_avg_daily"] > 0]
    df_spike["spike_ratio"] = (
        df_spike["recent7d_avg_daily"] / df_spike["prior30d_avg_daily"].replace(0, 0.1)
    ).round(2)
    df_spike = df_spike.sort_values("spike_ratio", ascending=False).head(30).reset_index(drop=True)

    # ---------- 저장 ----------
    df_volume_out = df_volume.copy()
    df_volume_out["date"] = df_volume_out["date"].dt.strftime("%Y-%m-%d")

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df_volume_out.to_excel(writer, sheet_name="Volume", index=False)
        df_sov.to_excel(writer, sheet_name="Brand_SOV_Long", index=False)
        df_sov_pivot.to_excel(writer, sheet_name="Brand_SOV_Pivot", index=False)
        df_keywords_raw.to_excel(writer, sheet_name="Keywords_Raw", index=False)
        df_norm_agg.to_excel(writer, sheet_name="Keywords_Normalized", index=False)
        df_posts.to_excel(writer, sheet_name="Top_Posts", index=False)
        monthly.to_excel(writer, sheet_name="Monthly_Summary", index=False)
        df_ranking.to_excel(writer, sheet_name="Brand_Ranking", index=False)
        df_weekly.to_excel(writer, sheet_name="Weekly_Trend", index=False)
        df_spike.to_excel(writer, sheet_name="Keyword_Spike", index=False)

    print(f"완료: {len(data)}개 날짜 -> {xlsx_path}")
    print(f"  시트: Volume, Brand_SOV_Long, Brand_SOV_Pivot, Keywords_Raw,")
    print(f"       Keywords_Normalized, Top_Posts, Monthly_Summary, Brand_Ranking,")
    print(f"       Weekly_Trend, Keyword_Spike")


if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else "data/dashboard_history.json"
    xlsx_path = sys.argv[2] if len(sys.argv) > 2 else "data/dashboard_history.xlsx"
    convert(json_path, xlsx_path)
