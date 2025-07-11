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

if not os.path.exists("user_stocks.xlsx"):
    pd.DataFrame(columns=["id", "symbol", "quantity"]).to_excel("user_stocks.xlsx", index=False)

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
    user_stocks = pd.read_excel("user_stocks.xlsx")

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

    user_stock_row = user_stocks[(user_stocks["id"] == data["id"]) & (user_stocks["symbol"] == symbol)]
    current_qty = int(user_stock_row.iloc[0]["quantity"]) if not user_stock_row.empty else 0

    if action == "buy":
        if balance < total:
            return jsonify(msg="잔액 부족")
        users.loc[users["id"] == data["id"], "balance"] = balance - total
        stocks.loc[stocks["symbol"] == symbol, "price"] = price * 1.01  # 가격 상승
        # 보유량 증가
        if user_stock_row.empty:
            user_stocks = pd.concat([user_stocks, pd.DataFrame([{
                "id": data["id"], "symbol": symbol, "quantity": qty
            }])], ignore_index=True)
        else:
            user_stocks.loc[(user_stocks["id"] == data["id"]) & (user_stocks["symbol"] == symbol), "quantity"] = current_qty + qty
    else:  # sell
        if user_stock_row.empty:
            return jsonify(msg="보유 내역이 없습니다.")
        if current_qty < qty:
            return jsonify(msg="보유 주식 수량 부족")
        users.loc[users["id"] == data["id"], "balance"] = balance + total
        stocks.loc[stocks["symbol"] == symbol, "price"] = price * 0.99  # 가격 하락
        # 보유량 감소
        user_stocks.loc[(user_stocks["id"] == data["id"]) & (user_stocks["symbol"] == symbol), "quantity"] = current_qty - qty

    users.to_excel("users.xlsx", index=False)
    stocks.to_excel("stock_data.xlsx", index=False)
    user_stocks.to_excel("user_stocks.xlsx", index=False)
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
        loan_val = float(loan_row.iloc[0]["loan"]) if not loan_row.empty and not pd.isna(loan_row.iloc[0]["loan"]) else 0.0

        # 이미 대출이 있으면 중복 대출 불가
        if loan_val > 0:
            return jsonify(msg="기존 대출이 남아있으면 추가 대출이 불가합니다.")

        # 대출 한도: 잔액의 150%까지
        max_loan = balance * 1.5
        if amount > max_loan:
            return jsonify(msg=f"대출 한도 초과: 최대 {int(max_loan)}원까지 대출 가능합니다.")

        # loan_row가 없으면 새로 추가
        if loan_row.empty:
            loans = pd.concat([loans, pd.DataFrame([{"id": data["id"], "loan": amount}])], ignore_index=True)
        else:
            loans.loc[loans["id"] == data["id"], "loan"] = amount

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

@app.route("/api/user_stocks/<id>", methods=["GET"])
def user_stocks(id):
    df = pd.read_excel("user_stocks.xlsx")
    user_stocks = df[df["id"] == id][["symbol", "quantity"]]
    # 딕셔너리 리스트로 반환
    stocks_list = user_stocks.to_dict(orient="records")
    return jsonify(stocks=stocks_list)

def update_stock_prices():
    global delisted_stocks
    while True:
        try:
            stocks = pd.read_excel("stock_data.xlsx")
            now = time.time()

            # 기존 종목 가격 변동
            for idx, row in stocks.iterrows():
                change = random.uniform(-0.10, 0.10)
                new_price = max(1, row["price"] * (1 + change))
                stocks.at[idx, "price"] = round(new_price, 2)

            # 상장폐지 종목 추적 및 폐지
            to_delist = stocks[stocks["price"] <= 150]["symbol"].tolist()
            for symbol in to_delist:
                if symbol not in delisted_stocks:
                    # 폐지시각과 초기가격 기록
                    init_price = initial_prices.get(symbol, 200.0)
                    delisted_stocks[symbol] = (now, init_price)
            stocks = stocks[stocks["price"] > 150].reset_index(drop=True)

            # 2분(120초) 지난 상장폐지 종목 재상장
            relist = []
            for symbol, (delist_time, init_price) in list(delisted_stocks.items()):
                if now - delist_time >= 120:
                    # 초기가격 ±500 내 랜덤 가격
                    new_price = round(random.uniform(init_price - 500, init_price + 500), 2)
                    new_price = max(1, new_price)
                    stocks = pd.concat([stocks, pd.DataFrame([{"symbol": symbol, "price": new_price}])], ignore_index=True)
                    relist.append(symbol)
            for symbol in relist:
                del delisted_stocks[symbol]

            stocks.to_excel("stock_data.xlsx", index=False)
            shutil.copy("stock_data.xlsx", os.path.join("static", "stock_data.xlsx"))
        except Exception as e:
            print("Stock price update error:", e)
        time.sleep(5)

INTEREST_RATE = 0.01  # 1% (원하는 이자율로 조정)
INTEREST_INTERVAL = 60  # 초 단위, 예: 60초마다 이자 부과

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

# 상장폐지 종목 추적: {symbol: (폐지시각, 초기가격)}
delisted_stocks = {}
initial_prices = {"AAPL": 150.0, "TSLA": 200.0, "GOOG": 100.0}  # 필요시 확장

# 서버 시작 시 스레드로 주식 가격 변동 시작
threading.Thread(target=update_stock_prices, daemon=True).start()
# 서버 시작 시 이자 부과 스레드도 시작
threading.Thread(target=apply_loan_interest, daemon=True).start()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
