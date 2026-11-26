"""Colorful UI building blocks for NearPal."""
from html import escape

import streamlit as st

# Playful palette (works for kids, readable for adults)
COLORS = {
    "pink": "#FF5E7E", "orange": "#FF9F43", "yellow": "#FFD93D", "green": "#2ECC9A",
    "teal": "#1FB6C9", "blue": "#4D8DFF", "purple": "#6C5CE7",
}
CHIP_COLORS = ["#FFE1E8", "#FFE9D2", "#FFF4C2", "#D8F7EA", "#D4F3F7", "#DDE8FF", "#E7E2FF"]

PAGE_STYLES = {  # page key -> (emoji, gradient start, gradient end)
    "My kids": ("🧸", COLORS["pink"], COLORS["orange"]),
    "My profile": ("🌟", COLORS["pink"], COLORS["orange"]),
    "Find pals": ("🔎", COLORS["teal"], COLORS["green"]),
    "Requests": ("📬", COLORS["blue"], COLORS["teal"]),
    "Pals & meetups": ("📅", COLORS["purple"], COLORS["pink"]),
    "Admin": ("🛡️", "#636E72", COLORS["purple"]),
}

CSS = """
<style>
/* page width + background confetti */
.block-container { padding-top: 3.5rem; max-width: 900px; }
[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(circle at 8% 12%, #FFE1E8 0 70px, transparent 71px),
    radial-gradient(circle at 92% 20%, #DDE8FF 0 90px, transparent 91px),
    radial-gradient(circle at 85% 85%, #FFF4C2 0 80px, transparent 81px),
    radial-gradient(circle at 5% 90%, #D8F7EA 0 60px, transparent 61px),
    #FFF8EE;
  background-attachment: fixed;
}

/* sidebar */
[data-testid="stSidebar"] { background: linear-gradient(180deg, #6C5CE7 0%, #5B4BD6 55%, #8E44AD 100%); }
[data-testid="stSidebar"] .np-logo { font-family: Fredoka, sans-serif; font-size: 2rem; font-weight: 700;
  color: #fff; letter-spacing: .5px; margin-bottom: .2rem; }
[data-testid="stSidebar"] .np-logo span { color: #FFD93D; }
[data-testid="stSidebar"] .np-hello { background: rgba(255,255,255,.14); border-radius: 18px;
  padding: .8rem 1rem; color: #fff; margin: .4rem 0 1rem; line-height: 1.5; }
[data-testid="stSidebar"] [role="radiogroup"] { width: 100%; }
[data-testid="stSidebar"] [role="radiogroup"] label { background: rgba(255,255,255,.10);
  border-radius: 999px; padding: .55rem 1rem; margin-bottom: .4rem; width: 100%;
  display: flex; transition: background .15s; cursor: pointer; }
[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child { display: none; }
[data-testid="stSidebar"] [role="radiogroup"] label p { font-size: 1.02rem; font-weight: 700; }
[data-testid="stSidebar"] [role="radiogroup"] label:hover { background: rgba(255,255,255,.22); }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) { background: #FFD93D; }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p { color: #2D2A4A; font-weight: 800; }

/* hero + page headers */
.np-hero { border-radius: 28px; padding: 2.2rem 2rem; color: #fff; text-align: center;
  background: linear-gradient(135deg, #FF5E7E 0%, #FF9F43 45%, #6C5CE7 100%);
  box-shadow: 0 14px 30px rgba(108,92,231,.25); margin-bottom: 1.2rem; }
.np-hero h1 { font-family: Fredoka, sans-serif; color: #fff; font-size: 3rem; margin: 0; padding: 0; }
.np-hero p { font-size: 1.15rem; margin: .4rem 0 1rem; opacity: .95; }
.np-pill { display: inline-block; background: rgba(255,255,255,.22); border: 1px solid rgba(255,255,255,.4);
  border-radius: 999px; padding: .35rem .9rem; margin: .2rem; font-weight: 700; font-size: .95rem; }
.np-head { border-radius: 24px; padding: 1.1rem 1.4rem; color: #fff; margin-bottom: 1.2rem;
  display: flex; align-items: center; gap: 1rem; box-shadow: 0 10px 22px rgba(0,0,0,.08); }
.np-head .np-emoji { font-size: 2.6rem; background: rgba(255,255,255,.25); border-radius: 18px;
  width: 64px; height: 64px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.np-head h2 { font-family: Fredoka, sans-serif; color: #fff; margin: 0; padding: 0; font-size: 1.9rem; }
.np-head p { margin: .1rem 0 0; opacity: .95; }

/* cards (any container with a key starting with "card") */
[class*="st-key-card"] { background: #fff; border: 2px solid #F3DFC6 !important;
  border-radius: 22px; box-shadow: 0 6px 16px rgba(45,42,74,.06); transition: transform .12s, box-shadow .12s; }
[class*="st-key-card"]:hover { transform: translateY(-2px); box-shadow: 0 10px 22px rgba(45,42,74,.10); }
.np-name { font-family: Fredoka, sans-serif; font-size: 1.3rem; font-weight: 600; }
.np-avatar { font-size: 2.3rem; line-height: 1; }
.np-meta { color: #6B6785; font-size: .95rem; }
.np-chip { display: inline-block; border-radius: 999px; padding: .2rem .7rem; margin: .15rem .2rem .15rem 0;
  font-size: .85rem; font-weight: 700; color: #2D2A4A; }
.np-badge { display: inline-block; border-radius: 999px; padding: .2rem .7rem; font-size: .8rem;
  font-weight: 800; color: #fff; }
.np-empty { text-align: center; padding: 2rem 1rem; border: 2px dashed #F3DFC6; border-radius: 22px;
  color: #6B6785; background: rgba(255,255,255,.6); }
.np-empty .big { font-size: 3rem; }

/* buttons */
.stButton > button, .stFormSubmitButton > button { font-weight: 800; transition: transform .1s; }
.stButton > button:hover, .stFormSubmitButton > button:hover { transform: scale(1.03); }
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {
  background: linear-gradient(90deg, #FF5E7E, #FF9F43) !important; border: none !important; }

/* tabs */
[data-baseweb="tab-list"] { gap: .5rem; }
[data-baseweb="tab"] { background: #fff; border-radius: 999px !important; padding: .4rem 1.2rem !important;
  border: 2px solid #F3DFC6 !important; }
[data-baseweb="tab"][aria-selected="true"] { background: #FF5E7E; color: #fff; border-color: #FF5E7E !important; }
[data-baseweb="tab"][aria-selected="true"] p { color: #fff; }
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] { display: none; }

/* forms and expanders as soft cards */
[data-testid="stForm"] { background: #fff; border: 2px solid #F3DFC6; border-radius: 22px; }
[data-testid="stExpander"] details { background: #fff; border: 2px solid #E7E2FF; border-radius: 22px; }
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def hero():
    st.markdown(
        """<div class="np-hero"><h1>🤝 NearPal</h1>
        <p>Find nearby pals who love the same things you do!</p>
        <span class="np-pill">🎨 Same hobbies</span><span class="np-pill">📍 Close to home</span>
        <span class="np-pill">🛡️ Safe &amp; parent-approved</span></div>""",
        unsafe_allow_html=True)


def page_header(page, subtitle=""):
    emoji, c1, c2 = PAGE_STYLES.get(page, ("✨", COLORS["pink"], COLORS["purple"]))
    sub = f"<p>{escape(subtitle)}</p>" if subtitle else ""
    st.markdown(
        f"""<div class="np-head" style="background: linear-gradient(120deg, {c1}, {c2});">
        <div class="np-emoji">{emoji}</div><div><h2>{escape(page)}</h2>{sub}</div></div>""",
        unsafe_allow_html=True)


def chips(items):
    """Colored hobby chips (HTML-escaped)."""
    return "".join(
        f'<span class="np-chip" style="background:{CHIP_COLORS[sum(map(ord, i)) % len(CHIP_COLORS)]}">'
        f"{escape(i)}</span>" for i in items)


def badge(text, color):
    return f'<span class="np-badge" style="background:{color}">{escape(text)}</span>'


def avatar(person):
    age, gender = person.get("age", 10), person.get("gender")
    if gender == "Male":
        return "👦" if age < 18 else "👨"
    if gender == "Female":
        return "👧" if age < 18 else "👩"
    return "🧒" if age < 18 else "🧑"


def gender_label(gender, age):
    if gender not in ("Male", "Female"):
        return "Not set"
    if age < 18:
        return "Boy" if gender == "Male" else "Girl"
    return gender


def person_html(person, extra_meta="", hobbies=None):
    """Avatar + name + meta line + hobby chips, all escaped."""
    meta = f"{person['age']} years · {gender_label(person.get('gender'), person['age'])}"
    if extra_meta:
        meta += f" · {escape(extra_meta)}"
    return (f'<div style="display:flex;gap:.9rem;align-items:center">'
            f'<div class="np-avatar">{avatar(person)}</div><div>'
            f'<div class="np-name">{escape(person["first_name"])}</div>'
            f'<div class="np-meta">{meta}</div>'
            f'<div>{chips(hobbies if hobbies is not None else person.get("hobbies", []))}</div>'
            f"</div></div>")


def empty(emoji, text):
    st.markdown(f'<div class="np-empty"><div class="big">{emoji}</div>{escape(text)}</div>',
                unsafe_allow_html=True)
