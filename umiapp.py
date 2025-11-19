import os
import time
import base64
import csv
import requests
from flask import Flask, request, jsonify, send_file
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
app = Flask(__name__)

cached_token = None
token_expiry = 0

def get_token():
    global cached_token, token_expiry
    if cached_token and time.time() < token_expiry:
        return cached_token

    client_id = os.getenv("EXTENSIV_CLIENT_ID")
    client_secret = os.getenv("EXTENSIV_CLIENT_SECRET")
    tpl_key = os.getenv("EXTENSIV_TPL_KEY")

    if not client_id or not client_secret or not tpl_key:
        raise ValueError("Missing Extensiv API credentials in environment variables")

    credentials = f"{client_id}:{client_secret}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")

    headers = {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "grant_type": "client_credentials",
        "tpl": f"{tpl_key}",
        "user_login_id": "4"
    }

    response = requests.post("https://secure-wms.com/AuthServer/api/Token", headers=headers, data=data)
    response.raise_for_status()
    token_data = response.json()

    cached_token = token_data["access_token"]
    token_expiry = time.time() + token_data.get("expires_in", 3600) - 60
    return cached_token

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/get-order", methods=["GET"])
def get_order():
    order_ref = request.args.get("reference")
    if not order_ref:
        return jsonify({"error": "Order reference is required"}), 400

    try:
        token = get_token()
    except Exception as e:
        return jsonify({"error": f"Token error: {str(e)}"}), 500

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    url = f"https://secure-wms.com/orders?referenceNum={order_ref}"
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        return jsonify({"error": f"Failed to fetch order: {response.text}"}), response.status_code

    try:
        order_data = response.json()
    except Exception:
        return jsonify({"error": "Invalid JSON response from API"}), 500

    if "orderItems" not in order_data or not order_data.get("orderItems"):
        return jsonify({"error": "No order items found"}), 404

    csv_file = f"/tmp/{order_ref}_northline.csv"
    try:
        with open(csv_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["OrderNumber", "SKU", "Qty"])
            for item in order_data.get("orderItems", []):
                writer.writerow([
                    order_data.get("referenceNum", "N/A"),
                    item["itemIdentifier"]["sku"],
                    item["qty"]
                ])
    except Exception as e:
        return jsonify({"error": f"Failed to write CSV: {str(e)}"}), 500

    return send_file(csv_file, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)