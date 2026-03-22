# RoutineAI 🤖⏰

> An AI-powered personal routine management system with predictive analytics, real-time alarms, and Gemini AI coaching — built as a Progressive Web App installable on any device.

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Click%20Here-7c6fef?style=for-the-badge)](https://daily-reminder-app-4dhl.onrender.com)
[![PWA](https://img.shields.io/badge/PWA-Installable-green?style=for-the-badge&logo=pwa)](https://daily-reminder-app-4dhl.onrender.com)
[![Gemini AI](https://img.shields.io/badge/Gemini-2.5%20Flash-blue?style=for-the-badge&logo=google)](https://ai.google.dev)
[![Python](https://img.shields.io/badge/Python-Flask-yellow?style=for-the-badge&logo=python)](https://flask.palletsprojects.com)

---

## 📌 Project Overview

RoutineAI is a full-stack AI-powered productivity application designed to help users manage their daily routines intelligently. It goes beyond a simple scheduler — it learns from your behaviour, predicts your productivity patterns, and delivers personalised coaching through Google's Gemini AI.

This project was built end-to-end: from ideation and UI/UX design to backend development, AI integration, predictive analytics, and cloud deployment — demonstrating a complete data-driven product development lifecycle.

---

## 🎯 Key Features

### ⏰ Smart Alarm System
- Real-time countdown timer (HH:MM:SS) for every activity
- Web Audio API alarm that fires at each task's start time
- Customisable snooze duration (5, 10, 15, 30 minutes)
- Alarm fires even when screen is locked (via Service Worker)

### 🗓️ Fully Editable Routines
- Create, edit, delete tasks with custom start/end times
- Multiple named routines (e.g. Home Workout, Gym Day, Weekend)
- Select one or multiple routines to run simultaneously
- Auto-detects MRP Project (Sat/Sun/Mon) vs Own Project (Tue–Fri)

### 🤖 Gemini AI Coaching
- Sends your real completion history to Google Gemini 2.5 Flash
- Returns personalised 5-point coaching analysis:
  - Overall performance trend summary
  - Strongest consistently completed task
  - Biggest challenge area
  - Specific actionable improvement tip
  - Personalised motivational closing
- Insights cached for 6 hours to minimise API calls
- API key stored server-side — users need zero setup

### 📊 Predictive Analytics
- **Productivity Heatmap** — 24-hour heatmap showing completion rates by hour of day
- **Trend Analysis** — 6-week bar chart with linear regression to detect improving/declining/steady performance
- **Weekly Pattern** — day-of-week completion rate bars identifying best and toughest days
- **Behind Schedule Detection** — real-time warning if you're falling behind today's targets
- **Task Improvement Suggestions** — flags tasks with <60% historical completion rate with contextual advice

### 📸 Photo Proof Completion
- Upload a photo to mark a task complete
- AI analyses the photo and scores it 1–10 with feedback
- Encourages accountability through visual evidence

### 🔥 Streak & Progress Tracking
- Daily streak counter (consecutive days all tasks completed)
- Persistent localStorage — data survives browser restarts
- Progress bar showing % of day completed
- Undo done functionality

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────┐
│                   CLIENT SIDE                    │
│  Progressive Web App (HTML + CSS + JS)           │
│  ├── Service Worker (offline + push alerts)      │
│  ├── localStorage (routines, history, streak)    │
│  └── Web Audio API (alarm sounds)                │
└──────────────────────┬──────────────────────────┘
                       │ HTTP
┌──────────────────────▼──────────────────────────┐
│                  SERVER SIDE                     │
│  Flask (Python) — Render.com Free Tier           │
│  ├── GET  /        → serves PWA shell            │
│  ├── GET  /sw.js   → service worker              │
│  ├── POST /api/gemini → proxies to Gemini API    │
│  └── GET  /static/ → manifest, icons             │
└──────────────────────┬──────────────────────────┘
                       │ HTTPS REST
┌──────────────────────▼──────────────────────────┐
│              GOOGLE GEMINI 2.5 FLASH             │
│  ├── Text generation (coaching insights)         │
│  └── Image analysis (photo proof scoring)        │
└─────────────────────────────────────────────────┘
```

---

## 📈 Analytical Methods Used

| Method | Purpose | Implementation |
|---|---|---|
| **Historical Frequency Analysis** | Completion rates per hour/day/task | Scan localStorage day records |
| **Linear Regression** | Trend direction over 6 weeks | Least squares slope calculation |
| **Time-of-Day Pattern Detection** | Peak productivity hours | 2-hour block aggregation |
| **Threshold-based Anomaly Detection** | Behind-schedule warning | Real-time task count comparison |
| **Per-task Success Rate** | Low-performance task flagging | Rolling completion percentage |
| **Day-of-week Aggregation** | Best/worst day identification | 7-bucket daily average |
| **LLM Reasoning (Gemini AI)** | Personalised coaching | Structured prompt with user history context |

---

## 🛠️ Tech Stack

**Frontend**
- Vanilla JavaScript (ES6+)
- CSS3 with custom properties (dark/light adaptive)
- Web Audio API for alarm synthesis
- Service Worker API for PWA + offline support
- localStorage for client-side persistence

**Backend**
- Python 3 + Flask
- Pillow (icon generation)
- Requests (Gemini API proxy)

**AI & APIs**
- Google Gemini 2.5 Flash (text generation + image analysis)
- Web Notifications API
- beforeinstallprompt API (PWA install)

**DevOps**
- GitHub (version control)
- Render.com (free cloud hosting)
- Progressive Web App (installable on Android, iOS, Windows)

---

## 🚀 Getting Started

### Run locally
```bash
git clone https://github.com/Mallika-434/Daily-Reminder-App.git
cd Daily-Reminder-App
pip install -r requirements.txt
```

Create a `.env` file:
```
GEMINI_API_KEY=your_gemini_api_key_here
```

```bash
python routineai.py
```

Open `http://localhost:5000`

### Deploy to Render
1. Fork this repo
2. Connect to [render.com](https://render.com)
3. Add `GEMINI_API_KEY` as an environment variable
4. Deploy — Procfile handles the rest

---

## 📱 Install as App

| Platform | Steps |
|---|---|
| **Android (Chrome)** | Open link → tap "Add to Home Screen" banner |
| **Windows (Chrome)** | Open link → click ⊕ icon in address bar → Install |
| **iPhone (Safari)** | Open link → Share → Add to Home Screen |

---

## 🔮 Future Enhancements

- [ ] Multi-user support with authentication
- [ ] Google Calendar sync
- [ ] ML-based task completion prediction (scikit-learn)
- [ ] Natural language task creation ("Add gym at 7am tomorrow")
- [ ] Wearable device integration (smartwatch alerts)
- [ ] Export analytics as PDF report

---

## 👩‍💻 About

Built by **Mallika** — MSc Data Analytics student passionate about building AI-powered tools that solve real everyday problems.

This project demonstrates practical application of:
- Full-stack web development
- AI/LLM integration and prompt engineering
- Predictive analytics and statistical methods
- Cloud deployment and DevOps
- UX design for productivity tools

---

## 📄 License

MIT License — feel free to fork and build on this!

---

*Built with Claude AI assistance · Powered by Google Gemini · Hosted on Render*
