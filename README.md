#  Grace - Virtual Nurse Assistant

Grace is an intelligent healthcare chatbot designed to assist patients with symptom tracking, appointment scheduling, and medication reminders — all through natural conversation.

Grace offers voice input, multilingual responses, and real-time interaction via a clean Bootstrap-powered interface.

---

##  Features

- **Conversational AI** (powered by OpenAI GPT-3.5)
- **Voice Input & Output**
  - 🎤 Speak to Grace using your mic
  - 🔊 She talks back with a friendly voice
- **Session Memory**
  - Remembers name & symptoms in current chat
- **Appointment Booking**
  - Integrates with **Google Calendar API**
  - Displays upcoming appointment slots
- **Medication Reminder System**
  - Add medications with dosage & duration
  - Sends **daily email, SMS**, and **voice** reminders
- **Emergency Detection**
  - Detects critical symptoms like "chest pain"
- **Clean UI** (Bootstrap 5)
  - Responsive chat interface with typing animation and Grace avatar

---

##  Tech Stack

- **Python** (Flask)
- **JavaScript + HTML/CSS** (Bootstrap UI)
- **OpenAI GPT-3.5 Turbo**
- **Google Calendar API**
- **Twilio SMS**
- **Gmail SMTP** (Email reminders)
- **SpeechRecognition** (Mic input in Python)
- **Web Speech API** (Mic + TTS in browser)
- **SQLite** (Appointment & medication tracking)
- **APScheduler** (Daily reminder scheduling)

---

##  Setup Instructions

### 1. Clone this repo

```bash
git clone https://github.com/yourusername/grace-nurse-assistant.git
cd grace-nurse-assistant

2. Install Dependencies
bash
Copy
Edit
pip install -r requirements.txt
Make sure you have:

Python 3.7+

A virtual environment (recommended)

3. Add API Keys
Create a .env file (or insert directly in grace_chatbot_gui.py):

env
Copy
Edit
OPENAI_API_KEY=your_openai_key
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
EMAIL_ADDRESS=your.email@gmail.com
EMAIL_APP_PASSWORD=your_app_password
Also place your Google Calendar API credentials.json file in the root.

4. Run the App
bash
Copy
Edit
python grace_chatbot_gui.py
Then open your browser and go to:
http://localhost:5000

Project Structure
csharp
Copy
Edit
grace-nurse-assistant/
│
├── static/                  # Frontend HTML/CSS/JS
│   └── index.html
│
├── grace_chatbot_gui.py     # Main Flask app
├── medication_reminder.py   # Reminder DB + scheduler
├── credentials.json         # Google Calendar credentials
├── grace_hospital.db        # SQLite database (auto-created)
├── README.md
└── requirements.txt
✅ Optional Enhancements
📄 PDF summary generation

🗣️ Multilingual support

🔐 Patient login & secure history

🧠 LangChain for medical documents

📊 Health dashboard (graphs of logs/symptoms)

Created By
Rachel Heke
Bachelor of Software Engineering
Media Design School – Auckland, NZ

“I built Grace to feel like a real assistant — helpful, human, and available 24/7.”