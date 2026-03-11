from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import os
import requests
from bs4 import BeautifulSoup
import urllib3
import ssl
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# 1. SSL 경고 무시 설정
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 2. 학교 서버 접속을 위한 레거시 보안 어댑터 설정
class LegacyAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        # OpenSSL 보안 수준을 낮춰 옛날 방식의 학교 서버와 통신합니다.
        context = create_urllib3_context(ciphers='DEFAULT@SECLEVEL=1')
        # 레거시 서버 연결 허용 (AttributeError 방지를 위해 getattr 사용)
        legacy_flag = getattr(ssl, 'OP_LEGACY_SERVER_CONNECT', 0x4)
        context.options |= legacy_flag
        kwargs['ssl_context'] = context
        return super(LegacyAdapter, self).init_poolmanager(*args, **kwargs)

app = Flask(__name__)

# 헬스체크 및 24시간 깨우기용 경로
@app.route("/health", methods=["GET"])
@app.route("/keep-alive", methods=["GET"])
def health():
    return "OK", 200

def get_jbnu_menu(target_date):
    try:
        # 학교 서버 주소 (보안 이슈 발생 시 http://로 변경 가능)
        url = f"https://likehome.jbnu.ac.kr/home/main/inner.php?sMenu=B7300&date={target_date}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # 보안 설정을 적용한 세션 생성
        session = requests.Session()
        session.mount("https://", LegacyAdapter())
        
        # 학교 서버 접속
        response = session.get(url, headers=headers, verify=False, timeout=10)
        response.encoding = 'utf-8'
        html = response.text

        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        
        if not tables:
            return f"📅 {target_date}\n식단 정보를 찾을 수 없습니다."

        rows = tables[0].find_all("tr")
        date_obj = datetime.strptime(target_date, "%Y-%m-%d")
        weekday = date_obj.weekday()
        
        # 주말 처리
        if weekday > 4:
            return f"📅 {target_date}\n주말은 식단을 운영하지 않습니다."

        col_idx = weekday + 1
        
        def extract(row_idx):
            try:
                tds = rows[row_idx].find_all("td")
                if len(tds) > col_idx:
                    menu = tds[col_idx].get_text(strip=True, separator=" ")
                    return menu if len(menu) > 1 else "미운영"
                return "미운영"
            except:
                return
