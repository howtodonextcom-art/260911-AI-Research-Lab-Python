from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from vietlott_mega645.analytics import (
    TICKET_PRICE_VND,
    TOTAL_COMBINATIONS,
    frequency_frame,
    latest_draw,
    outcome_frame,
    records_to_frame,
    summarize,
    top_numbers,
)
from vietlott_mega645.client import DrawRecord, FetchError, VietlottMega645Client, serialize_jsonl, _agent_log
from vietlott_mega645.storage import DEFAULT_DATA_DIR, DEFAULT_DATASET_PATH, DEFAULT_MANIFEST_PATH, load_manifest, load_records, merge_records, write_dataset


def _on_streamlit_cloud() -> bool:
    return Path("/mount/src").exists()


def _user_facing_fetch_error(exc: FetchError) -> str:
    message = str(exc)
    # #region agent log
    _agent_log(
        "H1",
        "streamlit_app.py:_user_facing_fetch_error",
        "cloud fetch mapped",
        {
            "msg": message[:300],
            "cloud": _on_streamlit_cloud(),
            "http_403": "HTTP 403" in message,
        },
        run_id="post-fix",
    )
    # #endregion
    if "HTTP 403" in message:
        return (
            "vietlott.vn trả HTTP 403 từ máy chủ này. Streamlit Cloud dùng IP datacenter "
            "nên Cloudflare thường chặn crawl trực tiếp. UI vẫn đọc data/official_mega645.jsonl "
            "đã commit. Cập nhật bền: chạy local `python -m vietlott_mega645 sync --all --delay 0.2` rồi push GitHub."
        )
    return message


st.set_page_config(
    page_title="Mega 6/45 Python Lab",
    page_icon=None,
    layout="wide",
)

st.markdown(
    """
    <style>
    :root {
      --ink: #18202a;
      --muted: #637083;
      --panel: #ffffff;
      --line: #d9e0ea;
      --viet-red: #d92332;
      --lottery-gold: #f4b740;
      --cyan: #26a6b8;
      --green: #2f9d62;
    }
    .stApp { background: linear-gradient(180deg, #f6f8fb 0%, #eef3f7 100%); color: var(--ink); }
    h1, h2, h3 { letter-spacing: 0; }
    div[data-testid="stMetric"] {
      background: var(--panel);
      border: 1px solid var(--line);
      border-left: 4px solid var(--viet-red);
      border-radius: 8px;
      padding: 0.85rem 1rem;
      box-shadow: 0 8px 24px rgba(24,32,42,0.06);
    }
    .draw-rack {
      display: flex;
      gap: 0.55rem;
      flex-wrap: wrap;
      align-items: center;
      padding: 0.9rem 0 0.2rem;
    }
    .draw-ball {
      width: 48px;
      height: 48px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 50%;
      font-weight: 800;
      color: #111827;
      background: radial-gradient(circle at 35% 28%, #fff7d7 0 18%, var(--lottery-gold) 45%, #d99a16 100%);
      border: 1px solid #c58b12;
      box-shadow: inset 0 1px 3px rgba(255,255,255,0.8), 0 8px 16px rgba(162,111,13,0.18);
    }
    .source-strip {
      padding: 0.75rem 0.9rem;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255,255,255,0.72);
      color: var(--muted);
      font-size: 0.92rem;
    }
    .freq-bars {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 0.5rem 1rem;
      margin: 0.2rem 0 1rem;
    }
    .freq-row {
      display: grid;
      grid-template-columns: 2.2rem 1fr 3.2rem;
      gap: 0.5rem;
      align-items: center;
      min-height: 1.7rem;
    }
    .freq-label {
      font-weight: 750;
      color: var(--viet-red);
    }
    .freq-track {
      height: 0.7rem;
      background: #dfe6ee;
      border-radius: 999px;
      overflow: hidden;
    }
    .freq-fill {
      height: 100%;
      background: linear-gradient(90deg, var(--viet-red), var(--lottery-gold));
      border-radius: 999px;
    }
    .freq-count {
      color: var(--muted);
      font-size: 0.9rem;
      text-align: right;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def cached_records(dataset_path: str) -> list[DrawRecord]:
    return load_records(Path(dataset_path))


def reload_records() -> list[DrawRecord]:
    cached_records.clear()
    return cached_records(str(DEFAULT_DATASET_PATH))


def format_vnd(value: float | int) -> str:
    return f"{value:,.0f} VND"


def render_balls(record: DrawRecord | None) -> None:
    if not record:
        st.info("Chưa có dữ liệu official trong thư mục Python.")
        return
    balls = "".join(f'<span class="draw-ball">{number:02d}</span>' for number in record.result)
    st.markdown(f'<div class="draw-rack">{balls}</div>', unsafe_allow_html=True)


def render_frequency_bars(frame: pd.DataFrame) -> None:
    if frame.empty:
        st.info("Chưa đủ dữ liệu để vẽ tần suất.")
        return
    max_count = max(1, int(frame["count"].max()))
    rows = []
    for row in frame.sort_values("number").itertuples(index=False):
        width = int(round(float(row.count) / max_count * 100))
        rows.append(
            f"""
            <div class="freq-row">
              <span class="freq-label">{int(row.number):02d}</span>
              <span class="freq-track"><span class="freq-fill" style="width: {width}%"></span></span>
              <span class="freq-count">{int(row.count)}</span>
            </div>
            """
        )
    st.markdown(f'<div class="freq-bars">{"".join(rows)}</div>', unsafe_allow_html=True)


def sync_from_official(max_pages: int | None, delay_seconds: float) -> dict[str, object]:
    # #region agent log
    _agent_log(
        "H4",
        "streamlit_app.py:sync_from_official",
        "sync start",
        {"max_pages": max_pages, "delay_seconds": delay_seconds, "fetch_all": max_pages is None},
    )
    # #endregion
    client = VietlottMega645Client(timeout_seconds=20)
    existing = load_records(DEFAULT_DATASET_PATH)
    try:
        incoming = client.fetch_history(max_pages=max_pages, delay_seconds=delay_seconds)
    except FetchError as exc:
        # #region agent log
        _agent_log(
            "H4",
            "streamlit_app.py:sync_from_official",
            "sync exception",
            {"type": type(exc).__name__, "msg": str(exc)[:500], "handled": True},
            run_id="post-fix",
        )
        # #endregion
        return {"status": "error", "error": _user_facing_fetch_error(exc)}
    except Exception as exc:  # noqa: BLE001 - debug capture then re-raise.
        # #region agent log
        _agent_log(
            "H4",
            "streamlit_app.py:sync_from_official",
            "sync exception",
            {"type": type(exc).__name__, "msg": str(exc)[:500], "handled": False},
            run_id="post-fix",
        )
        # #endregion
        raise
    merged, diff = merge_records(existing, incoming)
    if diff.conflicts:
        return {"status": "failed", "conflicts": list(diff.conflicts), "fetched": len(incoming)}
    manifest = write_dataset(merged)
    reload_records()
    return {
        "status": "ok",
        "fetched": len(incoming),
        "added": diff.added,
        "unchanged": diff.unchanged,
        "recordCount": manifest["recordCount"],
        "latestDrawDate": manifest["latestDrawDate"],
        "latestDrawId": manifest["latestDrawId"],
    }


st.title("Mega 6/45 Python Lab")
st.caption("Dữ liệu official từ vietlott.vn, phân tích bằng Python, UI bằng Streamlit.")

with st.sidebar:
    st.header("Dữ liệu")
    max_pages_choice = st.number_input("Số trang crawl", min_value=1, max_value=196, value=3, step=1)
    fetch_all = st.checkbox("Crawl toàn bộ lịch sử", value=False)
    delay = st.slider("Delay mỗi trang", min_value=0.1, max_value=2.0, value=0.3, step=0.1)
    if _on_streamlit_cloud():
        st.caption(
            "Máy chủ Cloud có thể bị vietlott.vn/Cloudflare chặn lúc crawl. Dataset chính là JSONL trong repo."
        )
    if st.button("Cập nhật từ Vietlott", width="stretch"):
        with st.spinner("Đang đọc dữ liệu public từ vietlott.vn"):
            result = sync_from_official(None if fetch_all else int(max_pages_choice), float(delay))
        if result["status"] == "ok":
            st.success(
                f"Đã cập nhật: {result['recordCount']} kỳ, mới nhất #{result['latestDrawId']} ngày {result['latestDrawDate']}."
            )
        elif result["status"] == "failed":
            st.error(f"Không ghi dữ liệu vì có xung đột: {result.get('conflicts')}")
        else:
            st.error(f"Không đọc được vietlott.vn: {result.get('error')}")
    st.divider()
    st.write("File dữ liệu")
    st.code(f"{DEFAULT_DATASET_PATH.parent.name}/{DEFAULT_DATASET_PATH.name}", language="text")

records = cached_records(str(DEFAULT_DATASET_PATH))
manifest = load_manifest(DEFAULT_MANIFEST_PATH)
summary = summarize(records)
latest = latest_draw(records)

st.markdown(
    '<div class="source-strip">Nguồn chính: https://vietlott.vn/vi/trung-thuong/ket-qua-trung-thuong/winning-number-645</div>',
    unsafe_allow_html=True,
)

metric_cols = st.columns(4)
metric_cols[0].metric("Số kỳ", f"{summary.record_count:,}")
metric_cols[1].metric("Từ ngày", summary.first_date or "-")
metric_cols[2].metric("Mới nhất", summary.latest_date or "-")
metric_cols[3].metric("Tổ hợp", f"{TOTAL_COMBINATIONS:,}")

left, right = st.columns([1, 2])
with left:
    st.subheader(f"Kỳ mới nhất #{summary.latest_id or '-'}")
    render_balls(latest)
    if manifest:
        st.caption(f"SHA-256: {str(manifest.get('datasetSha256', ''))[:16]}...")

with right:
    hot = top_numbers(records, limit=6, ascending=False)
    cold = top_numbers(records, limit=6, ascending=True)
    st.subheader("Nhiệt độ dữ liệu")
    col_hot, col_cold = st.columns(2)
    col_hot.dataframe(hot[["number", "count", "delta_percent", "gap"]], hide_index=True, width="stretch")
    col_cold.dataframe(cold[["number", "count", "delta_percent", "gap"]], hide_index=True, width="stretch")

tab_data, tab_freq, tab_odds, tab_quality = st.tabs(["Dữ liệu", "Tần suất", "Xác suất", "Kiểm chứng"])

with tab_data:
    frame = records_to_frame(records)
    st.dataframe(frame.sort_values("date", ascending=False), hide_index=True, width="stretch")
    st.download_button(
        "Tải JSONL",
        data=serialize_jsonl(records),
        file_name="official_mega645.jsonl",
        mime="application/x-ndjson",
        width="stretch",
    )

with tab_freq:
    freq = frequency_frame(records)
    render_frequency_bars(freq)
    st.dataframe(
        freq.sort_values("count", ascending=False).assign(delta_percent=lambda df: df["delta_percent"].round(2)),
        hide_index=True,
        width="stretch",
    )

with tab_odds:
    ticket_count = st.slider("Số vé trong danh mục", min_value=1, max_value=30, value=10)
    odds = outcome_frame(ticket_count)
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Chi phí", format_vnd(ticket_count * TICKET_PRICE_VND))
    col_b.metric("EV giải cố định/vé", format_vnd(summary.fixed_prize_expectation_vnd))
    col_c.metric("Xác suất Jackpot tuyến tính", f"{ticket_count / TOTAL_COMBINATIONS:.8%}")
    st.dataframe(
        odds.assign(
            probability_single_ticket=lambda df: df["probability_single_ticket"].map("{:.10%}".format),
            probability_portfolio_linear=lambda df: df["probability_portfolio_linear"].map("{:.10%}".format),
        ),
        hide_index=True,
        width="stretch",
    )

with tab_quality:
    st.subheader("A/B nguồn official")
    ab = pd.DataFrame(
        [
            {
                "Phương án": "A. Bảng lịch sử",
                "Kết quả kiểm chứng": "16 kỳ / 2 trang, khớp trang chi tiết",
                "Vai trò": "Nguồn chính",
            },
            {
                "Phương án": "B. Trang chi tiết từng kỳ",
                "Kết quả kiểm chứng": "Chính xác nhưng chậm hơn rõ rệt",
                "Vai trò": "Đối chiếu",
            },
            {
                "Phương án": "C. Thông báo/PDF",
                "Kết quả kiểm chứng": "Có link official nhưng cần parse PDF",
                "Vai trò": "Audit phụ",
            },
        ]
    )
    st.dataframe(ab, hide_index=True, width="stretch")
    validation = {
        "records": summary.record_count,
        "unique_ids": len({record.id for record in records}),
        "duplicates": summary.record_count - len({record.id for record in records}),
        "latest": latest.to_dict() if latest else None,
        "manifest": manifest,
    }
    st.json(validation, expanded=False)
