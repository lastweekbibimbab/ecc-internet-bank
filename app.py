from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pandas as pd
import os
import random
import json
from tinyec import registry
import secrets

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

curve = registry.get_curve('secp256r1')

# 파일 초기화
if not os.path.exists("users.xlsx"):
    pd.DataFrame(columns=["id", "pw", "private_key", "public_key", "balance"]).to_excel("users.xlsx", index=False)

if not os.path.exists("transactions.xlsx"):
    pd.DataFrame(columns=["from", "to", "amount"]).to_excel("transactions.xlsx", index=False)

if not os.path.exists("stock_data.xlsx"):
    df = pd.DataFrame({
        "symbol": ["AAPL", "TSLA", "GOOG"],
        "price": [150.0, 200.0, 100.0]
    })
    df.to_excel("stock_data.xlsx", index=False)

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

        if data["id"] in user_df["id"].values:
            return jsonify(msg="이미 존재하는 ID입니다.")

        priv, pub = generate_key_pair()
        pub_str = f"{pub.x},{pub.y}"
        new_user = {
            "id": data["id"],
            "pw": data["pw"],
            "private_key": priv,
            "public_key": pub_str,
            "balance": 100000
        }

        user_df = pd.concat([user_df, pd.DataFrame([new_user])], ignore_index=True)
        user_df.to_excel("users.xlsx", index=False)
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
    user = user_df[user_df["id"] == id]
    if not user.empty:
        return jsonify(balance=int(user.iloc[0]["balance"]))
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
    if sender.iloc[0]["balance"] < amount:
        return jsonify(msg="잔액 부족")

    users.loc[users["id"] == data["from"], "balance"] -= amount
    users.loc[users["id"] == data["to"], "balance"] += amount
    users.to_excel("users.xlsx", index=False)

    tx_df = pd.read_excel("transactions.xlsx")
    tx_df = tx_df.append({
        "from": data["from"],
        "to": data["to"],
        "amount": amount
    }, ignore_index=True)
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
        users.loc[users["id"] == data["id"], "balance"] -= total
        stocks.loc[stocks["symbol"] == symbol, "price"] *= 1.01  # 가격 상승
    else:
        users.loc[users["id"] == data["id"], "balance"] += total
        stocks.loc[stocks["symbol"] == symbol, "price"] *= 0.99  # 가격 하락

    users.to_excel("users.xlsx", index=False)
    stocks.to_excel("stock_data.xlsx", index=False)
    return jsonify(msg=f"{action.upper()} 성공")

@app.route("/api/loan", methods=["POST"])
def loan():
    data = request.json
    users = pd.read_excel("users.xlsx")
    user = users[users["id"] == data["id"]]

    if user.empty:
        return jsonify(msg="사용자 없음")

    amount = float(data["amount"])
    users.loc[users["id"] == data["id"], "balance"] += amount
    users.to_excel("users.xlsx", index=False)
    return jsonify(msg="대출 완료")

if __name__ == "__main__":
    app.run(debug=True, port=5000)
