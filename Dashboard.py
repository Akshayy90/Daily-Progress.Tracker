import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from fpdf import FPDF
from io import BytesIO
from collections import Counter
import plotly.express as px

# GitLab API Configuration
GITLAB_API = "https://code.swecha.org/api/v4"
ACCESS_TOKEN = st.secrets["GITLAB_TOKEN"]
HEADERS = {"PRIVATE-TOKEN": ACCESS_TOKEN}

# Get today's date in UTC and IST
today_utc = datetime.utcnow().date()
today_ist = (datetime.utcnow() + timedelta(hours=5, minutes=30)).date()


def fetch_user_events(username):
    url = f"{GITLAB_API}/users?username={username}"
    resp = requests.get(url, headers=HEADERS)
    if not resp.ok or not resp.json():
        return None, []

    user_id = resp.json()[0]['id']
    events_url = f"{GITLAB_API}/users/{user_id}/events"
    events_resp = requests.get(events_url, headers=HEADERS)

    if not events_resp.ok:
        return user_id, []

    events = events_resp.json()
    push_events = []

    for event in events:
        if event['action_name'] == 'pushed to':
            event_time = datetime.strptime(event['created_at'], "%Y-%m-%dT%H:%M:%S.%fZ") + timedelta(hours=5, minutes=30)
            if event_time.date() == today_ist:
                push_events.append({
                    "project": event['project_id'],
                    "branch": event['push_data'].get('ref'),
                    "time": event_time.strftime("%I:%M %p")
                })

    return user_id, push_events


def resolve_project_name(project_id):
    project_url = f"{GITLAB_API}/projects/{project_id}"
    project_resp = requests.get(project_url, headers=HEADERS)
    if project_resp.ok:
        return project_resp.json().get("name", "Unknown")
    elif project_resp.status_code == 404:
        return "Project not found or private"
    elif project_resp.status_code == 403:
        return "Access denied"
    return "Unknown"


def generate_pdf(dataframe):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    for idx, row in dataframe.iterrows():
        pdf.set_text_color(0, 0, 0)
        pdf.cell(200, 10, txt=f"Username: {row['username']}", ln=True)
        pdf.cell(200, 10, txt=f"Push Events: {row['push_events']}", ln=True)
        activities = row['activity'].split("\n")
        for act in activities:
            pdf.cell(200, 10, txt=f"{act}", ln=True)
        pdf.ln(5)

    pdf_output = pdf.output(dest='S').encode('utf-8')
    buffer = BytesIO(pdf_output)
    return buffer


# Streamlit UI
st.set_page_config(page_title="GitLab Daily Progress Tracker", layout="wide")
st.title("📊 GitLab Daily Progress Tracker")

# Tabs
tab1, tab2 = st.tabs(["Bulk CSV Upload", "Individual User Activity"])

with tab1:
    uploaded_file = st.file_uploader("Upload a CSV file with 'username' column", type=["csv"])
    if uploaded_file:
        users_df = pd.read_csv(uploaded_file)
        results = []

        for username in users_df['username']:
            user_id, events = fetch_user_events(username)
            activity_log = []
            for event in events:
                project_name = resolve_project_name(event['project'])
                activity_log.append(f"Pushed to '{event['branch']}' in '{project_name}' at {event['time']}")

            results.append({
                "username": username,
                "push_events": len(events),
                "activity": "\n".join(activity_log) if activity_log else "No push events today."
            })

        result_df = pd.DataFrame(results)
        st.dataframe(result_df)

        pdf_buffer = generate_pdf(result_df)
        st.download_button("📄 Download PDF Report", data=pdf_buffer, file_name="daily_report.pdf")

with tab2:
    username = st.text_input("GitLab Username", placeholder="Please enter your GitLab username")
    if username:
        user_id, events = fetch_user_events(username)
        if user_id is None:
            st.error("User not found.")
        else:
            st.markdown(f"### 👤 Activity Summary for `{username}`")
            if not events:
                st.info("No push events today.")
            else:
                activity_data = []
                for event in events:
                    project_name = resolve_project_name(event['project'])
                    activity_data.append({
                        "Project": project_name,
                        "Branch": event['branch'],
                        "Time": event['time']
                    })
                    st.markdown(f"- Pushed to **{event['branch']}** in **{project_name}** at **{event['time']}**")

                df = pd.DataFrame(activity_data)
                df.index += 1
                st.markdown("### 📊 Activity Breakdown")
                st.dataframe(df)

                proj_count = Counter([d['Project'] for d in activity_data])
                chart_df = pd.DataFrame(proj_count.items(), columns=['Project', 'Commits'])
                fig = px.bar(chart_df, x='Project', y='Commits', title='Commits by Project', color='Project')
                st.plotly_chart(fig)

                time_df = df.copy()
                time_df['Time'] = pd.to_datetime(time_df['Time'], format='%I:%M %p')
                time_df = time_df.sort_values('Time')
                fig2 = px.scatter(time_df, x='Time', y='Project', title='Push Timeline', color='Branch', symbol='Project')
                st.plotly_chart(fig2)

                st.markdown("### 💡 Key Insights")
                st.markdown(f"- Total push events today: **{len(events)}**")
                st.markdown(f"- Worked on **{df['Project'].nunique()}** unique projects")
                st.markdown(f"- Most active project: **{df['Project'].mode()[0]}**")
