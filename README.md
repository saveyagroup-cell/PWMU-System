# PWMU Unified AI Control-Room Dashboard

> **AI-Based Plastic Waste Management Unit Monitoring System**

Developed by **Team EchoByte**

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)]()
[![Flask](https://img.shields.io/badge/Flask-3.x-black.svg)]()
[![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-purple.svg)]()
[![OpenCV](https://img.shields.io/badge/OpenCV-Computer%20Vision-green.svg)]()
[![Supabase](https://img.shields.io/badge/Supabase-Database-3ECF8E.svg)]()
[![HuggingFace](https://img.shields.io/badge/Deployment-HuggingFace-yellow.svg)]()

---

# 📌 Project Overview

The **PWMU Unified AI Control-Room Dashboard** is an AI-powered monitoring platform developed for **Plastic Waste Management Units (PWMUs)**. The system integrates Computer Vision, Deep Learning, IoT, and Cloud Technologies to automate waste segregation, vehicle monitoring, number plate recognition, security surveillance, and operational reporting through a centralized dashboard.

The platform enables real-time monitoring of PWMU operations while improving efficiency, transparency, and data-driven decision-making.

---

# 🚀 Key Features

- 🚗 Vehicle Entry & Exit Counting
- 🔍 Automatic Number Plate Recognition (ANPR)
- ♻️ Primary Waste Segregation
- 🧴 Secondary Plastic Classification
- 🛡️ PWMU Shed Security Monitoring
- 📊 Real-Time Analytics Dashboard
- 🔐 Secure User Authentication
- ☁️ Supabase Cloud Integration
- 📸 Image Storage & Detection Logs
- 📄 PDF & CSV Report Generation
- 🌐 Multi-Language Support
- 🎥 Live Camera Streaming
- 📂 Video Upload Processing
- 📱 Responsive Dashboard UI

---

# 🆕 What's New (Latest Version)

## ⚡ Performance Optimization

- Background AI Model Warm-up
- Faster Camera Initialization
- Multi-threaded Video Processing
- Queue-Based Frame Streaming
- Reduced CPU Utilization
- Optimized Memory Usage
- Improved FPS Performance

---

## 🔐 Authentication System

- Secure Login
- Secure Registration
- Supabase Authentication
- User Profile Management
- Protected Dashboard Routes
- Session Management

---

## 🖥️ Dashboard Improvements

- Executive Command Center
- Modern Responsive UI
- Institutional Branding
- Improved Navigation
- Enhanced User Experience

---

## 🤖 AI Improvements

- Track-Based ANPR
- Multi-frame OCR Verification
- Character Voting Algorithm
- Duplicate Plate Detection
- Improved OCR Accuracy
- Faster AI Inference

---

## ☁️ Cloud Integration

- Supabase Database
- Cloud Image Storage
- Detection History
- Secure Storage Buckets
- Automatic Event Logging
- Cloud Synchronization

---

## 📊 Reporting System

- Daily Reports
- Weekly Reports
- Monthly Reports
- Audit Reports
- CSV Export
- PDF Export
- Historical Analytics

---

# 🖥️ System Modules

## 🚗 Gate & Security

- Vehicle Entry Counter
- Vehicle Exit Counter
- Automatic Number Plate Recognition (ANPR)
- Vehicle Search
- Manual Plate Entry
- Vehicle History

---

## ♻️ AI Waste Segregation

### Primary Waste Segregation

- Metal
- Other Waste

### Secondary Plastic Classification

Detects

- PET
- HDPE
- PVC
- LDPE
- PP
- PS
- Others

using custom-trained YOLO models.

---

## 🛡️ PWMU Shed Security

- Intrusion Detection
- Loitering Detection
- Theft Detection
- Browser Alarm
- Telegram Notification
- Image Capture
- Cloud Event Storage

---

## 📈 Analytics Dashboard

- Vehicle Statistics
- Waste Statistics
- Plastic Composition
- Revenue Analysis
- Detection History
- Audit Reports
- PDF Export

---

# 🛠 Technology Stack

## Frontend

- HTML5
- CSS3
- Bootstrap 5
- JavaScript

## Backend

- Python
- Flask

## AI & Computer Vision

- YOLOv8
- OpenCV
- EasyOCR

## Database

- Supabase PostgreSQL

## Cloud Storage

- Supabase Storage

## Reporting

- ReportLab
- Matplotlib

---

# 📂 Repository Structure

```text
PWMU-System/
│
├── frontend/
│   ├── templates/
│   └── static/
│       ├── css/
│       ├── js/
│       ├── images/
│       └── icons/
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
├── documentation/
│
├── screenshots/
│
├── uploads/
├── outputs/
├── captures/
│
├── README.md
├── requirements.txt
├── .env.example
├── supabase_schema.sql
└── LICENSE
```

---

# ⚙️ Installation Guide

```bash
# Clone Repository

git clone https://github.com/saveyagroup-cell/PWMU-System.git

# Open Project

cd PWMU-System

# Create Virtual Environment

python -m venv venv

# Activate Environment (Windows)

venv\Scripts\activate

# Install Dependencies

pip install -r requirements.txt

# Run Application

python app.py
```

---

# 🔐 Environment Variables

Create a `.env` file and configure the following variables:

```env
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

PLATE_FRAME_SKIP=5

JPEG_QUALITY=75
```

---

# 🚀 Deployment

## Hugging Face Spaces (Live)

**Live Demo**

👉 https://huggingface.co/spaces/saveyagroup/PWMU-SYSTEM

---

## Supported Platforms

- Hugging Face Spaces ✅
- Render
- Railway
- Docker
- Local Server

---

# 📷 System Screenshots



<img width="1358" height="598" alt="image" src="https://github.com/user-attachments/assets/a8d32c2d-ba8e-4821-aacb-35b0c8fa0f40" />


<img width="1348" height="588" alt="image" src="https://github.com/user-attachments/assets/ee4c27fb-46f2-474f-b79a-cf41f325671f" />


<img width="1600" height="766" alt="WhatsApp Image 2026-07-30 at 2 25 20 PM (3)" src="https://github.com/user-attachments/assets/95a3ef14-543a-4239-a138-88bdc9456f15" />


<img width="1600" height="801" alt="WhatsApp Image 2026-07-30 at 2 25 20 PM (4)" src="https://github.com/user-attachments/assets/eae865a3-acbd-4713-9dc6-60aa042ff098" />


<img width="1581" height="632" alt="WhatsApp Image 2026-07-30 at 2 25 20 PM (6)" src="https://github.com/user-attachments/assets/69e91372-7091-4583-9bc6-e77c3e59d5ad" />


<img width="1132" height="645" alt="WhatsApp Image 2026-07-30 at 2 25 20 PM (5)" src="https://github.com/user-attachments/assets/68085f02-ac51-4eb0-a86c-5cd137824d38" />


<img width="1113" height="643" alt="WhatsApp Image 2026-07-30 at 2 25 20 PM" src="https://github.com/user-attachments/assets/3c79f558-4960-4fad-adc4-dfadc8cb3e6e" />


<img width="1334" height="538" alt="image" src="https://github.com/user-attachments/assets/31276e53-d99e-4999-b1ba-bcb50ef24706" />



---

# 👨‍💻 Team Members

| Name | Role |
|------|------|
| Nomend Kumar Sahu | Team Lead |
| Yogesh Kumar Yadav | Backend Developer |
| Harsha Sahu | Frontend Developer |
| Dagendra Kumar Sahu | AI & IoT Developer |
| Jayant Verma | AI & IoT Developer |

---

# 🌐 Live Demo

### Hugging Face Spaces

https://huggingface.co/spaces/saveyagroup/PWMU-SYSTEM

---

# 📚 Documentation

The project documentation includes:

- Installation Guide
- User Manual
- API Documentation
- Database Schema
- System Architecture
- Deployment Guide

---

# 🔮 Future Enhancements

- Mobile Application Support
- Multi-Camera Integration
- AI Predictive Analytics
- GPS-Based Vehicle Tracking
- IoT Sensor Integration
- QR-Based Waste Tracking
- Voice Assistant Support
- Role-Based Access Control
- Email & SMS Notifications

---

# 📄 License

This project has been developed by **Team EchoByte** for academic research, innovation, and smart Plastic Waste Management Unit (PWMU) monitoring.

© 2026 Team EchoByte. All Rights Reserved.

---

## ⭐ Acknowledgements

- National Institute of Technology Raipur
- Government of Chhattisgarh
- UNICEF
- Ultralytics YOLO
- OpenCV
- EasyOCR
- Supabase
- Hugging Face
