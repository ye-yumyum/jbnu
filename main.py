from flask import Flask, request, jsonify
import urllib.request
import ssl
from datetime import datetime, timedelta
import re
import json
import os
import time
from bs4 import BeautifulSoup

app = Flask(__name__)

# --- 기존 로직 (식단 및 헬스체크) ---

@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

MENU_CACHE = {}
MENU_CACHE_TTL_SECONDS = 300
MENU_ERROR_CACHE_TTL_SECONDS = 30

def _cache_get(key: str):
    item = MENU_CACHE.get(key)
    if not item or item["expires_at"] < time.time():
        MENU_CACHE.pop(key, None)
        return None
    return item["value"]

def _cache_set(key: str, value: str, ttl_seconds: int):
    MENU_CACHE[key] = {"expires_at": time.time() + ttl_seconds, "value": value}

def get_jbnu_menu(target_date):
    korea_now = datetime.utcnow() + timedelta(hours=9)
    today_str = korea_now.strftime("%Y-%m-%d")

    if not target_date or any(x in str(target_date).lower() for x in ["{{", "sys", "none"]):
        target_date = today_str

    target_date = str(target_date).split("T")[0]
    try:
        date_obj = datetime.strptime(target_date, "%Y-%m-%d")
    except:
        target_date = today_str
        date_obj = datetime.strptime(target_date, "%Y-%m-%d")

    cached = _cache_get(target_date)
    if cached is not None:
        return cached

    url = f"https://likehome.jbnu.ac.kr/home/main/inner.php?sMenu=B7300&date={target_date}"
    context = ssl._create_unverified_context()
    context.set_ciphers("DEFAULT@SECURITY=1")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=context, timeout=2) as response:
            html = response.read().decode("utf-8", errors="ignore")

        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            result = f"📅 {target_date}\n식단표를 찾을 수 없습니다."
