# Deployment: Mega 6/45 Python Lab

Date: 2026-09-11

Winner: **Streamlit Community Cloud** (variant A).

Official sources used for classification:

- [Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud)
- [Prep and deploy](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app)
- [Deploy dialog, Python 3.12 default](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
- [File organization](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization)
- [App dependencies / requirements.txt](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)
- [Streamlit Docker tutorial](https://docs.streamlit.io/deploy/tutorials/docker)
- [Hugging Face Streamlit Spaces](https://huggingface.co/docs/hub/en/spaces-sdks-streamlit) (Streamlit SDK deprecated 2025-04-30; use Docker)
- [Hugging Face Docker Spaces](https://huggingface.co/docs/hub/spaces-sdks-docker)
- [Render web services / PORT on 0.0.0.0](https://render.com/docs/web-services)
- [stlite](https://stlite.net/) / [whitphx/stlite](https://github.com/whitphx/stlite)
- [Cloud Run Streamlit quickstart](https://docs.cloud.google.com/run/docs/quickstarts/build-and-deploy/deploy-python-streamlit-service)
- [Vercel Docker Python](https://vercel.com/kb/guide/vercel-docker-python-apps) — rejected for identity risk and non-native Streamlit runtime

## Comparison

| Option | Browser UI | Deploy from GitHub | Code change | Local JSONL | Public URL | Vercel/GitHub identity risk | MCP browser test |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A. Streamlit Community Cloud | Native Streamlit | One-click from repo | None beyond `requirements.txt` + `.streamlit/config.toml` | Copied with the repo | `*.streamlit.app` | No Vercel. GitHub OAuth once to Streamlit | Same local `streamlit run` |
| B. Hugging Face Docker / Render / Cloud Run | Streamlit in a container | GitHub or extra remote | Dockerfile + port bind | Copied into image | `*.hf.space` / `*.onrender.com` / Cloud Run URL | HF is a second identity; Render still uses GitHub OAuth | Needs Docker or extra account |
| C. stlite (Wasm / GitHub Pages) | In-browser Streamlit | GitHub Pages | Rewrite networking and storage | No durable write | GitHub Pages | Low | UI can load, crawl cannot |
| Vercel Functions | No (Streamlit is a long-lived WebSocket server) | Yes | Large rewrite | Ephemeral | `*.vercel.app` | High — explicitly avoided | N/A |
| GitHub Pages static only | No Python server | Yes | Rewrite to JS | No | `*.github.io` | Low | N/A |

## A/B test

Harness: `python scripts/ab_deploy_runtime.py` on 2026-09-11, Python 3.14.4, Windows.

| Variant | What was run | Result |
| --- | --- | --- |
| A | `streamlit run streamlit_app.py --server.headless=true --server.port=8501 --server.address=0.0.0.0` then `GET /_stcore/health` and `GET /` | **PASS** — health `ok` in 1043 ms, UI 200 with Streamlit marker (5381 bytes) |
| B | Same server on port 8510 (Render `$PORT` / Docker bind model). Docker Engine is not installed on the QA machine, so the image was not built. | **PASS** (entrypoint only) — health `ok` in 1019 ms, UI 200. Image build not executed. |
| C | `GET https://vietlott.vn/vi/trung-thuong/ket-qua-trung-thuong/winning-number-645` and inspect `Access-Control-Allow-Origin` | **FAIL** — HTTP 200, 224644 bytes, `Access-Control-Allow-Origin` is missing. Pyodide/stlite cannot crawl vietlott.vn from the browser. |

Winner A because it is the only option that stays on Streamlit, deploys from this GitHub repo with almost no code change, ships `data/official_mega645.jsonl`, gives a public URL, avoids Vercel, and is identical to the MCP local browser test.

## How to publish

1. `share.streamlit.io` → Create app → Yup, I have an app.
2. Repo `howtodonextcom-art/260911-AI-Research-Lab-Python`, branch `main`, file `streamlit_app.py`.
3. Advanced settings: Python **3.12** (platform default). `runtime.txt` is ignored on Community Cloud.
4. Optional subdomain: `vietlott-mega645`.

Filesystem note: Community Cloud disks are ephemeral. The committed JSONL is the durable dataset. The in-app "Cập nhật từ Vietlott" button still crawls vietlott.vn for the running session; reboot returns to the committed file. Re-run `python -m vietlott_mega645 sync --all --delay 0.2` locally and push to persist new draws.

## Test results (2026-09-11)

| Gate | Command / method | Result |
| --- | --- | --- |
| Unit | `python -m unittest discover -s tests` | PASS — 15 tests, 0.023s |
| CLI smoke | `python -m vietlott_mega645 latest --pretty` | PASS — `{"date":"2026-09-11","id":"01561","result":[14,18,20,21,26,27]}` |
| A/B runtime | `python scripts/ab_deploy_runtime.py` | PASS A+B, FAIL C (expected) |
| Streamlit MCP | `http://127.0.0.1:8501` — metrics, four tabs, live Vietlott sync | PASS — 1,561 kỳ, sync message `Đã cập nhật: 1561 kỳ, mới nhất #01561` |
| Public URL MCP | Streamlit Community Cloud create-app | Pending one GitHub OAuth at share.streamlit.io (no Vercel) |

## Local commands

```bash
python -m unittest discover -s tests
python -m vietlott_mega645 latest --pretty
python scripts/ab_deploy_runtime.py
streamlit run streamlit_app.py
```
