# models.py
import datetime
import os
import string

# -----------------------
# In-memory "database"
# -----------------------

# pet_types: id (str) -> pet-type JSON dict
pet_types = {}

# pets_by_type: pet_type_id (str) -> { pet_name_lower: pet_internal_dict }
# internal pet dict has keys: name, birthdate, picture, picture_url
pets_by_type = {}

# map from lowercase type name to id, to prevent duplicates
type_name_to_id = {}

# simple incremental id generator for pet-types
_next_pet_type_id = 1


def generate_pet_type_id():
    global _next_pet_type_id
    pet_id = str(_next_pet_type_id)
    _next_pet_type_id += 1
    return pet_id


# -----------------------
# Date helpers
# -----------------------

DATE_FORMAT = "%d-%m-%Y"


def parse_date(date_str):
    """Parse DD-MM-YYYY into datetime.date. Raise ValueError if invalid."""
    return datetime.datetime.strptime(date_str, DATE_FORMAT).date()


def compare_dates(d1_str, d2_str):
    """
    Compare two DD-MM-YYYY strings.
    Returns negative if d1<d2, 0 if equal, positive if d1>d2.
    """
    d1 = parse_date(d1_str)
    d2 = parse_date(d2_str)
    return (d1 - d2).days


# -----------------------
# Attribute helpers
# -----------------------

def temperament_to_attributes(text):
    """
    Convert temperament/group_behavior string into array of words.
    - lowercases
    - strips punctuation
    - splits on whitespace
    """
    if not text:
        return []

    # lower case for case-insensitive matching
    text = text.lower()

    # remove punctuation
    translator = str.maketrans("", "", string.punctuation)
    text = text.translate(translator)

    # split into words, drop empty
    words = [w for w in text.split() if w]
    return words


# -----------------------
# Pet-type helpers
# -----------------------

def pet_type_exists_by_name(type_name):
    """Check if a pet-type with this name (case-insensitive) already exists."""
    return type_name.lower() in type_name_to_id


def register_pet_type(pet_type_obj):
    """
    Store a new pet-type JSON object.
    pet_type_obj must already contain 'id' and 'type' and other fields.
    """
    pet_types[pet_type_obj["id"]] = pet_type_obj
    pets_by_type[pet_type_obj["id"]] = {}
    type_name_to_id[pet_type_obj["type"].lower()] = pet_type_obj["id"]


def remove_pet_type(pet_type_id):
    """Delete pet-type and all its pets (pictures should already be handled)."""
    pet_type = pet_types.pop(pet_type_id, None)
    if pet_type is None:
        return

    pets_by_type.pop(pet_type_id, None)
    type_name_to_id.pop(pet_type["type"].lower(), None)


# -----------------------
# Pet helpers
# -----------------------

def get_pets_for_type(pet_type_id):
    return pets_by_type.get(pet_type_id, {})


def add_pet(pet_type_id, internal_pet):
    """
    Add pet to pets_by_type and to pet_types[...]['pets'] list.
    internal_pet is dict with name, birthdate, picture, picture_url.
    """
    pets = pets_by_type.setdefault(pet_type_id, {})
    name_lower = internal_pet["name"].lower()
    pets[name_lower] = internal_pet

    pet_type = pet_types[pet_type_id]
    if internal_pet["name"] not in pet_type["pets"]:
        pet_type["pets"].append(internal_pet["name"])


def delete_pet(pet_type_id, pet_name):
    pets = pets_by_type.get(pet_type_id, {})
    name_lower = pet_name.lower()
    pet = pets.pop(name_lower, None)
    if pet is None:
        return None

    # remove from pet-types "pets" array
    pet_type = pet_types[pet_type_id]
    pet_type["pets"] = [n for n in pet_type["pets"] if n.lower() != name_lower]
    return pet


def pet_to_json(internal_pet):
    """Convert internal pet dict to JSON representation."""
    return {
        "name": internal_pet["name"],
        "birthdate": internal_pet["birthdate"],
        "picture": internal_pet["picture"],
    }


def ensure_pictures_folder():
    if not os.path.exists("pictures"):
        os.makedirs("pictures")
