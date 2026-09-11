# vietlott-mega645

Proof-of-concept Python package for reading public Vietlott Mega 6/45 draw data.

It supports two paths:

- Latest/detail pages, for example `https://vietlott.vn/vi/trung-thuong/ket-qua-trung-thuong/645?id=01561&nocatche=1`.
- The public historical table behind `winning-number-645`, including its AjaxPro pagination response.

This is intentionally conservative: no login, no CAPTCHA bypass, no browser automation, no hidden credential, bounded response size, and a configurable delay when iterating pages.

## Run

```bash
cd "D:\2026\260911-AI-Research Lab-Python"
python -m unittest discover -s tests
python -m vietlott_mega645 latest
python -m vietlott_mega645 history --max-pages 2 --output sample.jsonl
python -m vietlott_mega645 sync --all --delay 0.2
streamlit run streamlit_app.py
```

Local UI: [http://127.0.0.1:8501](http://127.0.0.1:8501)

## Deploy

Chosen path: **Streamlit Community Cloud** from GitHub `main`. Details, A/B results, and rejected options are in [DEPLOYMENT.md](DEPLOYMENT.md).

1. Push this repository to GitHub (already: `howtodonextcom-art/260911-AI-Research-Lab-Python`).
2. Open [https://share.streamlit.io](https://share.streamlit.io) and click **Create app**.
3. Repository `howtodonextcom-art/260911-AI-Research-Lab-Python`, branch `main`, main file `streamlit_app.py`.
4. Advanced settings: Python **3.12**.
5. Optional custom subdomain, for example `vietlott-mega645`.

Public URL shape: `https://<subdomain>.streamlit.app`

The JSONL output uses the same minimal shape as the existing app dataset:

```json
{"date":"2026-09-11","id":"01561","result":[14,18,20,21,26,27]}
```

## Source strategy

The package uses the public Vietlott Mega 6/45 history page as its main source:

`https://vietlott.vn/vi/trung-thuong/ket-qua-trung-thuong/winning-number-645`

The history table is much faster than crawling every detail page. Detail pages
remain useful as a spot-check source for individual draw ids.
