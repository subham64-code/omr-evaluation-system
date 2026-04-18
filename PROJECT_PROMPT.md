# OMR Evaluation System Project Prompt

Build a full-stack, real-time, modern animated OMR (Optical Mark Recognition) Evaluation System with separate roles for Admin (Teacher) and Student.

The system must be production-ready, scalable, and include AI-based OMR detection, real-time result processing, and modern UI/UX animations.

## Core Objective
Create an intelligent OMR evaluation platform where:
- Teachers upload OMR sheets or conduct online exams
- System automatically detects answers using AI / Computer Vision
- Results are evaluated instantly
- Admin publishes results
- Students securely view results in real time

## Roles & Permissions

### Admin (Teacher)
- Secure login (JWT/OAuth)
- Dashboard with analytics
- Create exam (MCQ-based)
- Upload answer key
- Upload scanned OMR sheets (images/PDF)
- Real-time OMR processing using OpenCV or AI model
- Manual override for incorrect detections
- Auto-evaluation and scoring
- Publish/unpublish results
- Export results (PDF/Excel)
- View student performance analytics (graphs, rank, accuracy)

### Student
- Secure login/signup
- View available exams
- Attempt online OMR-style exam (bubble UI)
- OR upload scanned OMR sheet
- Real-time submission status
- View result after admin publishes
- Performance insights (accuracy, weak topics, time analysis)
- Animated score visualization

## Unique AI Logic
- Use OpenCV for bubble detection (contours + thresholding)
- Use ML model for noisy/blurred sheet correction
- Auto-alignment of tilted images
- Detect multiple marked answers and flag anomalies
- Confidence score for each detected answer
- AI-based cheating detection (duplicate patterns)
- Auto-correct partially filled bubbles
- Detect invalid responses
- Highlight doubtful answers for admin review

## Real-Time Features
- Use WebSockets (Socket.IO / Firebase)
- Live processing status: Uploading -> Processing -> Evaluating -> Completed
- Real-time leaderboard
- Instant result push to students after publishing

## Frontend
- React / Next.js
- Tailwind CSS
- Framer Motion
- Glassmorphism dashboard
- Animated progress bars during OMR processing
- Interactive OMR bubble sheet
- Smooth transitions between pages
- Dark/light mode
- Responsive design

## Backend
- Node.js (Express) or Django
- REST API + WebSockets
- Authentication (JWT)
- Modules:
  - User Management
  - Exam Management
  - OMR Processing Engine
  - Result Engine
  - Notification System

## Database
- MongoDB or PostgreSQL
- Users, Exams, Questions, Answer Keys, Student Responses, Results, Logs

## Result System
- Auto-score calculation
- Negative marking support
- Rank calculation
- Percentile system
- Pie chart, bar graph, downloadable report card

## Security
- Role-based access control
- Encrypted passwords
- Secure file upload
- Rate limiting
- Input sanitization

## Extra Modern Features
- AI voice assistant
- Smart recommendations
- Heatmap of mistakes
- Auto-generated feedback using AI
- Multi-language support
- Offline exam mode sync

## Deployment
- Dockerized application
- CI/CD pipeline
- Cloud deployment (AWS / Vercel / Render)
- CDN for fast image processing
