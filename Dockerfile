FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium

COPY LICENSE NOTICE ./
COPY app.py .
COPY get_session.py .
COPY virel ./virel

ENV PORT=8001 CHROME_PROFILE_DIR=/app/runtime/browser-profile HEADLESS=true

EXPOSE 8001

CMD ["python", "app.py"]
