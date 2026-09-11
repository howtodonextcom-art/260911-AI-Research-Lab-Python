# Official Streamlit Docker tutorial, adapted to copy this repo
# instead of cloning streamlit-example:
# https://docs.streamlit.io/deploy/tutorials/docker
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md streamlit_app.py ./
COPY vietlott_mega645 ./vietlott_mega645
COPY data ./data
COPY .streamlit ./.streamlit

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
