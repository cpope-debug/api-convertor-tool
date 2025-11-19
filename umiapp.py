import os
import time
import base64
import csv
import requests
from datetime import datetime, timedelta
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
        "tpl": tpl_key,
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

    order_id = order_ref
    url = f"https://secure-wms.com/orders/{order_id}?detail=All&itemdetail=All"
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        return jsonify({"error": f"Failed to fetch order: {response.text}"}), response.status_code

    try:
        order_data = response.json()
    except Exception:
        return jsonify({"error": "Invalid JSON response from API"}), 500

    # Extract reference number and transaction ID if available
    customer_order_number = order_data.get("name", "N/A")  # Reference Number
    customer_ref_number = str(order_data.get("id", order_id))  # Transaction ID

    # Prepare CSV file
    csv_file = f"/tmp/{order_id}_northline.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        # Northline headers
        writer.writerow([
            "AccountCode","OrderDate","RequiredDeliveryDate","CustomerOrderNumber","CustomerRefNumber",
            "Warehouse","ReceiverName","ReceiverStreetAddress1","ReceiverSuburb","ReceiverSuburb",
            "ReceiverState","ReceiverPostcode","ReceiverContact","ReceiverPhone","ProductCode","Qty","Batch","ExpiryDate","SpecialInstructions"
        ])

        # Default values
        account_code = "8UNI48"
        warehouse = "PERTH"
        order_date = datetime.now().strftime("%Y%m%d")
        required_date = (datetime.now() + timedelta(days=1)).strftime("%Y%m%d")
        receiver_name = "TEST BUSINESS"
        receiver_address = "100 TEST STREET"
        receiver_suburb = "BUNDABERG"
        receiver_state = "QLD"
        receiver_postcode = "4670"
        receiver_contact = "TEXT TESTER"
        receiver_phone = "0411111111"
        special_instructions = "Please call test tester on 0411111111 to book a timeslot"

        # Loop through packages and contents
        for package in order_data.get("packages", []):
            for content in package.get("packageContents", []):
                sku = content.get("lotNumber", "N/A")
                qty = content.get("qty", 0)
                batch = content.get("serialNumber", "")
                expiry_date = ""  # If available, map from API

                writer.writerow([
                    account_code, order_date, required_date, customer_order_number, customer_ref_number,
                    warehouse, receiver_name, receiver_address, receiver_suburb, receiver_suburb,
                    receiver_state, receiver_postcode, receiver_contact, receiver_phone,
                    sku, qty, batch, expiry_date, special_instructions
                ])

    return send_file(csv_file, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)