# Dockerfile
FROM python:3.10-slim

WORKDIR /app

# 종속성 설치
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 앱 복사
COPY . .

# Flask 실행
ENV PORT 8080
CMD ["python", "app.py"]
