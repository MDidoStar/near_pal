"""NearPal: connects people with the same hobbies who live close to each other.

Under-15s are managed by a parent; 15+ have their own account. Matching only ever
happens within the same age band and the same gender. Contact details are only
shared after a request is accepted. AI (gpt-oss-20b on Groq) ranks matches and
suggests public meetups.
"""
import json
import re

import streamlit as st

from nearpal import ai, db, ui
from nearpal.auth import hash_password, verify_password
from nearpal.locations import location_picker

st.set_page_config(page_title="NearPal", page_icon="🤝", initial_sidebar_state="expanded")
ui.inject_css()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

try:
    DB = db.get_db()
    DB.command("ping")
except Exception as e:  # missing secrets or Mongo unreachable
    st.error(f"Can't connect to MongoDB. Check MONGO_URI in .streamlit/secrets.toml.\n\n{e}")
    st.stop()


def current_parent():
    pid = st.session_state.get("parent_id")
    return db.get_parent(DB, pid) if pid else None


def is_admin(parent):
    admins = [e.strip().lower() for e in st.secrets.get("ADMIN_EMAILS", [])]
    return parent["email"] in admins


def is_member(account):
    return account.get("account_type") == "member"


def gender_picker(label, age, key):
    """Radio with Boy/Girl for under-18s and Male/Female for adults. Stores Male/Female."""
    return st.radio(label, db.GENDERS, key=key, horizontal=True, index=None,
                    format_func=lambda g: ("👦 " if g == "Male" else "👧 ") + ui.gender_label(g, age))


def html(text):
    st.markdown(text, unsafe_allow_html=True)


# ------------------------------------------------------------------ sign in / up
def login_page():
    ui.hero()
    tab_in, tab_up = st.tabs(["🔑 Log in", "🎉 Sign up"])

    with tab_in:
        with st.form("login"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Log in", type="primary", width="stretch"):
                parent = db.find_parent_by_email(DB, email)
                if parent and verify_password(password, parent["password_hash"]):
                    st.session_state.parent_id = str(parent["_id"])
                    st.rerun()
                st.error("Wrong email or password.")

    with tab_up:
        signup_form()


def signup_form():
    age = st.number_input("🎂 How old are you?", min_value=4, max_value=120, value=15, step=1,
                          key="su_age")
    needs_parent = age < db.SELF_SIGNUP_AGE
    if needs_parent:
        st.warning(f"You're under {db.SELF_SIGNUP_AGE}, so you need a parent. 👨‍👩‍👧 "
                   "Ask your parent or guardian to fill in this form with **their own** details. "
                   "After signing up they can add you on the **My kids** page.")
        st.subheader("👨‍👩‍👧 Parent / guardian details")
        name_label = "Parent's full name"
    else:
        st.info("You'll get a regular account of your own. 🙌 Your phone and email are only "
                "shared with people whose pal request you accept (or who accept yours).")
        st.subheader("🙂 Your details")
        name_label = "Your full name"

    name = st.text_input(name_label, key="su_name")
    gender = None
    if not needs_parent:
        gender = gender_picker("Gender", age, "su_gender")
        st.caption("You'll only be matched with people of the same gender.")
    email = st.text_input("Email", key="su_email")
    phone = st.text_input("Phone number", key="su_phone")
    password = st.text_input("Password (at least 8 characters)", type="password", key="su_pw")
    password2 = st.text_input("Repeat password", type="password", key="su_pw2")
    st.subheader("📍 Where do you live?")
    loc = location_picker("signup")

    chosen = []
    if not needs_parent:
        st.subheader("🎨 Your hobbies")
        chosen = st.multiselect("Pick what you love doing", db.approved_hobbies(DB), key="su_hobbies")
        st.caption("Missing a hobby? You can suggest new ones from your profile after signing up.")

    if needs_parent:
        confirm = st.checkbox("I am the parent or legal guardian of the children I will add.")
    else:
        confirm = st.checkbox("I confirm the age I entered is my real age.")
    consent = st.checkbox("I agree that my name, phone and email are shared only with "
                          "people whose pal request I accept (or who accept mine).")

    if st.button("🎉 Create account", type="primary", width="stretch"):
        errors = []
        if not name.strip():
            errors.append("Enter a name.")
        if not needs_parent and gender not in db.GENDERS:
            errors.append("Choose your gender.")
        if not EMAIL_RE.match(email.strip()):
            errors.append("Enter a valid email.")
        if not phone.strip():
            errors.append("Enter a phone number.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != password2:
            errors.append("Passwords don't match.")
        if not loc["neighborhood"]:
            errors.append("Choose or type your neighborhood.")
        if not needs_parent and not chosen:
            errors.append("Pick at least one hobby.")
        if not (confirm and consent):
            errors.append("Please tick both boxes.")
        if not errors and db.find_parent_by_email(DB, email):
            errors.append("An account with this email already exists.")
        for err in errors:
            st.error(err)
        if errors:
            return

        account = {
            "name": name.strip(), "email": email.strip().lower(), "phone": phone.strip(),
            "password_hash": hash_password(password), "consent_contact_sharing": True,
            "account_type": "parent" if needs_parent else "member", **loc,
        }
        if needs_parent:
            account["guardian_confirmed"] = True
        else:
            account["age"] = int(age)
            account["gender"] = gender
        pid = db.create_parent(DB, account)
        if not needs_parent:  # a member's own matchable profile
            db.add_child(DB, db.get_parent(DB, pid), name.split()[0], age, chosen, gender)
        st.session_state.parent_id = str(pid)
        st.rerun()


def hobby_suggest_box(account, hobbies):
    with st.expander("💡 Hobby not in the list? Suggest one"):
        new = st.text_input("New hobby name")
        if st.button("Add hobby") and new.strip():
            name = " ".join(new.strip().split()).title()
            if name.lower() in {h.lower() for h in hobbies}:
                st.info(f"'{name}' is already in the list.")
                return
            with st.spinner("Checking the hobby..."):
                ok = ai.is_hobby_appropriate(name)
            if ok is False:
                st.error(f"'{name}' can't be added as a hobby.")
                return
            db.add_hobby(DB, name, approved=bool(ok), created_by=account["_id"])
            if ok:
                st.success(f"'{name}' added. You can pick it now.")
                st.rerun()
            st.info(f"'{name}' was saved and will appear after an admin reviews it.")


def missing_gender_fix(person, account, who):
    """Older profiles have no gender; they can't be matched until it's set."""
    st.warning(f"Please set {who} gender. Until then, no matches can be shown.")
    c1, c2 = st.columns([3, 1])
    with c1:
        g = gender_picker("Gender", person["age"], f"g_{person['_id']}")
    if c2.button("Save", key=f"gsave_{person['_id']}") and g:
        db.set_child_gender(DB, person["_id"], account["_id"], g)
        st.rerun()


# ------------------------------------------------------------------ my profile (15+)
def profile_page(account):
    ui.page_header("My profile", "Your hobbies decide who you'll meet.")
    me = next(iter(db.children_of(DB, account["_id"])), None)
    if not me:
        st.error("Your profile is missing. Please contact support.")
        return
    with st.container(border=True, key=f"card_me_{me['_id']}"):
        html(ui.person_html(me, f"📍 {me['neighborhood']}, {me['city']}"))
        if me.get("gender") not in db.GENDERS:
            missing_gender_fix(me, account, "your")

    hobbies = db.approved_hobbies(DB)
    with st.form("profile"):
        chosen = st.multiselect("🎨 My hobbies", hobbies, default=[h for h in me["hobbies"] if h in hobbies])
        if st.form_submit_button("Save hobbies", type="primary"):
            if not chosen:
                st.error("Pick at least one hobby.")
            else:
                db.update_child_hobbies(DB, me["_id"], account["_id"], chosen)
                st.rerun()
    hobby_suggest_box(account, hobbies)


# ------------------------------------------------------------------ my kids
def kids_page(parent):
    ui.page_header("My kids", "Add your kids and their favourite hobbies.")
    kids = db.children_of(DB, parent["_id"])
    for kid in kids:
        with st.container(border=True, key=f"card_kid_{kid['_id']}"):
            c1, c2 = st.columns([5, 1], vertical_alignment="center")
            with c1:
                html(ui.person_html(kid))
            if c2.button("Remove", key=f"rm_{kid['_id']}"):
                db.delete_child(DB, kid["_id"], parent["_id"])
                st.rerun()
            if kid.get("gender") not in db.GENDERS:
                missing_gender_fix(kid, parent, f"{kid['first_name']}'s")
    if not kids:
        ui.empty("🧸", "No kids added yet. Add your first one below!")

    st.subheader("➕ Add a kid")
    st.caption(f"For kids under {db.SELF_SIGNUP_AGE}. "
               f"Kids {db.SELF_SIGNUP_AGE} and older can sign up with their own account.")
    hobbies = db.approved_hobbies(DB)
    with st.form("add_kid", clear_on_submit=True):
        first = st.text_input("First name only (no last name, for safety)")
        c1, c2 = st.columns(2)
        age = c1.number_input("Age", min_value=4, max_value=db.SELF_SIGNUP_AGE - 1, value=8, step=1)
        with c2:
            gender = st.radio("Gender", db.GENDERS, horizontal=True, index=None,
                              format_func=lambda g: "👦 Boy" if g == "Male" else "👧 Girl")
        chosen = st.multiselect("Hobbies", hobbies)
        if st.form_submit_button("Add kid", type="primary"):
            if not first.strip():
                st.error("Enter a first name.")
            elif gender not in db.GENDERS:
                st.error("Choose boy or girl.")
            elif not chosen:
                st.error("Pick at least one hobby.")
            else:
                db.add_child(DB, parent, first, age, chosen, gender)
                st.rerun()

    hobby_suggest_box(parent, hobbies)


# ------------------------------------------------------------------ find pals
def find_page(parent):
    ui.page_header("Find pals", "Same hobbies, same age group, same gender, close to home.")
    kids = db.children_of(DB, parent["_id"])
    if not kids:
        ui.empty("🧸", "Add a kid first on the My kids page.")
        return
    if is_member(parent):
        kid = kids[0]
    else:
        labels = {f"{ui.avatar(k)} {k['first_name']} ({k['age']})": k for k in kids}
        kid = labels[st.selectbox("Find pals for", list(labels))]
    lo, _, hi = kid["age_band"].partition("-")
    band = f"{lo}+" if int(hi) >= 100 else kid["age_band"]
    who = {"Male": "boys" if kid["age"] < 18 else "men",
           "Female": "girls" if kid["age"] < 18 else "women"}.get(kid.get("gender"), "people")
    st.caption(f"Showing {who} aged {band} in {kid['city']} who share a hobby with {kid['first_name']}.")

    if kid.get("gender") not in db.GENDERS:
        missing_gender_fix(kid, parent, f"{kid['first_name']}'s" if not is_member(parent) else "your")
        return

    matches = db.find_matches(DB, kid)
    if not matches:
        ui.empty("🔭", "No matches yet. New people join all the time, so check back soon!")
        return
    st.caption("✨ The AI puts the best matches first: mainly by age, then hobbies and neighborhood.")
    reasons = {}
    if len(matches) > 1:
        payload = json.dumps([{
            "id": str(m["child"]["_id"]), "age": m["child"]["age"],
            "shared_hobbies": m["shared"], "same_neighborhood": m["same_neighborhood"],
        } for m in matches])
        with st.spinner("AI is ranking your matches..."):
            ranking = ai.rank_matches(kid["age"], tuple(kid["hobbies"]), payload, kid["gender"])
        if ranking:
            order = {r["id"]: i for i, r in enumerate(ranking)}
            reasons = {r["id"]: r["reason"] for r in ranking}
            matches.sort(key=lambda m: order.get(str(m["child"]["_id"]), len(order)))

    for m in matches:
        other = m["child"]
        with st.container(border=True, key=f"card_match_{other['_id']}"):
            c1, c2 = st.columns([4, 1], vertical_alignment="center")
            with c1:
                hood = "📍 Same neighborhood!" if m["same_neighborhood"] else f"📍 {other['neighborhood']}"
                html(ui.person_html(other, hood, m["shared"]))
                if reasons.get(str(other["_id"])):
                    st.caption(f"✨ {reasons[str(other['_id'])]}")
            conn = db.connection_between(DB, kid["_id"], other["_id"])
            if conn:
                with c2:
                    html({"pending": ui.badge("⏳ Pending", ui.COLORS["orange"]),
                          "accepted": ui.badge("✅ Pals", ui.COLORS["green"]),
                          "declined": ui.badge("Declined", "#999")}[conn["status"]])
            elif c2.button("👋 Say hi", key=f"req_{kid['_id']}_{other['_id']}", type="primary"):
                db.send_request(DB, kid, other)
                st.rerun()


# ------------------------------------------------------------------ requests
def requests_page(parent):
    ui.page_header("Requests", "Say yes to make a new pal!")
    incoming = db.incoming_requests(DB, parent["_id"])
    st.subheader(f"📥 Waiting for your answer ({len(incoming)})")
    if not incoming:
        ui.empty("📭", "No new requests right now.")
    for conn in incoming:
        theirs, mine = db.get_child(DB, conn["from_child"]), db.get_child(DB, conn["to_child"])
        if not (theirs and mine):
            continue
        with st.container(border=True, key=f"card_req_{conn['_id']}"):
            target = "you" if is_member(parent) else mine["first_name"]
            html(ui.person_html(theirs, f"📍 {theirs['neighborhood']}", conn["shared_hobbies"]))
            st.markdown(f"wants to be pals with **{target}** 💌")
            st.caption("If you accept, you'll both see each other's account name, phone and email.")
            c1, c2 = st.columns(2)
            if c1.button("✅ Accept", key=f"acc_{conn['_id']}", type="primary", width="stretch"):
                db.respond_request(DB, conn["_id"], parent["_id"], True)
                st.rerun()
            if c2.button("Decline", key=f"dec_{conn['_id']}", width="stretch"):
                db.respond_request(DB, conn["_id"], parent["_id"], False)
                st.rerun()

    outgoing = db.outgoing_requests(DB, parent["_id"])
    st.subheader(f"📤 Sent, waiting for a reply ({len(outgoing)})")
    if not outgoing:
        st.caption("Nothing waiting.")
    for conn in outgoing:
        mine, theirs = db.get_child(DB, conn["from_child"]), db.get_child(DB, conn["to_child"])
        if mine and theirs:
            st.markdown(f"⏳ {ui.avatar(mine)} {mine['first_name']} → {ui.avatar(theirs)} "
                        f"{theirs['first_name']} ({theirs['age']})")


# ------------------------------------------------------------------ meetups
def meetups_page(parent):
    ui.page_header("Pals & meetups",
                   f"Always in public places. Kids under {db.SELF_SIGNUP_AGE} come with a parent.")
    conns = db.accepted_connections(DB, parent["_id"])
    if not conns:
        ui.empty("🤝", "No pals yet. Send or accept a request first.")
    for conn in conns:
        mine_is_from = conn["from_parent"] == parent["_id"]
        my_kid = db.get_child(DB, conn["from_child" if mine_is_from else "to_child"])
        their_kid = db.get_child(DB, conn["to_child" if mine_is_from else "from_child"])
        other_parent = db.get_parent(DB, conn["to_parent" if mine_is_from else "from_parent"])
        if not (my_kid and their_kid and other_parent):
            continue

        with st.expander(f"{ui.avatar(my_kid)} {my_kid['first_name']} & {ui.avatar(their_kid)} "
                         f"{their_kid['first_name']} · {', '.join(conn['shared_hobbies'])}", expanded=True):
            who = "Contact" if is_member(other_parent) else f"{their_kid['first_name']}'s parent"
            st.markdown(f"**{who}:** {other_parent['name']}  \n"
                        f"📞 {other_parent['phone']} · ✉️ {other_parent['email']}")
            meetup_section(parent, conn, my_kid, their_kid, other_parent)


def meetup_section(parent, conn, my_kid, their_kid, other_parent):
    cid = str(conn["_id"])
    meetup = db.get_meetup(DB, conn["_id"])
    chosen = meetup.get("chosen") if meetup else None
    confirmed = [str(p) for p in (meetup.get("confirmed_by", []) if meetup else [])]

    if meetup and chosen is not None:
        opt = meetup["options"][chosen]
        both = len(confirmed) >= 2
        box = st.success if both else st.info
        box(f"**{'✅ Confirmed' if both else '⏳ Proposed'} meetup:** {opt['place']} ({opt['area']})  \n"
            f"🗓️ {opt['day']}, {opt['time']}  \n🎯 {opt['activity']}")
        if not both:
            if str(parent["_id"]) in confirmed:
                st.caption(f"Waiting for {other_parent['name']} to confirm.")
            elif st.button("✅ Confirm this meetup", key=f"conf_{cid}", type="primary"):
                db.confirm_meetup(DB, conn["_id"], parent["_id"])
                st.rerun()

    st.markdown("#### ✨ Plan with AI")
    availability = st.text_input("When are you both free?", key=f"avail_{cid}",
                                 placeholder="e.g. Friday or Saturday afternoon")
    notes = st.text_input("Anything else? (optional)", key=f"notes_{cid}",
                          placeholder="e.g. indoor place, close to the metro")
    if st.button("✨ Suggest meetups", key=f"plan_{cid}", type="primary"):
        if not availability.strip():
            st.error("Tell us when you're free first.")
        else:
            with st.spinner("AI is planning..."):
                try:
                    options = ai.plan_meetups(
                        conn["shared_hobbies"], [my_kid["age"], their_kid["age"]],
                        my_kid["country"], my_kid["governorate"], my_kid["city"],
                        sorted({my_kid["neighborhood"], their_kid["neighborhood"]}),
                        availability, notes, my_kid.get("gender", ""))
                except Exception as e:
                    options = []
                    st.error(f"The AI couldn't plan right now: {e}")
            if options:
                db.save_meetup_options(DB, conn["_id"], options)
                st.rerun()

    if meetup and meetup.get("options"):
        st.caption("Pick one to propose it to the other side.")
        for i, opt in enumerate(meetup["options"]):
            with st.container(border=True, key=f"card_opt_{cid}_{i}"):
                st.markdown(f"**📍 {opt['place']}** · {opt['area']}  \n🗓️ {opt['day']}, {opt['time']}  \n"
                            f"🎯 {opt['activity']}  \n_{opt['why']}_")
                if i != chosen and st.button("Propose this", key=f"pick_{cid}_{i}"):
                    db.choose_meetup_option(DB, conn["_id"], i, parent["_id"])
                    st.rerun()


# ------------------------------------------------------------------ admin
def admin_page():
    ui.page_header("Admin", "Review hobbies the AI wasn't sure about.")
    pending = db.pending_hobbies(DB)
    if not pending:
        ui.empty("🎉", "Nothing to review.")
    for h in pending:
        c1, c2, c3 = st.columns([3, 1, 1])
        c1.write(h["name"])
        if c2.button("Approve", key=f"ap_{h['_id']}"):
            db.set_hobby_approved(DB, h["_id"], True)
            st.rerun()
        if c3.button("Reject", key=f"rj_{h['_id']}"):
            db.set_hobby_approved(DB, h["_id"], False)
            st.rerun()


# ------------------------------------------------------------------ main
parent = current_parent()
if not parent:
    login_page()
    st.stop()

home = ("My profile", profile_page) if is_member(parent) else ("My kids", kids_page)
pages = {home[0]: home[1], "Find pals": find_page, "Requests": requests_page,
         "Pals & meetups": meetups_page}
if is_admin(parent):
    pages["Admin"] = lambda _p: admin_page()

with st.sidebar:
    html('<div class="np-logo">🤝 Near<span>Pal</span></div>')
    html(f'<div class="np-hello">👋 Hi, <b>{ui.escape(parent["name"])}</b><br>'
         f'📍 {ui.escape(parent["neighborhood"])}, {ui.escape(parent["city"])}</div>')
    page = st.radio("Go to", list(pages), key="nav", label_visibility="collapsed",
                    format_func=lambda p: f"{ui.PAGE_STYLES.get(p, ('✨',))[0]}  {p}")
    n_in = len(db.incoming_requests(DB, parent["_id"]))
    if n_in:
        st.warning(f"📬 {n_in} new pal request{'s' if n_in > 1 else ''}")
    st.divider()
    if st.button("🚪 Log out", width="stretch"):
        st.session_state.clear()
        st.rerun()

    with st.popover("🗑️ Delete account", width="stretch"):
        what = "your profile" if is_member(parent) else "all your kids"
        st.warning(f"This permanently deletes your account, {what}, and all pal "
                   "connections and meetups. It can't be undone.")
        pw = st.text_input("Enter your password to confirm", type="password", key="del_pw")
        if st.button("Delete my account", type="primary", key="del_btn"):
            if verify_password(pw, parent["password_hash"]):
                db.delete_account(DB, parent["_id"])
                st.session_state.clear()
                st.rerun()
            else:
                st.error("Wrong password.")

pages[page](parent)
