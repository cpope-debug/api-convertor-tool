import io
import csv
import os
import time
import base64
import requests
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
app = Flask(__name__)

# ✅ Enable universal CORS for testing
CORS(app)

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

    url = f"https://secure-wms.com/orders/{order_ref}?detail=All&itemdetail=All"
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        return jsonify({"error": f"Failed to fetch order: {response.text}"}), response.status_code

    try:
        order_data = response.json()
    except Exception:
        return jsonify({"error": "Invalid JSON response from API"}), 500

    return jsonify(order_data)

@app.route("/export-northline", methods=["GET"])
def export_northline():
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

    url = f"https://secure-wms.com/orders/{order_ref}?detail=All&itemdetail=All"
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        return jsonify({"error": f"Failed to fetch order: {response.text}"}), response.status_code

    try:
        order_data = response.json()
    except Exception:
        return jsonify({"error": "Invalid JSON response from API"}), 500

    # Prepare CSV
    output = io.StringIO()
    writer = csv.writer(output)
    header = [
        "AccountCode", "OrderDate", "RequiredDeliveryDate", "CustomerOrderNumber", "CustomerRefNumber",
        "Warehouse", "ReceiverName", "ReceiverStreetAddress1", "ReceiverSuburb", "ReceiverState",
        "ReceiverPostcode", "ReceiverContact", "ReceiverPhone", "ProductCode", "Qty", "Batch", "ExpiryDate",
        "SpecialInstructions"
    ]
    writer.writerow(header)

    account_code = "8UNI48"
    warehouse = "PERTH"
    order_date = order_data.get("ReadOnly", {}).get("CreationDate", "")
    customer_order_number = order_data.get("ReferenceNum", "")
    customer_ref_number = customer_order_number
    receiver = order_data.get("ShipTo", {})
    receiver_name = receiver.get("CompanyName", "")
    receiver_address = receiver.get("Address1", "")
    receiver_suburb = receiver.get("City", "")
    receiver_state = receiver.get("State", "")
    receiver_postcode = receiver.get("Zip", "")
    receiver_contact = receiver.get("Name", "")
    receiver_phone = receiver.get("PhoneNumber", "")
    special_instructions = order_data.get("Notes", "")

    for item in order_data.get("OrderItems", []):
        product_code = item.get("ItemIdentifier", {}).get("Sku", "")
        qty = item.get("Qty", "")

# ✅ Serial number mapping logic using logging
logging.basicConfig(level=logging.INFO)
logging.info(f'DEBUG Allocations: {item.get("ReadOnly", {}).get("Allocations", [])}')
serials = []
for alloc in item.get('ReadOnly', {}).get('Allocations', []):
    serial = alloc.get('detail', {}).get('serialNumber')
    if serial:
        serials.append(serial)
    else:
        serials.append(str(alloc.get('ReceiveItemId', '')))
        # ✅ One row per serial number
        if serials:
            for serial in serials:
                row = [
                    account_code, order_date, "", customer_order_number, customer_ref_number,
                    warehouse, receiver_name, receiver_address, receiver_suburb, receiver_state,
                    receiver_postcode, receiver_contact, receiver_phone, product_code, 1, serial, "",
                    special_instructions
                ]
                writer.writerow(row)
        else:
            # If no serials, write one row with qty
            row = [
                account_code, order_date, "", customer_order_number, customer_ref_number,
                warehouse, receiver_name, receiver_address, receiver_suburb, receiver_state,
                receiver_postcode, receiver_contact, receiver_phone, product_code, qty, "", "",
                special_instructions
            ]
            writer.writerow(row)

    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv', headers={"Content-Disposition": "attachment;filename=northline_export.csv"})

if __name__ == "__main__":
    app.run(debug=True)