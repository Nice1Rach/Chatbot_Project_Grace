import sqlite3
from datetime import datetime, timedelta

# Create medications table if it doesn’t exist
def init_medication_db():
    with sqlite3.connect("grace_hospital.db") as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS medications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                dosage TEXT,
                times_per_day INTEGER,
                start_date TEXT,
                duration_days INTEGER,
                notes TEXT
            )
        ''')
        conn.commit()

# Add new medication and schedule reminders
def add_medication(name, dosage, times_per_day, duration_days, notes=""):
    start_date = datetime.now().date().isoformat()
    with sqlite3.connect("grace_hospital.db") as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO medications (name, dosage, times_per_day, start_date, duration_days, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (name, dosage, times_per_day, start_date, duration_days, notes)
        )
        conn.commit()

# Check and return reminders due today
def get_today_medications():
    today = datetime.now().date()
    reminders = []
    with sqlite3.connect("grace_hospital.db") as conn:
        c = conn.cursor()
        c.execute("SELECT name, dosage, times_per_day, start_date, duration_days FROM medications")
        for name, dosage, times, start_str, duration in c.fetchall():
            start = datetime.fromisoformat(start_str).date()
            end = start + timedelta(days=duration)
            # Check if today's date falls within the medication period
            if start <= today <= end:
                reminders.append(f"Take {dosage} of {name} - {times} times today")
    return reminders

# Example usage:
if __name__ == '__main__':
    init_medication_db()
    # Add a sample medication reminder
    add_medication("Amoxicillin", "500mg", 3, 7, notes="After meals")
    print("Today's reminders:")
    for r in get_today_medications():
        print("-", r)
