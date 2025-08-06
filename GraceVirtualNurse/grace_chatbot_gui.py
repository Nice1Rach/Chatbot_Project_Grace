import openai
import sqlite3
import speech_recognition as sr
import pyttsx3
import time
import random
import smtplib
import re
from twilio.rest import Client
from email.mime.text import MIMEText
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from datetime import datetime, timezone, timedelta
from googleapiclient.discovery import build
from google.oauth2 import service_account
from medication_reminder import (
    init_medication_db,
    add_medication,
    get_today_medications
)
from apscheduler.schedulers.background import BackgroundScheduler
from collections import defaultdict

import os
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN")

# --- Configurations ---
openai.api_key = "OPENAI_API_KEY"  # Replace with your key or load from environment
app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

# --- Google Calendar Credentials ---
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
SERVICE_ACCOUNT_FILE = 'credentials.json'
creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)

# --- Session Memory ---
session_memory = defaultdict(lambda: {
    "name": None,
    "symptoms": [],
    "last_topic": "",
    "last_appointment": None,
    "available_slots": [],
    "greeted": False
})

# --- Helper: Intent Recognition ---
def get_user_intent(user_input):
    user_input = user_input.lower().strip()
    
    # Check for summary intent first.
    if "summary" in user_input:
        return "summary"
    
    # Prioritize name extraction.
    if "my name is" in user_input:
        return "provide_name"
    
    # Check for symptom keywords.
    symptom_keywords = ["headache", "fever", "cough", "pain", "stuffy", "sore throat", "chills", "sore"]
    if any(keyword in user_input for keyword in symptom_keywords):
        return "symptom"
    
    # Check for greetings using whole words.
    greeting_keywords = ["hi", "hello", "hey"]
    if any(word in user_input.split() for word in greeting_keywords):
        return "greeting"
    
    # Appointment-related intents.
    if "confirm" in user_input or user_input in ["yes", "y"]:
        return "confirm_booking"
    if "book" in user_input or "appointment" in user_input:
        if "cancel" in user_input:
            return "cancel_appointment"
        elif "reschedule" in user_input:
            return "reschedule_appointment"
        else:
            return "book_appointment"
    if "remind" in user_input or "medication" in user_input:
        return "medication_reminder"
    
    return "unknown"

def get_greeting(memory):
    if not memory.get("greeted"):
        memory["greeted"] = True
        prompt = (
            "You are Grace, a compassionate virtual nurse. "
            "Greet a new patient warmly and ask for their name. "
            "Make your greeting natural and empathetic."
        )
        return generate_response(prompt)
    elif not memory.get("name"):
        return "I’d love to know your name before we continue. What is your name?"
    else:
        prompt = (
            f"Patient's name is {memory['name']}. "
            "Greet them warmly and ask how you can help today."
        )
        return generate_response(prompt)

# --- Booking Helpers ---
def book_appointment(doctor_name, date, time_str):
    # Create a summary and time details
    event = {
        'summary': f'Appointment with {doctor_name}',
        'start': {
            'dateTime': f'{date}T{time_str}:00',
            'timeZone': 'UTC'
        },
        'end': {
            'dateTime': f'{date}T{time_str}:30',  # Assuming a 30-minute slot
            'timeZone': 'UTC'
        }
    }
    service = build('calendar', 'v3', credentials=creds)
    event_result = service.events().insert(calendarId='primary', body=event).execute()
    return f"Appointment booked with {doctor_name} on {date} at {time_str}."

def remove_slot(doctor_name, date, time):
    slots = doctors_schedule.get(doctor_name, [])
    for slot in slots:
        if slot["date"] == date and slot["time"] == time:
            slots.remove(slot)
            break

# --- Other Helper Functions ---
def list_available_slots(memory):
    if not memory.get("available_slots"):
        return "I don’t see any available slots at the moment. Could you try again later?"
    return "\n".join([f"Slot {i+1}: {slot}" for i, slot in enumerate(memory["available_slots"])])

def confirm_slot(slot_text, memory):
    parts = slot_text.split(" with ", 1)
    if len(parts) < 2:
        return "There was an issue with the slot format. Please try again."
    start_time, doctor = parts
    memory["last_appointment"] = slot_text
    memory["last_topic"] = "booking_confirmed"
    return f"📅 Appointment with {doctor} at {start_time} confirmed."

def handle_symptoms(user_input, memory):
    # Build a dynamic prompt for ChatGPT to generate an empathetic response.
    prompt = (
        "You are Grace, a compassionate virtual nurse for Grace Hospital. "
        "A patient reports the following symptoms: '" + user_input + "'. "
        "Provide an empathetic response that acknowledges the symptoms and offers guidance. "
        "Also, ask if the patient would like to schedule an appointment if their condition worsens."
    )
    return generate_response(prompt)

def set_medication_reminder(times):
    # times should be a list of strings like ["08:00 AM", "12:00 PM", "6:00 PM"]
    for t in times:
        send_email("user@example.com", "Medication Reminder", f"Please take your medication at {t}.")
        send_sms("", f"Please take your medication at {t}.")
    return "Great! I’ll remind you at the times you mentioned."

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect("grace_hospital.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_input TEXT,
        response TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

def log_symptom(user_input, response):
    conn = sqlite3.connect("grace_hospital.db")
    c = conn.cursor()
    c.execute("INSERT INTO appointments (user_input, response) VALUES (?, ?)", (user_input, response))
    conn.commit()
    conn.close()

# --- Voice Helpers ---
def listen_to_user():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("Grace is listening...")
        audio = recognizer.listen(source)
        try:
            return recognizer.recognize_google(audio)
        except sr.UnknownValueError:
            return "Sorry, I couldn't understand that."
        except sr.RequestError:
            return "Error connecting to the speech recognition service."

def speak_response(text):
    engine = pyttsx3.init()
    engine.setProperty("rate", 135)
    engine.say(text)
    engine.runAndWait()

# --- Reminder System ---
def send_email(to_email, subject, body):
    from_email = ""
    password = ""  # Remember to secure your credentials!
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(from_email, password)
        server.sendmail(from_email, to_email, msg.as_string())

def send_sms(to_number, message_body):
    account_sid = "TWILIO_ACCOUNT_SID"
    auth_token = "TWILIO_AUTH_TOKEN"
    twilio_number = ''
    client = Client(account_sid, auth_token)
    try:
        message = client.messages.create(
            body=message_body,
            from_=twilio_number,
            to=to_number
        )
        print(f"SMS sent successfully! SID: {message.sid}")
        return message.sid
    except Exception as e:
        print("Error sending SMS via Twilio:", str(e))
        return None

def send_daily_medication_reminders():
    reminders = get_today_medications()
    if reminders:
        msg = "Grace Medication Reminder:\n\n" + "\n".join(reminders)
        send_email("", "Your Daily Medication Reminder", msg)
        send_sms("", msg)
        speak_response(msg)

def speak_night_reminders():
    msg = "Don’t forget to take your evening medication."
    print("[Grace Night Reminder] Sending scheduled message...")
    speak_response(msg)
    send_email("", "Evening Pill Reminder", msg)
    send_sms("", msg)

# --- AI Core ---
def generate_response(prompt):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are Grace, a helpful healthcare chatbot for Grace Hospital."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=200,
        temperature=0.7
    )
    return response.choices[0].message["content"].strip()

def fetch_google_calendar_slots():
    service = build('calendar', 'v3', credentials=creds)
    now = datetime.now(timezone.utc).isoformat()

    # Define potential slots (e.g., every 30 minutes from 9 AM to 5 PM)
    start_of_day = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    end_of_day = datetime.now().replace(hour=17, minute=0, second=0, microsecond=0)
    potential_slots = []
    current_time = start_of_day
    while current_time < end_of_day:
        potential_slots.append(current_time.strftime("%A, %B %d, %Y at %I:%M %p"))
        current_time += timedelta(minutes=30)

    events_result = service.events().list(
        calendarId='primary',
        timeMin=now,
        maxResults=10,
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    slots = potential_slots.copy()
    for event in events_result.get('items', []):
        start_raw = event['start'].get('dateTime', event['start'].get('date'))
        if 'T' in start_raw:
            start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
            formatted_start = start_dt.strftime("%A, %B %d, %Y at %I:%M %p")
            if formatted_start in slots:
                slots.remove(formatted_start)
    return slots

# --- Flask API Endpoint ---
@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_input = data.get("message", "").strip()
    user_input_lower = user_input.lower()
    user_id = "default"
    memory = session_memory[user_id]

    # -- Confirmation Check --
    confirmation_phrases = ["yes", "confirm", "book", "go ahead", "okay", "sure", "please do", "sounds good"]
    if any(phrase in user_input_lower for phrase in confirmation_phrases) and memory.get("available_slots"):
        slot_text = memory["available_slots"][0]
        try:
            # Expected format: "Tuesday, April 01, 2025 at 09:00 AM with Dr. Smith"
            start_time, doctor = slot_text.split(" with ")
        except ValueError:
            start_time = slot_text
            doctor = "your doctor"
        
        event_link = "https://calendar.google.com"  # Placeholder for actual calendar event link.
        send_email("",
                   "Grace Appointment Confirmation",
                   f" Your appointment with {doctor} is confirmed for {start_time}.\nView it here: {event_link}")
        send_sms("", f" Confirmed: {doctor} at {start_time}")
        response_text = f" Your appointment with {doctor} is confirmed! Reminders sent."
        return jsonify({"response": response_text})

    # -- Determine the User's Intent --
    intent = get_user_intent(user_input)

    if intent == "provide_name":
        # Extract name from phrases like "my name is ..." etc.
        name_match = re.search(r"my name is\s+([a-zA-Z]+)", user_input, re.IGNORECASE)
        if name_match:
            memory["name"] = name_match.group(1).capitalize()
            return jsonify({"response": f"Nice to meet you, {memory['name']}! How are you feeling today? Feel free to share any symptoms."})
        else:
            return jsonify({"response": "I didn't catch your name clearly. Could you please repeat it?"})

    elif intent == "greeting":
        if memory.get("name"):
            return jsonify({"response": f"Hello again, {memory['name']}! How can I assist you today?"})
        else:
            return jsonify({"response": "Hello! How can I assist you today? Could you please tell me your name?"})

    elif intent == "symptom":
        response_text = handle_symptoms(user_input, memory)
        return jsonify({"response": response_text})

    elif intent == "book_appointment":
        slots = fetch_google_calendar_slots()
        memory["available_slots"] = slots
        if slots:
            return jsonify({"response": "Here are some available slots:\n" + "\n".join(slots) +
                                        "\nPlease type 'confirm' (or a similar phrase) to book the first available slot."})
        else:
            return jsonify({"response": "No available slots at the moment. Please try again later."})

    elif intent == "confirm_booking":
        # Try to extract a slot number from the user input (e.g., "slot 2" or "2")
        slot_match = re.search(r'slot\s*(\d+)', user_input_lower)
        if slot_match:
            slot_index = int(slot_match.group(1)) - 1  # Convert to zero-based index.
        else:
            slot_index = 0  # Default to the first slot if no number is found.

        if memory.get("available_slots") and slot_index < len(memory["available_slots"]):
            slot_text = memory["available_slots"][slot_index]
            try:
                # Expected format: "Tuesday, April 01, 2025 at 09:00 AM with Dr. Smith"
                start_time, doctor = slot_text.split(" with ")
            except ValueError:
                start_time = slot_text
                doctor = "your doctor"
            
            event_link = "https://calendar.google.com"  # Placeholder for actual event link.
            send_email("",
                       "Grace Appointment Confirmation",
                       f" Your appointment with {doctor} is confirmed for {start_time}.\nView it here: {event_link}")
            send_sms("", f" Confirmed: {doctor} at {start_time}")
            response_text = f" Your appointment with {doctor} is confirmed! Reminders sent."
            return jsonify({"response": response_text})
        else:
            return jsonify({"response": "I couldn't find that slot. Please check the available slots and try again."})

    elif intent == "cancel_appointment":
        return jsonify({"response": "Your appointment has been cancelled."})

    elif intent == "reschedule_appointment":
        slots = fetch_google_calendar_slots()  # Retrieve new available slots.
        memory["available_slots"] = slots      # Store them in memory.
        if slots:
            return jsonify({"response": "Here are your available slots for rescheduling:\n" +
                                        "\n".join(slots) +
                                        "\nPlease type 'confirm' (or a similar phrase) followed by the desired slot number to reschedule your appointment."})
        else:
            return jsonify({"response": "No available slots for rescheduling at the moment. Please try again later."})

    elif intent == "medication_reminder":
        # Medication reminder setup: multi-turn conversation.
        if "med_setup" not in memory:
            memory["med_setup"] = {"step": "ask_med_details"}
            return jsonify({"response": "Sure, let's set up your medication reminder. Please tell me the medication name, dosage, tablet count, and the time you'd like to take it. For example: 'Atomoxetine 80 mgs, 1 tablet at 8:00 AM every day'"})
        else:
            current_step = memory["med_setup"].get("step")
            if current_step == "ask_med_details":
                parts = user_input.split(',')
                if len(parts) >= 2:
                    med_info = parts[0].strip()  # e.g., "Atomoxetine 80 mgs"
                    schedule_info = parts[1].strip()  # e.g., "1 tablet at 8:00 AM every day"
                    memory["med_setup"]["med_info"] = med_info
                    memory["med_setup"]["schedule_info"] = schedule_info
                    memory["med_setup"]["step"] = "confirm_med"
                    return jsonify({"response": f"Okay, you've entered: '{med_info}' and '{schedule_info}'. Should I set up the reminder with these details?"})
                else:
                    return jsonify({"response": "I didn't catch all the details. Please provide medication name, dosage, tablet count, and the time. For example: 'Atomoxetine 80 mgs, 1 tablet at 8:00 AM every day'"})
            elif current_step == "confirm_med":
                if any(word in user_input_lower for word in ["yes", "confirm", "correct"]):
                    med_parts = memory["med_setup"]["med_info"].split()
                    medication_name = med_parts[0]
                    dosage = med_parts[1] if len(med_parts) > 1 else ""
                    
                    time_match = re.search(r'\d{1,2}:\d{2}\s*[APap][Mm]', memory["med_setup"]["schedule_info"])
                    if time_match:
                        time_str = time_match.group(0)
                    else:
                        time_str = "08:00 AM"  # default fallback
                        
                    times_per_day = 1  # default to 1 tablet per day
                    duration_days = 30  # default duration, or you could ask the user for this detail
                    
                    add_medication(
                        medication_name,
                        dosage,
                        times_per_day,
                        duration_days,
                        memory["med_setup"]["schedule_info"]
                    )
                    del memory["med_setup"]
                    return jsonify({"response": f"All set! I'll remind you to take {medication_name} at {time_str} every day."})
                else:
                    del memory["med_setup"]
                    return jsonify({"response": "Okay, let's start over. What medication reminder would you like to set up?"})
            else:
                return jsonify({"response": "I'm sorry, something went wrong with the medication setup. Let's start over. What medication reminder would you like to set up?"})

    elif intent == "summary":
        summary_lines = []
        if memory.get("name"):
            summary_lines.append(f"Patient's name: {memory['name']}")
        if memory.get("symptoms"):
            summary_lines.append(f"Symptoms mentioned: {', '.join(memory['symptoms'])}")
        if memory.get("last_appointment"):
            summary_lines.append(f"Last appointment: {memory['last_appointment']}")
        
        if summary_lines:
            summary = "\n".join(summary_lines)
            return jsonify({"response": f"Here is your summary:\n{summary}"})
        else:
            return jsonify({"response": "I don't have enough information for a summary yet."})

    else:
        # ----- Custom Fallback Branch -----
        formatted_slots = ""
        if memory.get("available_slots"):
            formatted_slots = "\n".join(memory["available_slots"])

        if any(x in user_input_lower for x in ["my name is", "i'm", "i am"]):
            parts = user_input.split()
            for i, word in enumerate(parts):
                if word.lower() in ["is", "i'm", "i", "am"] and i + 1 < len(parts):
                    memory["name"] = parts[i + 1].capitalize()
        for word in user_input.split():
            if word not in memory["symptoms"]:
                memory["symptoms"].append(word)

        name_part = f"Patient's name is {memory['name']}.\n" if memory.get("name") else ""
        symptom_part = f"Recent symptoms mentioned: {', '.join(memory['symptoms'])}\n" if memory.get("symptoms") else ""
        prompt = (
            f"{name_part}{symptom_part}"
            f"The patient says: '{user_input}'.\n"
            f"Here are upcoming available appointment slots:\n{formatted_slots}\n\n"
            f"Provide empathetic healthcare advice. Suggest a slot if appropriate. Use the patient's name if known."
        )
        response_text = generate_response(prompt)
        log_symptom(user_input, response_text)
        return jsonify({"response": response_text})

@app.route("/")
def index():
    return app.send_static_file('index.html')

# --- Scheduler Initialization ---
scheduler = BackgroundScheduler()
scheduler.add_job(send_daily_medication_reminders, 'cron', hour=8, minute=0)
scheduler.add_job(speak_night_reminders, 'cron', hour=21, minute=0)
scheduler.start()

if __name__ == '__main__':
    init_db()
    init_medication_db()
    app.run(debug=True, port=5000)