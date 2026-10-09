FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git curl build-essential && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --no-cache-dir --upgrade pip uv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN mkdir -p /app/vendor && git clone --depth 1 https://github.com/pingqLIN/Image-to-Raw.git /app/vendor/Image-to-Raw
RUN uv sync --project /app/vendor/Image-to-Raw
COPY app.py .
COPY static ./static
ENV IMAGE2DNG_PROJECT=/app/vendor/Image-to-Raw
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
