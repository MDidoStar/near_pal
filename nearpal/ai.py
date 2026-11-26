"""AI helpers (Groq, gpt-oss-20b): hobby safety check and meetup planning."""
import json

import streamlit as st
from groq import Groq


@st.cache_resource(show_spinner=False)
def _client():
    return Groq(api_key=st.secrets["GROQ_API_KEY"])


def _model():
    return st.secrets.get("GROQ_MODEL", "openai/gpt-oss-20b")


def _ask_json(prompt: str) -> dict:
    response = _client().chat.completions.create(
        model=_model(),
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Always reply with a single JSON object."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.4,
        reasoning_effort="low",
    )
    return json.loads(response.choices[0].message.content)


def is_hobby_appropriate(hobby: str):
    """Returns True/False, or None if the AI couldn't be reached (then an admin reviews it)."""
    prompt = (
        "You moderate the shared hobby list of a hobby-buddy app used by children "
        "(from age 4), teens and adults. "
        f'Is "{hobby}" a real hobby that is safe and appropriate for children to see in the list? '
        'Reply as JSON: {"appropriate": true or false, "reason": "short reason"}'
    )
    try:
        return bool(_ask_json(prompt).get("appropriate"))
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def rank_matches(my_age: int, my_hobbies: tuple, candidates_json: str):
    """Rank candidate pals. Candidates are already filtered (same city and age band);
    the AI only orders them, it can't add anyone.

    candidates_json: JSON list of {"id", "age", "shared_hobbies", "same_neighborhood"}.
    Returns [{"id", "reason"}] best first, or None if the AI failed."""
    candidates = json.loads(candidates_json)
    prompt = f"""
You match people for a hobby-buddy app. Rank the candidates as pals for this person.

Person: age {my_age}, hobbies: {", ".join(my_hobbies)}
Candidates: {candidates_json}

Ranking rules, most important first:
1. Age: smaller age gap is better. For children a gap of 1 year matters a lot;
   for adults it matters less.
2. More shared hobbies is better.
3. Same neighborhood is better (easier to meet).

Reply as JSON: {{"ranking": [{{"id": "<candidate id>", "reason": "max 12 words, mention age and hobbies"}}]}}
Include every candidate exactly once.
"""
    try:
        ranking = _ask_json(prompt).get("ranking", [])
    except Exception:
        return None
    valid = {c["id"] for c in candidates}
    seen, result = set(), []
    for item in ranking:
        cid = str(item.get("id", ""))
        if cid in valid and cid not in seen:
            seen.add(cid)
            result.append({"id": cid, "reason": str(item.get("reason", ""))})
    result += [{"id": c["id"], "reason": ""} for c in candidates if c["id"] not in seen]
    return result


def _supervision_rule(ages):
    youngest = min(ages)
    if youngest < 15:
        return ("A child is under 15: parents MUST attend. Daytime only, between 9:00 and 19:00. "
                "Pick activities suitable for the youngest age.")
    if youngest < 18:
        return ("Teens aged 15-17: busy public places only, daytime between 9:00 and 20:00. "
                "Remind them to tell a parent where and when they're meeting.")
    return "Adults: public places only; any reasonable time."


def plan_meetups(hobbies, ages, country, governorate, city, neighborhoods, availability, notes=""):
    """Ask the AI for 3 meetup suggestions at public places, suited to the ages."""
    prompt = f"""
You help plan a first meetup between two hobby pals.

Ages: {", ".join(str(a) for a in ages)}
Supervision: {_supervision_rule(ages)}
Shared hobbies: {", ".join(hobbies)}
Location: {city}, {governorate}, {country}
Families' neighborhoods: {", ".join(neighborhoods)}
Availability: {availability}
Extra notes: {notes or "none"}

Rules:
- Only public places (parks, libraries, clubs, sports centers, museums, community
  centers, cafes). Never homes or private places.
- Follow the supervision rule above and stay within the availability given.
- Activities must suit the ages: e.g. a playground for a 6-year-old, a climbing gym
  or chess club for teens.
- Prefer places between the two neighborhoods, and connected to the shared hobby.
- Use real, well-known places in that city where you can; otherwise describe the kind of place.

Reply as JSON: {{"options": [ ...exactly 3 objects... ]}} where each object has keys
"place" (name), "area" (neighborhood/district), "day", "time" (e.g. "16:00-17:30"),
"activity" (what the kids will do), "why" (one sentence).
"""
    data = _ask_json(prompt)
    if isinstance(data, dict):
        data = data.get("options") or next((v for v in data.values() if isinstance(v, list)), [])
    keys = ["place", "area", "day", "time", "activity", "why"]
    return [{k: str(item.get(k, "")) for k in keys} for item in data[:3] if isinstance(item, dict)]
