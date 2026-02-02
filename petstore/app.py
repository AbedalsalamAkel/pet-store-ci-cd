# app.py
from flask import Flask, request, jsonify, send_from_directory
import os
import requests

from models import (
    pet_types,
    pets_by_type,
    generate_pet_type_id,
    pet_type_exists_by_name,
    register_pet_type,
    remove_pet_type,
    get_pets_for_type,
    add_pet,
    delete_pet,
    pet_to_json,
    parse_date,
    compare_dates,
    ensure_pictures_folder,
)
from ninja_client import fetch_pet_type_data, NinjaApiError, NinjaNotFound

app = Flask(__name__)

ensure_pictures_folder()

# -----------------------
# Helpers for responses
# -----------------------

def json_error(message, status):
    return jsonify({"error": message}), status


def server_error_from_ninja(status_code):
    return jsonify({"server error": f"API response code {status_code}"}), 500


def require_json():
    if not request.is_json:
        return json_error("Expected application/json media type", 415)
    return None


# -----------------------
# /pet-types
# -----------------------

@app.route("/pet-types", methods=["POST"])
def create_pet_type():
    # Content-Type check
    resp = require_json()
    if resp:
        return resp

    data = request.get_json(silent=True)
    if not data or "type" not in data or not isinstance(data["type"], str):
        return json_error("Malformed data", 400)

    type_name = data["type"]
    if pet_type_exists_by_name(type_name):
        return json_error("Malformed data", 400)  # already exists

    # call Ninja Animals API
    try:
        info = fetch_pet_type_data(type_name)
    except NinjaNotFound:
        # Ninja does not recognize this type -> 400
        return json_error("Malformed data", 400)
    except NinjaApiError as e:
        # unexpected Ninja error -> 500
        return server_error_from_ninja(e.status_code)
    except Exception:
        # any other unexpected issue
        return jsonify({"server error": "API call failed"}), 500

    pet_type_id = generate_pet_type_id()
    pet_type_obj = {
        "id": pet_type_id,
        "type": type_name,
        "family": info["family"],
        "genus": info["genus"],
        "attributes": info["attributes"],
        "lifespan": info["lifespan"],
        "pets": [],
    }

    register_pet_type(pet_type_obj)

    return jsonify(pet_type_obj), 201


@app.route("/pet-types", methods=["GET"])
def list_pet_types():
    # Start with all pet-types
    result = list(pet_types.values())

    # query fields: id, type, family, genus, lifespan
    field_filters = {}
    for field in ["id", "type", "family", "genus", "lifespan"]:
        if field in request.args:
            field_filters[field] = request.args.get(field)

    # apply simple field=value filters
    for field, value in field_filters.items():
        if field == "lifespan":
            # lifespan is int, but query is string
            try:
                value_int = int(value)
            except ValueError:
                return json_error("Malformed data", 400)
            result = [pt for pt in result if pt["lifespan"] == value_int]
        else:
            result = [
                pt for pt in result
                if str(pt[field]).lower() == value.lower()
            ]

    # hasAttribute=<attr>
    has_attr = request.args.get("hasAttribute")
    if has_attr is not None:
        attr_lower = has_attr.lower()
        result = [
            pt for pt in result
            if any(a.lower() == attr_lower for a in pt["attributes"])
        ]

    return jsonify(result), 200


# -----------------------
# /pet-types/{id}
# -----------------------

@app.route("/pet-types/<pet_type_id>", methods=["GET"])
def get_pet_type(pet_type_id):
    pt = pet_types.get(pet_type_id)
    if not pt:
        return json_error("Not found", 404)
    return jsonify(pt), 200


@app.route("/pet-types/<pet_type_id>", methods=["DELETE"])
def delete_pet_type(pet_type_id):
    pt = pet_types.get(pet_type_id)
    if not pt:
        return json_error("Not found", 404)

    if pt["pets"]:
        # cannot delete if there are pets
        return json_error("Malformed data", 400)

    remove_pet_type(pet_type_id)
    return "", 204


# PUT is not allowed on /pet-types/{id}
@app.route("/pet-types/<pet_type_id>", methods=["PUT"])
def put_pet_type_not_allowed(pet_type_id):
    # Method not allowed
    return "", 405


# -----------------------
# /pet-types/{id}/pets
# -----------------------

def _download_picture(picture_url):
    """Download picture and return file name, or raise for errors."""
    resp = requests.get(picture_url, stream=True)
    if resp.status_code != 200:
        # simulate internal server error for unexpected codes
        raise NinjaApiError(resp.status_code)

    # guess extension from content-type
    content_type = resp.headers.get("Content-Type", "")
    ext = ".jpg"
    if "png" in content_type.lower():
        ext = ".png"

    ensure_pictures_folder()
    file_name = f"pet_{abs(hash(picture_url))}{ext}"
    path = os.path.join("pictures", file_name)

    with open(path, "wb") as f:
        for chunk in resp.iter_content(8192):
            if chunk:
                f.write(chunk)

    return file_name


def _build_or_update_pet(pet_type_id, data, existing_pet=None):
    """
    Create or update internal pet dict from JSON payload.
    - data must contain 'name'
    - 'birthdate' optional
    - 'picture-url' optional
    """
    if "name" not in data or not isinstance(data["name"], str):
        raise ValueError("Malformed")

    name = data["name"]
    birthdate = data.get("birthdate", "NA")
    picture_url = data.get("picture-url")

    if birthdate != "NA":
        # validate date format
        try:
            parse_date(birthdate)
        except Exception:
            raise ValueError("Malformed")

    # starting values
    picture = "NA"
    old_picture_file = None

    if existing_pet:
        # preserve old values when not provided
        if "birthdate" not in data:
            birthdate = existing_pet["birthdate"]
        if "picture-url" not in data:
            picture = existing_pet["picture"]
            picture_url = existing_pet.get("picture_url")
        else:
            # they provided a new picture-url; if it is the same, no re-download
            if picture_url == existing_pet.get("picture_url"):
                picture = existing_pet["picture"]
            else:
                old_picture_file = existing_pet["picture"]

    # download picture if we still have a new picture-url and picture != old picture
    if picture_url and (not existing_pet or picture != existing_pet["picture"]):
        file_name = _download_picture(picture_url)
        picture = file_name

    # delete old file if changed
    if old_picture_file and old_picture_file != "NA":
        try:
            os.remove(os.path.join("pictures", old_picture_file))
        except OSError:
            pass

    internal = {
        "name": name,
        "birthdate": birthdate,
        "picture": picture,
        "picture_url": picture_url,
    }
    return internal


@app.route("/pet-types/<pet_type_id>/pets", methods=["POST"])
def create_pet(pet_type_id):
    # check that pet-type exists
    if pet_type_id not in pet_types:
        return json_error("Not found", 404)

    resp = require_json()
    if resp:
        return resp

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return json_error("Malformed data", 400)

    try:
        internal_pet = _build_or_update_pet(pet_type_id, data)
    except ValueError:
        return json_error("Malformed data", 400)
    except NinjaApiError as e:
        return server_error_from_ninja(e.status_code)

    add_pet(pet_type_id, internal_pet)
    return jsonify(pet_to_json(internal_pet)), 201


@app.route("/pet-types/<pet_type_id>/pets", methods=["GET"])
def list_pets(pet_type_id):
    if pet_type_id not in pet_types:
        return json_error("Not found", 404)

    pets_map = get_pets_for_type(pet_type_id)
    pets_list = [pet_to_json(p) for p in pets_map.values()]

    # date filters: birthdateGT, birthdateLT
    gt = request.args.get("birthdateGT")
    lt = request.args.get("birthdateLT")

    # validate dates if present
    try:
        if gt:
            parse_date(gt)
        if lt:
            parse_date(lt)
    except Exception:
        return json_error("Malformed data", 400)

    if gt:
        pets_list = [
            p for p in pets_list
            if p["birthdate"] != "NA" and compare_dates(p["birthdate"], gt) > 0
        ]
    if lt:
        pets_list = [
            p for p in pets_list
            if p["birthdate"] != "NA" and compare_dates(p["birthdate"], lt) < 0
        ]

    return jsonify(pets_list), 200


# -----------------------
# /pet-types/{id}/pets/{name}
# -----------------------

@app.route("/pet-types/<pet_type_id>/pets/<name>", methods=["GET"])
def get_pet(pet_type_id, name):
    if pet_type_id not in pet_types:
        return json_error("Not found", 404)

    pets_map = get_pets_for_type(pet_type_id)
    pet = pets_map.get(name.lower())
    if not pet:
        return json_error("Not found", 404)

    return jsonify(pet_to_json(pet)), 200


@app.route("/pet-types/<pet_type_id>/pets/<name>", methods=["DELETE"])
def delete_pet_route(pet_type_id, name):
    if pet_type_id not in pet_types:
        return json_error("Not found", 404)

    pet = delete_pet(pet_type_id, name)
    if not pet:
        return json_error("Not found", 404)

    # delete picture file if exists
    if pet["picture"] != "NA":
        try:
            os.remove(os.path.join("pictures", pet["picture"]))
        except OSError:
            pass

    return "", 204


@app.route("/pet-types/<pet_type_id>/pets/<name>", methods=["PUT"])
def update_pet(pet_type_id, name):
    if pet_type_id not in pet_types:
        return json_error("Not found", 404)

    resp = require_json()
    if resp:
        return resp

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return json_error("Malformed data", 400)

    # load existing pet
    pets_map = get_pets_for_type(pet_type_id)
    existing = pets_map.get(name.lower())
    if not existing:
        return json_error("Not found", 404)

    try:
        internal_pet = _build_or_update_pet(pet_type_id, data, existing_pet=existing)
    except ValueError:
        return json_error("Malformed data", 400)
    except NinjaApiError as e:
        return server_error_from_ninja(e.status_code)

    # update storage
    add_pet(pet_type_id, internal_pet)
    return jsonify(pet_to_json(internal_pet)), 200


# -----------------------
# /pictures/{file-name}
# -----------------------

@app.route("/pictures/<file_name>", methods=["GET"])
def get_picture(file_name):
    # we ignore JSON payload and just use the file name in the path
    if not os.path.exists(os.path.join("pictures", file_name)):
        return json_error("Not found", 404)

    # send the image; Flask guesses mimetype from filename
    return send_from_directory("pictures", file_name), 200


# -----------------------
# Main entrypoint
# -----------------------

if __name__ == "__main__":
    # listen on 0.0.0.0:5001 as required
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)
