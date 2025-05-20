from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pandas as pd
import os
import random
import json
from tinyec import registry
import secrets
import threading
import time
import shutil
import datetime

app = Flask(__name__)
CORS(app, supports_credentials=True)

curve = registry.get_curve('secp256r1')

# 파일 초기화
if not os.path.exists("users.xlsx"):
    pd.DataFrame(columns=["id", "pw", "balance", "private_key", "public_key"]).to_excel("users.xlsx", index=False)

if not os.path.exists("loans.xlsx"):
    pd.DataFrame(columns=["id", "loan"]).to_excel("loans.xlsx", index=False)

if not os.path.exists("transactions.xlsx"):
    pd.DataFrame(columns=["from", "to", "amount"]).to_excel("transactions.xlsx", index=False)

if not os.path.exists("stock_data.xlsx"):
    df = pd.DataFrame({
        "symbol": ["AAPL", "TSLA", "GOOG"],
        "price": [150.0, 200.0, 100.0]
    })
    df.to_excel("stock_data.xlsx", index=False)

# static 폴더에 stock_data.xlsx 복사
if not os.path.exists("static"):
    os.makedirs("static")
shutil.copy("stock_data.xlsx", os.path.join("static", "stock_data.xlsx"))

def generate_key_pair():
    private_key = secrets.randbelow(curve.field.n)
    public_key = private_key * curve.g
    return private_key, public_key

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api/register", methods=["POST"])
def register():
    try:
        data = request.json
        user_df = pd.read_excel("users.xlsx")
        loan_df = pd.read_excel("loans.xlsx")

        if data["id"] in user_df["id"].values:
            return jsonify(msg="이미 존재하는 ID입니다.")

        priv, pub = generate_key_pair()
        pub_str = f"{pub.x},{pub.y}"
        new_user = {
            "id": data["id"],
            "pw": data["pw"],
            "balance": 100000,
            "private_key": priv,
            "public_key": pub_str
        }
        new_loan = {
            "id": data["id"],
            "loan": 0
        }

        user_df = pd.concat([user_df, pd.DataFrame([new_user])], ignore_index=True)
        loan_df = pd.concat([loan_df, pd.DataFrame([new_loan])], ignore_index=True)
        user_df.to_excel("users.xlsx", index=False)
        loan_df.to_excel("loans.xlsx", index=False)
        return jsonify(msg="회원가입 성공")

    except Exception as e:
        print("Register error:", e)
        return jsonify(error=str(e)), 500

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    user_df = pd.read_excel("users.xlsx")
    user = user_df[(user_df["id"] == data["id"]) & (user_df["pw"] == data["pw"])]
    if not user.empty:
        return jsonify(msg="로그인 성공")
    else:
        return jsonify(msg="로그인 실패")

@app.route("/api/balance/<id>", methods=["GET"])
def balance(id):
    user_df = pd.read_excel("users.xlsx")
    loan_df = pd.read_excel("loans.xlsx")
    user = user_df[user_df["id"] == id]
    loan = loan_df[loan_df["id"] == id]
    if not user.empty:
        balance_val = float(user.iloc[0]["balance"]) if not pd.isna(user.iloc[0]["balance"]) else 0.0
        loan_val = float(loan.iloc[0]["loan"]) if not loan.empty and not pd.isna(loan.iloc[0]["loan"]) else 0.0
        return jsonify(
            balance=int(balance_val),
            loan=float(loan_val)
        )
    else:
        return jsonify(msg="사용자 없음")

@app.route("/api/send", methods=["POST"])
def send():
    data = request.json
    users = pd.read_excel("users.xlsx")

    sender = users[users["id"] == data["from"]]
    receiver = users[users["id"] == data["to"]]

    if sender.empty or receiver.empty:
        return jsonify(msg="송금 대상이 올바르지 않습니다.")

    amount = float(data["amount"])
    if float(sender.iloc[0]["balance"]) < amount:
        return jsonify(msg="잔액 부족")

    users.loc[users["id"] == data["from"], "balance"] = float(sender.iloc[0]["balance"]) - amount
    users.loc[users["id"] == data["to"], "balance"] = float(receiver.iloc[0]["balance"]) + amount
    users.to_excel("users.xlsx", index=False)

    tx_df = pd.read_excel("transactions.xlsx")
    tx_df = pd.concat([tx_df, pd.DataFrame([{
        "from": data["from"],
        "to": data["to"],
        "amount": amount
    }])], ignore_index=True)
    tx_df.to_excel("transactions.xlsx", index=False)

    return jsonify(msg="송금 완료")

@app.route("/api/stock/trade", methods=["POST"])
def trade_stock():
    data = request.json
    users = pd.read_excel("users.xlsx")
    stocks = pd.read_excel("stock_data.xlsx")

    user = users[users["id"] == data["id"]]
    if user.empty:
        return jsonify(msg="사용자 없음")

    symbol = data["symbol"]
    action = data["action"]
    qty = int(data["quantity"])
    stock = stocks[stocks["symbol"] == symbol]
    if stock.empty:
        return jsonify(msg="종목 없음")

    price = float(stock.iloc[0]["price"])
    total = price * qty
    balance = float(user.iloc[0]["balance"])

    if action == "buy":
        if balance < total:
            return jsonify(msg="잔액 부족")
        users.loc[users["id"] == data["id"], "balance"] = balance - total
        stocks.loc[stocks["symbol"] == symbol, "price"] = price * 1.01  # 가격 상승
    else:
        users.loc[users["id"] == data["id"], "balance"] = balance + total
        stocks.loc[stocks["symbol"] == symbol, "price"] = price * 0.99  # 가격 하락

    users.to_excel("users.xlsx", index=False)
    stocks.to_excel("stock_data.xlsx", index=False)
    return jsonify(msg=f"{action.upper()} 성공")

@app.route("/api/loan", methods=["POST"])
def loan():
    try:
        data = request.json
        users = pd.read_excel("users.xlsx")
        loans = pd.read_excel("loans.xlsx")
        user = users[users["id"] == data["id"]]
        loan_row = loans[loans["id"] == data["id"]]

        if user.empty:
            return jsonify(msg="사용자 없음")

        amount = float(data["amount"])
        balance = float(user.iloc[0]["balance"]) if not pd.isna(user.iloc[0]["balance"]) else 0.0

        # loan_row가 없으면 새로 추가
        if loan_row.empty:
            loan_val = 0.0
            loans = pd.concat([loans, pd.DataFrame([{"id": data["id"], "loan": amount}])], ignore_index=True)
        else:
            loan_val = float(loan_row.iloc[0]["loan"]) if not pd.isna(loan_row.iloc[0]["loan"]) else 0.0
            loans.loc[loans["id"] == data["id"], "loan"] = loan_val + amount

        users.loc[users["id"] == data["id"], "balance"] = balance + amount
        users.to_excel("users.xlsx", index=False)
        loans.to_excel("loans.xlsx", index=False)
        return jsonify(msg="대출 완료")
    except Exception as e:
        print("Loan error:", e)
        return jsonify(msg="서버 오류", error=str(e)), 500

@app.route("/api/repay_loan", methods=["POST"])
def repay_loan():
    data = request.json
    users = pd.read_excel("users.xlsx")
    loans = pd.read_excel("loans.xlsx")

    user = users[users["id"] == data["id"]]
    loan_row = loans[loans["id"] == data["id"]]

    if user.empty:
        return jsonify(msg="사용자 없음")

    amount = float(data["amount"])
    balance = float(user.iloc[0]["balance"]) if not pd.isna(user.iloc[0]["balance"]) else 0.0
    loan_val = float(loan_row.iloc[0]["loan"]) if not loan_row.empty and not pd.isna(loan_row.iloc[0]["loan"]) else 0.0

    if amount > loan_val:
        return jsonify(msg="상환 금액이 대출 잔액을 초과합니다.")
    if balance < amount:
        return jsonify(msg="잔액 부족")

    users.loc[users["id"] == data["id"], "balance"] = balance - amount
    if not loan_row.empty:
        loans.loc[loans["id"] == data["id"], "loan"] = loan_val - amount
    else:
        loans = pd.concat([loans, pd.DataFrame([{"id": data["id"], "loan": 0.0}])], ignore_index=True)

    users.to_excel("users.xlsx", index=False)
    loans.to_excel("loans.xlsx", index=False)
    return jsonify(msg="대출 상환 완료")

def update_stock_prices():
    while True:
        try:
            stocks = pd.read_excel("stock_data.xlsx")
            # 각 주식 가격을 -5%~+5% 랜덤 변동
            for idx, row in stocks.iterrows():
                change = random.uniform(-0.05, 0.05)
                new_price = max(1, row["price"] * (1 + change))
                stocks.at[idx, "price"] = round(new_price, 2)
            stocks.to_excel("stock_data.xlsx", index=False)
            shutil.copy("stock_data.xlsx", os.path.join("static", "stock_data.xlsx"))  # static 폴더도 갱신
        except Exception as e:
            print("Stock price update error:", e)
        time.sleep(120)  # 5초마다 가격 갱신

INTEREST_RATE = 0.58  # 5.8% (원하는 이자율로 조정)
INTEREST_INTERVAL = 120  # 초 단위

def apply_loan_interest():
    while True:
        try:
            loans = pd.read_excel("loans.xlsx")
            # 모든 사용자 대출에 대해 이자 부과
            for idx, row in loans.iterrows():
                loan = float(row["loan"]) if not pd.isna(row["loan"]) else 0.0
                if loan > 0:
                    new_loan = loan * (1 + INTEREST_RATE)
                    loans.at[idx, "loan"] = round(new_loan, 2)
            loans.to_excel("loans.xlsx", index=False)
        except Exception as e:
            print("Loan interest error:", e)
        time.sleep(INTEREST_INTERVAL)

# 서버 시작 시 스레드로 주식 가격 변동 시작
threading.Thread(target=update_stock_prices, daemon=True).start()
# 서버 시작 시 이자 부과 스레드도 시작
threading.Thread(target=apply_loan_interest, daemon=True).start()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
