# 베이스 이미지
FROM python:3.10-slim

# 작업 디렉토리 설정
WORKDIR /app

# 코드 복사
COPY . /app

# 필요 패키지 설치
RUN pip install --no-cache-dir -r requirements.txt

# 포트 설정
EXPOSE 8080

# 앱 실행
CMD ["python", "app.py"]
