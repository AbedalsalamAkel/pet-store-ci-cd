from flask import Flask, request, jsonify
from pymongo import MongoClient
import os
import requests
import random
import uuid

app = Flask(__name__)

# -----------------------
# MongoDB
# -----------------------
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://mongodb:27017")
client = MongoClient(MONGO_URL)
db = client.petorder
transactions = db.transactions

# -----------------------
# Constants
# -----------------------
OWNER_HEADER = "OwnerPC"
OWNER_VALUE = "LovesPetsL2M3n4"

PETSTORE1 = "http://petstore1:5001"
PETSTORE2 = "http://petstore2:5001"

# -----------------------
# Helpers
# -----------------------
def json_error(msg, code):
    return jsonify({"error": msg}), code


def require_json():
    if not request.is_json:
        return json_error("Expected application/json media type", 415)
    return None


def get_pet_type_id(store_url, pet_type):
    r = requests.get(f"{store_url}/pet-types")
    if r.status_code != 200:
        return None

    for pt in r.json():
        if pt["type"].lower() == pet_type.lower():
            return pt["id"]
    return None


def get_pets(store_url, pet_type_id):
    r = requests.get(f"{store_url}/pet-types/{pet_type_id}/pets")
    if r.status_code != 200:
        return []
    return r.json()


def delete_pet(store_url, pet_type_id, pet_name):
    return requests.delete(
        f"{store_url}/pet-types/{pet_type_id}/pets/{pet_name}"
    ).status_code

# -----------------------
# Routes
# -----------------------

@app.route("/purchases", methods=["POST"])
def create_purchase():
    # Content-Type
    resp = require_json()
    if resp:
        return resp

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return json_error("Malformed data", 400)

    purchaser = data.get("purchaser")
    pet_type = data.get("pet-type")
    store = data.get("store")
    pet_name = data.get("pet-name")

    if not isinstance(purchaser, str) or not isinstance(pet_type, str):
        return json_error("Malformed data", 400)

    if store is not None and store not in [1, 2]:
        return json_error("Malformed data", 400)

    if store is None and pet_name is not None:
        return json_error("Malformed data", 400)

    stores_to_check = []
    if store == 1:
        stores_to_check = [(1, PETSTORE1)]
    elif store == 2:
        stores_to_check = [(2, PETSTORE2)]
    else:
        stores_to_check = [(1, PETSTORE1), (2, PETSTORE2)]

    chosen = None

    for store_id, store_url in stores_to_check:
        pet_type_id = get_pet_type_id(store_url, pet_type)
        if not pet_type_id:
            continue

        pets = get_pets(store_url, pet_type_id)
        if not pets:
            continue

        if pet_name:
            for p in pets:
                if p["name"].lower() == pet_name.lower():
                    chosen = (store_id, store_url, pet_type_id, p["name"])
                    break
        else:
            p = random.choice(pets)
            chosen = (store_id, store_url, pet_type_id, p["name"])

        if chosen:
            break

    if not chosen:
        return json_error("No pet of this type is available", 400)

    store_id, store_url, pet_type_id, pet_name = chosen

    status = delete_pet(store_url, pet_type_id, pet_name)
    if status != 204:
        return json_error("No pet of this type is available", 400)

    purchase_id = str(uuid.uuid4())

    transaction = {
        "purchaser": purchaser,
        "pet-type": pet_type,
        "store": store_id,
        "pet-name": pet_name,
        "purchase-id": purchase_id,
    }

    transactions.insert_one(transaction)

    return jsonify(transaction), 201


@app.route("/transactions", methods=["GET"])
def list_transactions():
    if request.headers.get(OWNER_HEADER) != OWNER_VALUE:
        return "", 401

    query = {}
    for k, v in request.args.items():
        if k == "store":
            try:
                query[k] = int(v)
            except ValueError:
                continue
        else:
            query[k] = v

    result = list(transactions.find(query, {"_id": 0}))
    return jsonify(result), 200


@app.route("/kill", methods=["GET"])
def kill():
    os._exit(1)
    
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)
