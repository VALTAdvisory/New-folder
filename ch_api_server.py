import streamlit as st
import requests
import json
from datetime import datetime, date
import pandas as pd   # for table view

# ----------------- CONFIG -----------------
API_KEY = "b52fef15-0797-4fa8-ab2b-a4eada7797c3"  # <- put your Companies House API key here
BASE_URL = "https://api.company-information.service.gov.uk"

st.set_page_config(page_title="CH-Connect", layout="wide")

# ----------------- SESSION STATE -----------------
if "last_company" not in st.session_state:
    st.session_state["last_company"] = None


# ----------------- JSON STORAGE HELPERS -----------------
def load_companies():
    """Load saved companies from companies.json"""
    try:
        with open("companies.json", "r") as f:
            return json.load(f)
    except:
        return []


def save_companies(data):
    """Save list of companies to companies.json"""
    with open("companies.json", "w") as f:
        json.dump(data, f, indent=4)


def add_company(company_data):
    """Add a company to the JSON file, avoid duplicates by CRN"""
    companies = load_companies()
    for c in companies:
        if c["crn"] == company_data["crn"]:
            return False
    companies.append(company_data)
    save_companies(companies)
    return True


def delete_company(crn):
    """Remove a company from the JSON file"""
    companies = load_companies()
    companies = [c for c in companies if c["crn"] != crn]
    save_companies(companies)


# ----------------- COMPANIES HOUSE API -----------------
def get_json(endpoint):
    r = requests.get(f"{BASE_URL}{endpoint}", auth=(API_KEY, ""))
    if r.status_code == 200:
        return r.json()
    return None


def refresh_company_data(crn):
    """Fetch up-to-date company data and return a cleaned dictionary."""
    profile = get_json(f"/company/{crn}")
    if not profile:
        return None

    accounts = profile.get("accounts", {})
    cs = profile.get("confirmation_statement", {})

    return {
        "crn": crn,
        "name": profile.get("company_name"),
        "status": profile.get("company_status"),
        "accounts_due": accounts.get("next_due", "N/A"),
        "cs_due": cs.get("next_due", "N/A"),
        "last_updated": datetime.now().strftime("%Y-%m-%d")
    }


def refresh_all_companies():
    companies = load_companies()
    updated_list = []
    for c in companies:
        updated = refresh_company_data(c["crn"])
        if updated:
            updated_list.append(updated)
    save_companies(updated_list)
    return len(updated_list)


def get_company_profile_api(crn):
    return get_json(f"/company/{crn}")


def get_company_officers(crn):
    return get_json(f"/company/{crn}/officers")


def get_company_charges(crn):
    return get_json(f"/company/{crn}/charges")


def get_company_filings(crn, items_per_page=10):
    return get_json(f"/company/{crn}/filing-history?items_per_page={items_per_page}")


# ----------------- DEADLINE / RELATIVE LABEL HELPERS -----------------
def days_until(date_str):
    """Return days until date (int), negative if in past, or None."""
    if not date_str or date_str == "N/A":
        return None
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        today = date.today()
        return (d - today).days
    except Exception:
        return None


def relative_label(date_str):
    """
    Turn a YYYY-MM-DD date into labels like:
    'in 2 months', 'in 10 days', '2 months ago', 'N/A'
    """
    d = days_until(date_str)
    if d is None:
        return "N/A"
    if d < 0:
        days_ago = abs(d)
        months_ago = days_ago // 30
        if months_ago == 0:
            return f"{days_ago} days ago"
        return f"{months_ago} month{'s' if months_ago != 1 else ''} ago"
    if d < 30:
        return f"in {d} days"
    months = d // 30
    return f"in {months} month{'s' if months != 1 else ''}"


def status_label(date_str: str) -> str:
    """
    Turn a date into a colour-coded status:
    🟢 OK / 🟡 Due soon / 🔴 Overdue / ⚪ N/A
    """
    d = days_until(date_str)
    if d is None:
        return "⚪ N/A"
    if d < 0:
        return "🔴 Overdue"
    if d <= 7:
        return "🟠 Due in 7 days"
    if d <= 30:
        return "🟡 Due in 30 days"
    return "🟢 OK"


def days_remaining(date_str):
    """Wrapper for summary tiles (same as days_until)."""
    return days_until(date_str)


def company_overall_status(company):
    """
    Combine Accounts + CS01 deadlines into one status:
    Overdue / Due in 7 days / Due in 30 days / OK / N/A
    """
    days_list = [
        days_remaining(company.get("accounts_due")),
        days_remaining(company.get("cs_due")),
    ]
    days_list = [d for d in days_list if d is not None]
    if not days_list:
        return "N/A"

    min_days = min(days_list)
    if min_days < 0:
        return "Overdue"
    if min_days <= 7:
        return "Due in 7 days"
    if min_days <= 30:
        return "Due in 30 days"
    return "OK"


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Convert DataFrame to CSV bytes for download."""
    return df.to_csv(index=False).encode("utf-8")


def show_company_details(crn: str):
    """Show a rich details panel for a single company."""
    profile = get_company_profile_api(crn)
    officers = get_company_officers(crn) or {}
    charges = get_company_charges(crn) or {}
    filings = get_company_filings(crn, items_per_page=10) or {}

    if not profile:
        st.warning("Could not load details from Companies House.")
        return

    st.markdown("---")
    st.subheader(f"📄 Company details – {profile.get('company_name', '')} ({crn})")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Overview**")
        st.write(f"**Status:** {profile.get('company_status', 'N/A')}")
        st.write(f"**Incorporated on:** {profile.get('date_of_creation', 'N/A')}")
        sic = profile.get("sic_codes") or []
        st.write(f"**SIC codes:** {', '.join(sic) if sic else 'N/A'}")

        addr = profile.get("registered_office_address", {}) or {}
        if addr:
            st.write("**Registered office:**")
            addr_lines = [
                addr.get("address_line_1", ""),
                addr.get("address_line_2", ""),
                addr.get("locality", ""),
                addr.get("postal_code", ""),
                addr.get("country", ""),
            ]
            st.write("<br>".join([a for a in addr_lines if a]), unsafe_allow_html=True)

    with col2:
        st.markdown("**Officers (top 5)**")
        o_items = officers.get("items", [])[:5]
        if not o_items:
            st.write("No officers data available.")
        else:
            for o in o_items:
                name = o.get("name", "Unknown")
                role = o.get("officer_role", "N/A")
                appointed = o.get("appointed_on", "N/A")
                resigned = o.get("resigned_on")
                line = f"- {name} — {role} (appointed {appointed}"
                if resigned:
                    line += f", resigned {resigned}"
                line += ")"
                st.write(line)

    st.markdown("**Recent filings**")
    f_items = filings.get("items", [])[:10]
    if f_items:
        filing_rows = []
        for item in f_items:
            filing_rows.append({
                "Date": item.get("date", ""),
                "Type": item.get("type", ""),
                "Description": item.get("description", ""),
            })
        fd = pd.DataFrame(filing_rows)
        st.dataframe(fd, use_container_width=True, hide_index=True)
    else:
        st.write("No filing history available.")

    st.markdown("**Charges**")
    c_items = charges.get("items", []) or []
    if not c_items:
        st.write("No registered charges.")
    else:
        total = charges.get("total_count", len(c_items))
        st.write(f"Total charges: {total}")
        for ch in c_items[:5]:
            status = ch.get("status", "N/A")
            created = ch.get("created_on", "N/A")
            desc = ch.get("secured_details", {}).get("description", "")
            st.write(f"- {status} — created {created} — {desc}")


# ----------------- SIDEBAR MENU -----------------
with st.sidebar:
    menu = st.radio("Menu", ["Dashboard", "My Companies"])


# ----------------- DASHBOARD PAGE -----------------
if menu == "Dashboard":
    st.title("🏢 CH-Connect — Companies House Dashboard")

    crn_input = st.text_input("Enter Company Registration Number")

    # When Search is clicked -> fetch data and store in session_state
    if st.button("Search") and crn_input:
        profile = get_json(f"/company/{crn_input}")

        if not profile:
            st.error("Invalid CRN or API request failed.")
            st.session_state["last_company"] = None
        else:
            st.success("Company Found!")

            name = profile.get("company_name")
            status = profile.get("company_status")
            sic = profile.get("sic_codes")
            accounts = profile.get("accounts", {})
            cs = profile.get("confirmation_statement", {})
            accounts_due = accounts.get("next_due", "N/A")
            cs_due = cs.get("next_due", "N/A")
            address = profile.get("registered_office_address", {})
            date_of_creation = profile.get("date_of_creation")

            # store everything we need for display + saving
            st.session_state["last_company"] = {
                "crn": crn_input,
                "name": name,
                "status": status,
                "sic": sic,
                "address": address,
                "date_of_creation": date_of_creation,
                "accounts_due": accounts_due,
                "cs_due": cs_due,
                "last_updated": datetime.now().strftime("%Y-%m-%d")
            }

    last = st.session_state["last_company"]

    # Only show details + save button if we have a company in memory
    if last:
        name = last["name"]
        status = last["status"]
        sic = last["sic"]
        address = last["address"]
        accounts_due = last["accounts_due"]
        cs_due = last["cs_due"]

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Company Overview")
            st.write(f"**Name:** {name}")
            st.write(f"**Status:** {status}")
            st.write(f"**SIC Codes:** {sic}")
            st.write(f"**Incorporated:** {last['date_of_creation']}")

            if address:
                addr_lines = [
                    address.get("address_line_1", ""),
                    address.get("address_line_2", ""),
                    address.get("locality", ""),
                    address.get("postal_code", ""),
                    address.get("country", "")
                ]
                st.write("**Registered Office:**")
                st.write("<br>".join([a for a in addr_lines if a]), unsafe_allow_html=True)

        with col2:
            st.subheader("Filing Deadlines")
            st.write(f"**Accounts due:** {accounts_due}")
            st.write(f"**CS01 due:** {cs_due}")

        st.markdown(f"**Ready to save:** {name} ({last['crn']})")

        # Save button now uses data from session_state, not local vars
        if st.button("💾 Save to My Companies", key="save_company"):
            data = {
                "crn": last["crn"],
                "name": last["name"],
                "status": last["status"],
                "accounts_due": last["accounts_due"],
                "cs_due": last["cs_due"],
                "last_updated": last["last_updated"]
            }
            if add_company(data):
                st.success(f"{name} saved to your portfolio!")
            else:
                st.warning("This company is already saved.")


# ----------------- MY COMPANIES PAGE (Inform Direct style table) ---------
elif menu == "My Companies":
    st.title("📂 My Companies Portfolio")

    if st.button("🔄 Refresh All Companies"):
        count = refresh_all_companies()
        st.success(f"Updated {count} companies!")
        st.rerun()

    companies = load_companies()

    if not companies:
        st.info("No companies saved yet. Go to Dashboard and save one.")
    else:
        # ------- Filter control -------
        filter_choice = st.radio(
            "Show companies",
            ["All", "Overdue", "Due in 7 days", "Due in 30 days", "OK"],
            horizontal=True,
        )

        if filter_choice == "All":
            filtered_companies = companies
        else:
            filtered_companies = [
                c for c in companies
                if company_overall_status(c) == filter_choice
            ]

        # ---------- Summary Stats (for all companies) ----------
        total = len(companies)
        due_30 = 0
        due_7 = 0
        overdue = 0

        for c in companies:
            for d in (
                days_remaining(c["accounts_due"]),
                days_remaining(c["cs_due"])
            ):
                if d is None:
                    continue
                if d < 0:
                    overdue += 1
                elif d <= 7:
                    due_7 += 1
                elif d <= 30:
                    due_30 += 1

        # ---- Build table rows (for filtered companies only) ----
        rows = []
        for c in filtered_companies:
            acc_due = c["accounts_due"]
            cs_due = c["cs_due"]

            rows.append({
                "Company Name": c["name"],
                "Company Number": c["crn"],

                "Accounts Due Date": acc_due,
                "Accounts Deadline": relative_label(acc_due),
                "Accounts Status": status_label(acc_due),

                "CS01 Due Date": cs_due,
                "CS01 Deadline": relative_label(cs_due),
                "CS01 Status": status_label(cs_due),

                "Company Status": c["status"],
                "Last Updated": c["last_updated"],
            })

        df = pd.DataFrame(rows)

        # Summary tiles
        st.subheader("📊 Portfolio Summary")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Companies", total)
        c2.metric("Due in 30 Days", due_30)
        c3.metric("Due in 7 Days", due_7)
        c4.metric("Overdue", overdue)

        st.markdown("---")

        # Sort by nearest CS01 deadline (like Inform Direct)
        if not df.empty:
            df["__cs_days__"] = df["CS01 Due Date"].apply(
                lambda x: days_until(x) if x not in (None, "N/A", "") else 99999
            )
            df = df.sort_values("__cs_days__").drop(columns="__cs_days__")

            # Download button for the current (filtered + sorted) view
            csv_bytes = df_to_csv_bytes(df)
            st.download_button(
                label="⬇️ Download portfolio as CSV",
                data=csv_bytes,
                file_name="ch_connect_portfolio.csv",
                mime="text/csv",
            )

        st.caption("Your current companies")
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
        )

        # --------- Company details panel ----------
        st.markdown("### Company details")

        if filtered_companies:
            options = [f"{c['name']} ({c['crn']})" for c in filtered_companies]
            choice = st.selectbox("Select a company to view details", options)
            # Extract CRN from "Name (CRN)" string
            selected_crn = choice.rsplit("(", 1)[-1].strip(")")
            show_company_details(selected_crn)
        else:
            st.info("No companies match this filter.")

        st.markdown("### Actions")
        delete_crn = st.text_input("Enter a Company Number to delete")
        if st.button("❌ Delete company"):
            if delete_crn:
                delete_company(delete_crn)
                st.success(f"{delete_crn} removed.")
                st.rerun()
            else:
                st.warning("Please enter a company number first.")
