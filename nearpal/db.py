"""MongoDB access for NearPal.

Collections
-----------
parents      one document per parent account (holds the only contact info)
children     a parent's kids: first name, age, hobbies (no contact info)
hobbies      shared hobby list; new ones are checked before everyone sees them
connections  a request between two children, accepted/declined by the parents
meetups      AI-suggested meetup plans for an accepted connection
"""
from datetime import datetime, timezone

import streamlit as st
from bson import ObjectId
from pymongo import ASCENDING, MongoClient

STARTER_HOBBIES = [
    "Arts & Crafts", "Basketball", "Board Games", "Chess", "Coding", "Cycling",
    "Dancing", "Drawing", "Football", "Gymnastics", "Lego & Building", "Martial Arts",
    "Music", "Photography", "Reading", "Robotics", "Science Experiments", "Swimming",
    "Tennis", "Video Games",
]

# Under this age a parent/guardian must manage the account
SELF_SIGNUP_AGE = 15

# People are only ever matched within the same band, so adults never see minors.
# Under-15 bands are parent-managed; 15-17 and 18+ have their own accounts.
AGE_BANDS = [(4, 6), (7, 9), (10, 12), (13, 14), (15, 17), (18, 120)]


def age_band(age: int) -> str:
    for lo, hi in AGE_BANDS:
        if lo <= age <= hi:
            return f"{lo}-{hi}"
    return "other"


def now():
    return datetime.now(timezone.utc)


@st.cache_resource(show_spinner=False)
def get_db():
    client = MongoClient(st.secrets["MONGO_URI"], serverSelectionTimeoutMS=8000)
    db = client[st.secrets.get("MONGO_DB_NAME", "nearpal")]
    _setup(db)
    return db


def _setup(db):
    db.parents.create_index([("email", ASCENDING)], unique=True)
    db.children.create_index([("parent_id", ASCENDING)])
    db.children.create_index([("city_key", ASCENDING), ("age_band", ASCENDING), ("hobbies", ASCENDING)])
    db.hobbies.create_index([("key", ASCENDING)], unique=True)
    db.connections.create_index([("from_child", ASCENDING), ("to_child", ASCENDING)], unique=True)
    if db.hobbies.count_documents({}) == 0:
        db.hobbies.insert_many(
            [{"name": h, "key": h.lower(), "approved": True, "created_at": now()} for h in STARTER_HOBBIES]
        )


def oid(value):
    return value if isinstance(value, ObjectId) else ObjectId(value)


# ---------- parents ----------
def create_parent(db, doc):
    doc["city_key"] = city_key(doc["country"], doc["governorate"], doc["city"])
    doc["created_at"] = now()
    return db.parents.insert_one(doc).inserted_id


def find_parent_by_email(db, email):
    return db.parents.find_one({"email": email.strip().lower()})


def get_parent(db, parent_id):
    return db.parents.find_one({"_id": oid(parent_id)})


def delete_account(db, parent_id):
    """Delete an account, its kids/profile, their connections and meetups."""
    pid = oid(parent_id)
    conns = db.connections.find({"$or": [{"from_parent": pid}, {"to_parent": pid}]}, {"_id": 1})
    conn_ids = [c["_id"] for c in conns]
    db.meetups.delete_many({"connection_id": {"$in": conn_ids}})
    db.connections.delete_many({"_id": {"$in": conn_ids}})
    db.children.delete_many({"parent_id": pid})
    db.parents.delete_one({"_id": pid})


def city_key(country, governorate, city):
    return f"{country}|{governorate}|{city}".lower()


# ---------- hobbies ----------
def approved_hobbies(db):
    return [h["name"] for h in db.hobbies.find({"approved": True}).sort("key", ASCENDING)]


def add_hobby(db, name, approved, created_by):
    """Insert a hobby if new. Returns the existing or new document."""
    name = " ".join(name.strip().split()).title()
    existing = db.hobbies.find_one({"key": name.lower()})
    if existing:
        return existing
    doc = {"name": name, "key": name.lower(), "approved": approved,
           "created_by": oid(created_by), "created_at": now()}
    db.hobbies.insert_one(doc)
    return doc


def pending_hobbies(db):
    return list(db.hobbies.find({"approved": False}))


def set_hobby_approved(db, hobby_id, approved: bool):
    if approved:
        db.hobbies.update_one({"_id": oid(hobby_id)}, {"$set": {"approved": True}})
    else:
        db.hobbies.delete_one({"_id": oid(hobby_id)})


# ---------- children ----------
def add_child(db, parent, first_name, age, hobbies):
    return db.children.insert_one({
        "parent_id": parent["_id"],
        "first_name": first_name.strip(),
        "age": int(age),
        "age_band": age_band(int(age)),
        "hobbies": hobbies,
        "country": parent["country"],
        "governorate": parent["governorate"],
        "city": parent["city"],
        "neighborhood": parent["neighborhood"],
        "city_key": parent["city_key"],
        "created_at": now(),
    }).inserted_id


def children_of(db, parent_id):
    return list(db.children.find({"parent_id": oid(parent_id)}))


def update_child_hobbies(db, child_id, parent_id, hobbies):
    db.children.update_one({"_id": oid(child_id), "parent_id": oid(parent_id)},
                           {"$set": {"hobbies": hobbies}})


def get_child(db, child_id):
    return db.children.find_one({"_id": oid(child_id)})


def delete_child(db, child_id, parent_id):
    child_id = oid(child_id)
    db.children.delete_one({"_id": child_id, "parent_id": oid(parent_id)})
    db.connections.delete_many({"$or": [{"from_child": child_id}, {"to_child": child_id}]})


def find_matches(db, child):
    """People in the same city and age band who share at least one hobby.
    Default order: same neighborhood, more shared hobbies, closer age."""
    cursor = db.children.find({
        "city_key": child["city_key"],
        "age_band": child["age_band"],
        "hobbies": {"$in": child["hobbies"]},
        "parent_id": {"$ne": child["parent_id"]},
    })
    results = []
    for other in cursor:
        shared = sorted(set(other["hobbies"]) & set(child["hobbies"]))
        same_hood = other.get("neighborhood", "").lower() == child.get("neighborhood", "").lower()
        results.append({"child": other, "shared": shared, "same_neighborhood": same_hood})
    results.sort(key=lambda r: (not r["same_neighborhood"], -len(r["shared"]),
                                abs(r["child"]["age"] - child["age"]), r["child"]["first_name"]))
    return results


# ---------- connections ----------
def connection_between(db, child_a, child_b):
    a, b = oid(child_a), oid(child_b)
    return db.connections.find_one({"$or": [
        {"from_child": a, "to_child": b}, {"from_child": b, "to_child": a}]})


def send_request(db, from_child, to_child):
    if from_child["age_band"] != to_child["age_band"]:  # never connect across age bands
        return None
    if connection_between(db, from_child["_id"], to_child["_id"]):
        return None
    return db.connections.insert_one({
        "from_child": from_child["_id"], "to_child": to_child["_id"],
        "from_parent": from_child["parent_id"], "to_parent": to_child["parent_id"],
        "shared_hobbies": sorted(set(from_child["hobbies"]) & set(to_child["hobbies"])),
        "status": "pending", "created_at": now(),
    }).inserted_id


def incoming_requests(db, parent_id):
    return list(db.connections.find({"to_parent": oid(parent_id), "status": "pending"}))


def outgoing_requests(db, parent_id):
    return list(db.connections.find({"from_parent": oid(parent_id), "status": "pending"}))


def accepted_connections(db, parent_id):
    pid = oid(parent_id)
    return list(db.connections.find({"status": "accepted", "$or": [{"from_parent": pid}, {"to_parent": pid}]}))


def respond_request(db, connection_id, parent_id, accept: bool):
    db.connections.update_one(
        {"_id": oid(connection_id), "to_parent": oid(parent_id), "status": "pending"},
        {"$set": {"status": "accepted" if accept else "declined", "responded_at": now()}},
    )


# ---------- meetups ----------
def get_meetup(db, connection_id):
    return db.meetups.find_one({"connection_id": oid(connection_id)})


def save_meetup_options(db, connection_id, options):
    db.meetups.update_one(
        {"connection_id": oid(connection_id)},
        {"$set": {"options": options, "chosen": None, "confirmed_by": [], "updated_at": now()}},
        upsert=True,
    )


def choose_meetup_option(db, connection_id, index, parent_id):
    """The parent who picks an option confirms it; the other parent must confirm too."""
    db.meetups.update_one(
        {"connection_id": oid(connection_id)},
        {"$set": {"chosen": index, "confirmed_by": [oid(parent_id)], "updated_at": now()}},
    )


def confirm_meetup(db, connection_id, parent_id):
    db.meetups.update_one(
        {"connection_id": oid(connection_id)},
        {"$addToSet": {"confirmed_by": oid(parent_id)}, "$set": {"updated_at": now()}},
    )
