import streamlit as st
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from datetime import datetime, timedelta

# ─────────────────────────────────────────
# 기본 설정
# ─────────────────────────────────────────
st.set_page_config(
    page_title="알뜰폰 커뮤니티 모니터링",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    /* 전체 배경 */
    .block-container { padding-top: 1.5rem; }

    /* 메트릭 카드 */
    [data-testid="metric-container"] {
        background: #f8f9fb;
        border: 1px solid #e8eaed;
        border-radius: 10px;
        padding: 14px 18px;
    }
    [data-testid="metric-container"] > div:first-child { font-size: 0.78rem; color: #666; }
    [data-testid="metric-container"] > div:nth-child(2) { font-size: 1.6rem; font-weight: 700; }

    /* 섹션 헤더 */
    .section-header {
        font-size: 1rem;
        font-weight: 600;
        color: #333;
        border-left: 3px solid #4a90d9;
        padding-left: 10px;
        margin: 10px 0 6px 0;
    }

    /* 게시글 링크 테이블 */
    .post-table { width: 100%; border-collapse: collapse; font-size: 0.87rem; }
    .post-table th { background: #f1f3f5; color: #555; padding: 8px 10px; text-align: left; border-bottom: 2px solid #dee2e6; }
    .post-table td { padding: 7px 10px; border-bottom: 1px solid #f0f0f0; vertical-align: middle; }
    .post-table tr:hover td { background: #fafbff; }
    .post-table a { color: #2563eb; text-decoration: none; }
    .post-table a:hover { text-decoration: underline; }

    /* 활성도 뱃지 */
    .badge-hot  { background:#fee2e2; color:#b91c1c; padding:3px 9px; border-radius:12px; font-size:0.8rem; font-weight:600; }
    .badge-mid  { background:#fef3c7; color:#92400e; padding:3px 9px; border-radius:12px; font-size:0.8rem; font-weight:600; }
    .badge-calm { background:#d1fae5; color:#065f46; padding:3px 9px; border-radius:12px; font-size:0.8rem; font-weight:600; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────
# 데이터 로드
# ─────────────────────────────────────────
DATA_PATH = Path("data/dashboard_history.json")

@st.cache_data(ttl=300)
def load_data():
    if not DATA_PATH.exists():
        return []
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

history = load_data()

if not history:
    st.error("📂 `data/dashboard_history.json` 파일을 찾을 수 없어요. 크롤러를 먼저 실행해주세요.")
    st.stop()

df_history = pd.DataFrame([
    {
        "date": d["date"],
        "ppomppu": d["total_volume"].get("ppomppu", 0),
        "dc": d["total_volume"].get("dc", 0),
        **{f"sov_{k}": v for k, v in d.get("brand_sov", {}).items()},
    }
    for d in history
])
df_history["total"] = df_history["ppomppu"] + df_history["dc"]
df_history["date"] = pd.to_datetime(df_history["date"])
df_history = df_history.sort_values("date")

latest = history[-1]
prev   = history[-2] if len(history) >= 2 else None


# ─────────────────────────────────────────
# 사이드바 필터
# ─────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📡 알뜰폰 모니터링")
    st.markdown("---")

    # 날짜 범위 슬라이더
    all_dates = df_history["date"].dt.date.tolist()
    st.markdown("#### 📅 조회 기간")
    if len(all_dates) >= 2:
        date_range = st.slider(
            "기간 선택",
            min_value=all_dates[0],
            max_value=all_dates[-1],
            value=(
                max(all_dates[0], all_dates[-1] - timedelta(days=29)),
                all_dates[-1]
            ),
            format="MM/DD",
            label_visibility="collapsed",
        )
        mask = (df_history["date"].dt.date >= date_range[0]) & (df_history["date"].dt.date <= date_range[1])
        df_filtered = df_history[mask]
    else:
        df_filtered = df_history

    st.markdown("---")

    # SOV 트렌드에서 볼 브랜드 선택
    st.markdown("#### 📈 SOV 트렌드 브랜드")
    brand_cols = [c.replace("sov_", "") for c in df_history.columns if c.startswith("sov_")]
    # 기본값: 언급량 상위 5개
    default_brands = (
        df_history[[f"sov_{b}" for b in brand_cols]]
        .sum()
        .sort_values(ascending=False)
        .head(5)
        .index.str.replace("sov_", "")
        .tolist()
    )
    selected_brands = st.multiselect(
        "브랜드 선택",
        options=brand_cols,
        default=default_brands,
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown(f"📆 최신 데이터: **{latest['date']}**")
    st.markdown(f"📦 총 {len(history)}일치 수집")
    if st.button("🔄 데이터 새로고침"):
        st.cache_data.clear()
        st.rerun()


# ─────────────────────────────────────────
# 메인 헤더
# ─────────────────────────────────────────
st.markdown("# 📊 알뜰폰 커뮤니티 모니터링 대시보드")
st.markdown(f"기준일: **{latest['date']}**")
st.markdown("---")


# ─────────────────────────────────────────
# 1. KPI 메트릭 카드
# ─────────────────────────────────────────
p_cnt   = latest["total_volume"].get("ppomppu", 0)
d_cnt   = latest["total_volume"].get("dc", 0)
total   = p_cnt + d_cnt
p_prev  = prev["total_volume"].get("ppomppu", 0) if prev else None
d_prev  = prev["total_volume"].get("dc", 0) if prev else None
t_prev  = (p_prev + d_prev) if prev else None

# 7일 평균
if len(history) >= 7:
    avg7 = sum(
        h["total_volume"].get("ppomppu", 0) + h["total_volume"].get("dc", 0)
        for h in history[-7:]
    ) / 7
else:
    avg7 = None

# 가장 많이 언급된 브랜드
brand_sov = latest.get("brand_sov", {})
top_brand = max(brand_sov, key=brand_sov.get) if brand_sov else "-"
top_brand_cnt = brand_sov.get(top_brand, 0)

def activity_badge(cnt, p_thres=(80, 180), d_thres=(300, 600)):
    if cnt == 0: return '<span class="badge-calm">데이터 없음</span>'
    return ""  # 아래에서 개별 처리

def fmt_delta(val, ref):
    if ref is None or ref == 0: return None
    d = val - ref
    return f"{'+' if d >= 0 else ''}{d}건"

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("📦 총 게시글", f"{total:,}건", fmt_delta(total, t_prev))
with col2:
    st.metric("🔴 뽐뿌", f"{p_cnt:,}건", fmt_delta(p_cnt, p_prev))
with col3:
    st.metric("🟣 디시", f"{d_cnt:,}건", fmt_delta(d_cnt, d_prev))
with col4:
    st.metric("📉 7일 평균", f"{avg7:.0f}건" if avg7 else "-")
with col5:
    st.metric("🏆 TOP 브랜드", f"{top_brand}", f"{top_brand_cnt}건 언급")

st.markdown("")


# ─────────────────────────────────────────
# 2. 커뮤니티 활성도 상태
# ─────────────────────────────────────────
def activity_label(cnt, low, high):
    if cnt >= high:   return "🔴 과열", "badge-hot"
    elif cnt >= low:  return "🟡 활발", "badge-mid"
    else:             return "🟢 평온", "badge-calm"

p_label, p_cls = activity_label(p_cnt, 80, 180)
d_label, d_cls = activity_label(d_cnt, 300, 600)

st.markdown('<div class="section-header">🌡️ 커뮤니티 활성도</div>', unsafe_allow_html=True)
c1, c2 = st.columns(2)
with c1:
    st.markdown(
        f'뽐뿌 휴대폰포럼 &nbsp; <span class="{p_cls}">{p_label} ({p_cnt}건)</span>',
        unsafe_allow_html=True,
    )
with c2:
    st.markdown(
        f'디시 알뜰폰갤 &nbsp; <span class="{d_cls}">{d_label} ({d_cnt}건)</span>',
        unsafe_allow_html=True,
    )

st.markdown("---")


# ─────────────────────────────────────────
# 3. 게시글 볼륨 추이
# ─────────────────────────────────────────
st.markdown('<div class="section-header">📈 일별 게시글 볼륨 추이</div>', unsafe_allow_html=True)

df_vol = df_filtered[["date", "ppomppu", "dc"]].copy()
df_vol_melt = df_vol.melt("date", var_name="커뮤니티", value_name="게시글 수")
df_vol_melt["커뮤니티"] = df_vol_melt["커뮤니티"].map({"ppomppu": "뽐뿌", "dc": "디시"})

fig_vol = px.line(
    df_vol_melt,
    x="date", y="게시글 수", color="커뮤니티",
    markers=True,
    color_discrete_map={"뽐뿌": "#ef4444", "디시": "#3b82f6"},
    template="plotly_white",
)
fig_vol.update_traces(line_width=2, marker_size=5)
fig_vol.update_layout(
    margin=dict(t=10, b=10), height=280,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    xaxis_title="", yaxis_title="게시글 수",
    hovermode="x unified",
)
st.plotly_chart(fig_vol, use_container_width=True)


# ─────────────────────────────────────────
# 4. 브랜드 SOV (최신일 + 트렌드)
# ─────────────────────────────────────────
st.markdown('<div class="section-header">🏷️ 브랜드 언급량 (SOV)</div>', unsafe_allow_html=True)
tab_sov1, tab_sov2 = st.tabs(["오늘 순위", "기간별 트렌드"])

with tab_sov1:
    sov_df = pd.DataFrame(
        sorted(brand_sov.items(), key=lambda x: x[1], reverse=True),
        columns=["브랜드", "언급 건수"]
    )
    sov_df = sov_df[sov_df["언급 건수"] > 0]
    if sov_df.empty:
        st.info("언급된 브랜드가 없어요.")
    else:
        fig_sov = px.bar(
            sov_df, x="언급 건수", y="브랜드", orientation="h",
            color="언급 건수",
            color_continuous_scale=["#dbeafe", "#1d4ed8"],
            template="plotly_white",
            text="언급 건수",
        )
        fig_sov.update_traces(textposition="outside")
        fig_sov.update_layout(
            margin=dict(t=10, b=10), height=max(250, len(sov_df) * 32),
            coloraxis_showscale=False, yaxis=dict(autorange="reversed"),
            xaxis_title="언급 건수", yaxis_title="",
        )
        st.plotly_chart(fig_sov, use_container_width=True)

with tab_sov2:
    if not selected_brands:
        st.info("사이드바에서 브랜드를 선택해주세요.")
    else:
        trend_cols = ["date"] + [f"sov_{b}" for b in selected_brands if f"sov_{b}" in df_filtered.columns]
        df_trend = df_filtered[trend_cols].copy()
        df_trend = df_trend.rename(columns={f"sov_{b}": b for b in selected_brands})
        df_melt = df_trend.melt("date", var_name="브랜드", value_name="언급 건수")

        fig_trend = px.line(
            df_melt, x="date", y="언급 건수", color="브랜드",
            markers=True, template="plotly_white",
        )
        fig_trend.update_traces(line_width=2, marker_size=5)
        fig_trend.update_layout(
            margin=dict(t=10, b=10), height=300,
            xaxis_title="", yaxis_title="언급 건수",
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_trend, use_container_width=True)


# ─────────────────────────────────────────
# 5. 핫 키워드 + SOV 누적 파이
# ─────────────────────────────────────────
st.markdown('<div class="section-header">🔥 핫 키워드 & 브랜드 점유율</div>', unsafe_allow_html=True)
col_kw, col_pie = st.columns([3, 2])

with col_kw:
    kw_raw = latest.get("top_keywords", {})
    if kw_raw:
        kw_df = pd.DataFrame(kw_raw.items(), columns=["키워드", "빈도"]).sort_values("빈도")
        fig_kw = px.bar(
            kw_df, x="빈도", y="키워드", orientation="h",
            color="빈도",
            color_continuous_scale=["#fef3c7", "#f59e0b"],
            template="plotly_white", text="빈도",
        )
        fig_kw.update_traces(textposition="outside")
        fig_kw.update_layout(
            margin=dict(t=10, b=10), height=320,
            coloraxis_showscale=False,
            xaxis_title="빈도", yaxis_title="",
        )
        st.plotly_chart(fig_kw, use_container_width=True)
    else:
        st.info("키워드 데이터 없음")

with col_pie:
    # 기간 내 브랜드 누적 언급 파이차트
    sov_sum = {
        b: int(df_filtered[f"sov_{b}"].sum())
        for b in brand_cols
        if f"sov_{b}" in df_filtered.columns
    }
    sov_sum = {k: v for k, v in sov_sum.items() if v > 0}
    if sov_sum:
        pie_df = pd.DataFrame(sov_sum.items(), columns=["브랜드", "누적 언급"])
        fig_pie = px.pie(
            pie_df, names="브랜드", values="누적 언급",
            hole=0.4, template="plotly_white",
            color_discrete_sequence=px.colors.qualitative.Pastel,
        )
        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
        fig_pie.update_layout(
            margin=dict(t=30, b=10), height=320,
            showlegend=False,
            title=dict(text="기간 내 브랜드 점유율", x=0.5, font_size=13),
        )
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("선택 기간 내 브랜드 언급 없음")


# ─────────────────────────────────────────
# 6. 인기글 아카이브
# ─────────────────────────────────────────
st.markdown("---")
st.markdown('<div class="section-header">🏆 일별 인기글 아카이브</div>', unsafe_allow_html=True)

available_dates = [h["date"] for h in history]
selected_date = st.selectbox(
    "날짜 선택",
    options=list(reversed(available_dates)),
    label_visibility="collapsed",
)
day_data = next((h for h in history if h["date"] == selected_date), None)

if day_data:
    tab_p, tab_d = st.tabs(["📮 뽐뿌 Top 5", "💬 디시 Top 5"])

    def render_posts(posts, source):
        if not posts:
            st.info("데이터 없음")
            return
        rows_html = ""
        for i, p in enumerate(posts, 1):
            icon = "💰 " if any(k in p.get("title","") for k in ["0원","무제한","평생","대란","공짜"]) else ""
            rows_html += f"""
            <tr>
                <td style="color:#999;width:28px">{i}</td>
                <td><a href="{p['link']}" target="_blank">{icon}{p['title']}</a></td>
                <td style="color:#666;white-space:nowrap">👁 {p.get('views',0):,}</td>
                <td style="color:#666;white-space:nowrap">💬 {p.get('comments',0)}</td>
            </tr>"""
        st.markdown(
            f'<table class="post-table"><thead><tr><th>#</th><th>제목</th><th>조회</th><th>댓글</th></tr></thead><tbody>{rows_html}</tbody></table>',
            unsafe_allow_html=True,
        )

    with tab_p:
        render_posts(day_data.get("top_posts", {}).get("ppomppu", []), "ppomppu")
    with tab_d:
        render_posts(day_data.get("top_posts", {}).get("dc", []), "dc")


# ─────────────────────────────────────────
# 7. 원본 데이터 다운로드
# ─────────────────────────────────────────
with st.expander("📥 원본 데이터 다운로드"):
    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        csv_vol = df_history[["date", "ppomppu", "dc", "total"]].to_csv(index=False).encode("utf-8-sig")
        st.download_button("볼륨 CSV", csv_vol, "volume.csv", "text/csv")
    with col_dl2:
        json_bytes = json.dumps(history, ensure_ascii=False, indent=2).encode("utf-8")
        st.download_button("전체 JSON", json_bytes, "dashboard_history.json", "application/json")
