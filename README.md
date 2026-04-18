# OMR Evaluation System

Full-stack, real-time OMR (Optical Mark Recognition) Evaluation System with role-based access for Admin (Teacher) and Student.

## Tech Stack
- Backend: Flask, Flask-SocketIO, Flask-JWT-Extended, SQLAlchemy
- OMR Engine: OpenCV + confidence and anomaly scoring
- Frontend: Modern animated SPA in HTML/CSS/JS with Chart.js and Socket.IO
- Database: SQLite (easy local setup; can move to PostgreSQL)

## Core Features Implemented
- JWT-based authentication with role-based authorization
- Admin dashboard:
  - Create exams
  - Save answer key
  - Upload scanned OMR sheets
  - Real-time pipeline status (Uploading -> Processing -> Evaluating -> Completed)
  - Publish/unpublish results
  - Analytics and CSV export
- Student dashboard:
  - Signup/login
  - View available exams
  - Attempt online bubble exam
  - Upload OMR sheet
  - View real-time status and results
  - Performance chart
- OMR AI logic:
  - Image thresholding and deskewing
  - Bubble-fill confidence score
  - Invalid/multiple mark anomaly flags
  - Partial fill auto-correction heuristic
  - Duplicate-pattern anomaly check

## Demo Credentials
- Admin: admin@omr.local / admin123
- Student: student@omr.local / student123

## Run Locally
1. Create and activate virtual environment.
2. Install dependencies:
   - pip install -r requirements.txt
3. Start server:
   - python app.py
4. Open browser:
   - http://127.0.0.1:5000

## API Summary
- POST /api/auth/signup
- POST /api/auth/login
- GET /api/profile
- POST /api/exams
- GET /api/exams
- POST /api/exams/<exam_id>/questions
- GET /api/exams/<exam_id>/questions
- POST /api/exams/<exam_id>/answer-key
- POST /api/exams/<exam_id>/publish
- POST /api/exams/<exam_id>/submit-online
- POST /api/exams/<exam_id>/upload-omr
- PUT /api/results/<result_id>/override
- GET /api/results/me
- GET /api/admin/analytics
- GET /api/admin/results/export

## Real-Time Events (Socket.IO)
- processing_status
- result_published
- result_updated

## Database Schema
See db_schema.sql for full schema.

## Deployment
- Dockerfile and docker-compose.yml included
- CI pipeline: .github/workflows/ci.yml
- For cloud deployment:
  - Render: create Web Service, set start command python app.py, set `SECRET_KEY`, `JWT_SECRET_KEY`, and `DATABASE_URL` or `OMR_SQLITE_PATH`
  - AWS Elastic Beanstalk: deploy as Docker platform or Python platform
  - Vercel: frontend can be separated if migrated to React/Next.js

## Notes
- SQLite is used for quick setup. For production scale, migrate to PostgreSQL.
- OMR detection currently assumes a structured bubble layout. For institution-specific sheets, calibrate coordinates/model per template.
- When running in Docker locally, the database is persisted in `./data/omr_eval.db`.
- Render free web services use an ephemeral filesystem, so SQLite data will not persist across redeploys; for persistence, switch `DATABASE_URL` to Render Postgres.
