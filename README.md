PWMU Unified AI Control-Room Dashboard
AI-Based Plastic Waste Management Unit Monitoring System

Team EchoByte

Project Overview

PWMU Unified AI Control-Room Dashboard is an AI-powered monitoring platform developed for Plastic Waste Management Units (PWMUs). The system integrates Computer Vision, Deep Learning, IoT, and Cloud Technologies to automate waste monitoring, vehicle tracking, plastic segregation, security surveillance, and operational reporting through a single intelligent dashboard.

The platform combines multiple AI modules into one centralized control room for real-time monitoring and decision making.

System Modules
1. Gate & Security
Vehicle Entry Counting
Vehicle Exit Counting
Automatic Number Plate Recognition (ANPR)
Number Plate Search
Manual Plate Entry
Vehicle History
2. AI Waste Segregation
Primary Segregation
Metal
Other Waste
Secondary Plastic Classification

Detects

PET
HDPE
PVC
LDPE
PP
PS
Others

using custom-trained YOLO models.

3. PWMU Shed Security

Features

AI Intrusion Detection
Loitering Detection
Theft Detection
Browser Alarm
Telegram Notification
Image Capture
Cloud Event Storage
4. Analytics Dashboard

Real-time monitoring dashboard including

Vehicle Statistics
Waste Statistics
Plastic Composition
Revenue Estimation
Daily Reports
Weekly Reports
Monthly Reports
Audit Reports
PDF Export
Key Features
AI-powered Waste Segregation
Vehicle Counting
Automatic Number Plate Recognition
Real-time Dashboard
Live Camera Streaming
Video Upload Processing
Multi-language Support
Secure User Authentication
Supabase Cloud Storage
Telegram Security Alerts
CSV Export
PDF Report Generation
Responsive UI
Modular Architecture
What's New (Final Update)
Performance Improvements
Background AI Model Warm-up
Faster Camera Startup
Multi-threaded Video Processing
Queue-based Frame Streaming
Lower CPU Usage
Lower RAM Consumption
Authentication
Secure Login
Secure Registration
User Profile
Session Management
Protected Routes
Dashboard Improvements
New Executive Command Center
Professional Dashboard Layout
Institutional Branding
Modern Navigation
Responsive Design
AI Improvements
Track-based ANPR
Multi-frame OCR Verification
Character Voting
Duplicate Plate Removal
Improved Detection Accuracy
Cloud Integration
Supabase Authentication
Cloud Database
Image Storage
Storage Buckets
Event Logging
Reporting
CSV Export
PDF Export
Analytics Dashboard
Historical Records
Technology Stack
Frontend
HTML5
CSS3
Bootstrap 5
JavaScript
Backend
Python
Flask
AI Models
YOLOv8
EasyOCR
OpenCV
Database
Supabase
PostgreSQL
Cloud
Supabase Storage
Reporting
ReportLab
Matplotlib
Repository Structure
PWMU-System/
│
├── frontend/
│   ├── templates/
│   ├── static/
│   │   ├── css/
│   │   ├── js/
│   │   ├── images/
│   │   └── icons/
│
├── backend/
│   ├── app.py
│   ├── config.py
│   ├── modules/
│   ├── auth/
│   ├── reports/
│   └── utils/
│
├── ai_models/
│   ├── waste_primary.pt
│   ├── final_7types.pt
│   ├── number_plate.pt
│   └── yolov8s.pt
│
├── hardware/
│   ├── IoT/
│   ├── Arduino/
│   └── ESP32/
│
├── api/
│
├── documentation/
│   ├── Installation_Guide.pdf
│   ├── Architecture.pdf
│   └── User_Manual.pdf
│
├── screenshots/
│
├── outputs/
├── uploads/
├── captures/
│
├── README.md
├── requirements.txt
├── .env.example
├── supabase_schema.sql
└── LICENSE
Installation Guide
git clone https://github.com/saveyagroup-cell/PWMU-System.git

cd PWMU-System

python -m venv venv

venv\Scripts\activate

pip install -r requirements.txt

python app.py
Environment Variables
FLASK_SECRET_KEY=

SUPABASE_URL=

SUPABASE_ANON_KEY=

SUPABASE_SERVICE_ROLE_KEY=

SUPABASE_BUCKET=

SUPABASE_ANPR_BUCKET=

SUPABASE_SECURITY_BUCKET=

TELEGRAM_BOT_TOKEN=

TELEGRAM_CHAT_ID=

CAMERA_INDEX=0
FRAME_SKIP=2
JPEG_QUALITY=75
Deployment Instructions

Supported Platforms

Render (Recommended)
Railway
Docker
Local Server
Team Members
Name	Role
Nomend Kumar Sahu	Team Lead
Yogesh Kumar Yadav	Backend Developer
Harsha Sahu	Frontend Developer
Dagendra Kumar Sahu	AI & IoT Developer
Jayant Verma	AI & IoT Developer
System Screenshots
screenshots/

home_dashboard.png

gate_security.png

ai_segregation.png

analytics_dashboard.png

login_page.png

report_generation.png
Live Demo
https://your-render-link.onrender.com
Documentation
Installation Guide
User Manual
API Documentation
Database Schema
Project Architecture
License

Developed by Team EchoByte for the AI-Based Plastic Waste Management Unit (PWMU) Monitoring System, Department of Computer Science & Engineering, NIT Raipur.
