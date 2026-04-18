import csv
import io
import json
import os
from datetime import datetime, timedelta, timezone
from functools import wraps
from uuid import uuid4

import cv2
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)
from flask_socketio import SocketIO, emit, join_room
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

from omr_engine import evaluate_submission, process_omr_image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
RESULT_DIR = os.path.join(BASE_DIR, "results")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__, static_url_path="", static_folder=BASE_DIR)
database_url = os.getenv("DATABASE_URL")
if not database_url:
    sqlite_path = os.getenv("OMR_SQLITE_PATH", os.path.join(DATA_DIR, "omr_eval.db"))
    database_url = f"sqlite:///{sqlite_path}"

secret_key = os.getenv("SECRET_KEY") or os.getenv("JWT_SECRET_KEY") or "omr-evaluation-system-dev-secret-key-change-me"

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = secret_key
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", secret_key)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

CORS(app)
db = SQLAlchemy(app)
jwt = JWTManager(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")
    preferred_language = db.Column(db.String(20), nullable=False, default="en")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Exam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(120), nullable=False)
    total_questions = db.Column(db.Integer, nullable=False, default=20)
    negative_marking = db.Column(db.Float, nullable=False, default=0.0)
    published = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exam.id"), nullable=False)
    question_no = db.Column(db.Integer, nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    options_json = db.Column(db.Text, nullable=False)
    topic = db.Column(db.String(80), nullable=False, default="General")


class AnswerKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exam.id"), unique=True, nullable=False)
    key_json = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exam.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    source = db.Column(db.String(30), nullable=False, default="online")
    response_json = db.Column(db.Text, nullable=False)
    time_taken_sec = db.Column(db.Integer, default=0)
    pattern_hash = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Result(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exam.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    submission_id = db.Column(db.Integer, db.ForeignKey("submission.id"), nullable=False)
    score = db.Column(db.Float, nullable=False)
    correct_count = db.Column(db.Integer, nullable=False)
    wrong_count = db.Column(db.Integer, nullable=False)
    unattempted_count = db.Column(db.Integer, nullable=False)
    percentile = db.Column(db.Float, default=0.0)
    rank = db.Column(db.Integer, default=0)
    accuracy = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), nullable=False, default="draft")
    confidence_avg = db.Column(db.Float, default=0.0)
    anomalies_json = db.Column(db.Text, default="[]")
    feedback_text = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DetectionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    result_id = db.Column(db.Integer, db.ForeignKey("result.id"), nullable=False)
    question_no = db.Column(db.Integer, nullable=False)
    predicted_option = db.Column(db.String(2), nullable=False)
    confidence = db.Column(db.Float, nullable=False)
    flagged = db.Column(db.Boolean, default=False)


def role_required(*roles):
    def decorator(func):
        @wraps(func)
        @jwt_required()
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            role = claims.get("role")
            if role not in roles:
                return jsonify({"error": "Access denied"}), 403
            return func(*args, **kwargs)

        return wrapper

    return decorator


def parse_json_body():
    data = request.get_json(silent=True)
    if not data:
        return None, (jsonify({"error": "Invalid JSON body"}), 400)
    return data, None


def student_room(student_id):
    return f"student_{student_id}"


def exam_room(exam_id):
    return f"exam_{exam_id}"


def emit_processing(exam_id, student_id, stage, extra=None):
    payload = {
        "stage": stage,
        "exam_id": exam_id,
        "student_id": student_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        payload.update(extra)
    socketio.emit("processing_status", payload, to=student_room(student_id))
    socketio.emit("processing_status", payload, to=exam_room(exam_id))


def generate_pattern_hash(response_map):
    return "|".join(str(response_map.get(str(i), "-")) for i in sorted(map(int, response_map.keys())))


def build_feedback(accuracy, weak_topics):
    if accuracy >= 90:
        tone = "Excellent performance. Keep your revision momentum strong."
    elif accuracy >= 75:
        tone = "Strong performance. Focus on precision in medium-difficulty questions."
    elif accuracy >= 50:
        tone = "Average performance. Improve topic-wise consistency and speed."
    else:
        tone = "Needs improvement. Build fundamentals with short timed practice sets."

    if weak_topics:
        return f"{tone} Priority topics: {', '.join(weak_topics[:3])}."
    return tone


def recalculate_rank_and_percentile(exam_id):
    results = Result.query.filter_by(exam_id=exam_id).order_by(Result.score.desc()).all()
    total = len(results)
    if total == 0:
        return

    for index, row in enumerate(results, start=1):
        row.rank = index
        row.percentile = round(((total - index) / max(total - 1, 1)) * 100.0, 2)
    db.session.commit()


def evaluate_and_store(exam, student, response_map, source, time_taken_sec, confidence_map=None, anomalies=None):
    answer_key_row = AnswerKey.query.filter_by(exam_id=exam.id).first()
    if not answer_key_row:
        raise ValueError("Answer key not configured for this exam")

    key_map = json.loads(answer_key_row.key_json)
    stats = evaluate_submission(
        answer_key=key_map,
        student_response=response_map,
        negative_marking=exam.negative_marking,
        confidence_map=confidence_map or {},
    )

    submission = Submission(
        exam_id=exam.id,
        student_id=student.id,
        source=source,
        response_json=json.dumps(response_map),
        time_taken_sec=time_taken_sec,
        pattern_hash=generate_pattern_hash(response_map),
    )
    db.session.add(submission)
    db.session.flush()

    topic_scores = {}
    question_rows = Question.query.filter_by(exam_id=exam.id).all()
    topic_by_question = {q.question_no: q.topic for q in question_rows}
    for q_num, value in stats["breakdown"].items():
        topic = topic_by_question.get(int(q_num), "General")
        topic_scores.setdefault(topic, {"correct": 0, "total": 0})
        topic_scores[topic]["total"] += 1
        if value["is_correct"]:
            topic_scores[topic]["correct"] += 1

    weak_topics = []
    for topic, topic_stat in topic_scores.items():
        if topic_stat["total"] == 0:
            continue
        topic_accuracy = (topic_stat["correct"] / topic_stat["total"]) * 100
        if topic_accuracy < 60:
            weak_topics.append(topic)

    feedback = build_feedback(stats["accuracy"], weak_topics)

    result = Result(
        exam_id=exam.id,
        student_id=student.id,
        submission_id=submission.id,
        score=stats["score"],
        correct_count=stats["correct"],
        wrong_count=stats["wrong"],
        unattempted_count=stats["unattempted"],
        accuracy=stats["accuracy"],
        confidence_avg=stats["confidence_avg"],
        anomalies_json=json.dumps(anomalies or []),
        feedback_text=feedback,
    )
    db.session.add(result)
    db.session.flush()

    for q_num, confidence in stats["confidence_by_question"].items():
        entry = stats["breakdown"][str(q_num)]
        db.session.add(
            DetectionLog(
                result_id=result.id,
                question_no=int(q_num),
                predicted_option=entry["marked"],
                confidence=float(confidence),
                flagged=float(confidence) < 0.6,
            )
        )

    duplicate_count = (
        Submission.query.filter_by(exam_id=exam.id, pattern_hash=submission.pattern_hash)
        .count()
    )
    if duplicate_count >= 3:
        anomalies = json.loads(result.anomalies_json)
        anomalies.append("Potential duplicate response pattern detected")
        result.anomalies_json = json.dumps(anomalies)

    db.session.commit()
    recalculate_rank_and_percentile(exam.id)
    db.session.refresh(result)
    return result


def result_to_dict(result):
    return {
        "result_id": result.id,
        "exam_id": result.exam_id,
        "student_id": result.student_id,
        "score": result.score,
        "correct": result.correct_count,
        "wrong": result.wrong_count,
        "unattempted": result.unattempted_count,
        "accuracy": result.accuracy,
        "rank": result.rank,
        "percentile": result.percentile,
        "status": result.status,
        "confidence_avg": result.confidence_avg,
        "anomalies": json.loads(result.anomalies_json or "[]"),
        "feedback": result.feedback_text,
        "created_at": result.created_at.isoformat(),
    }


@app.get("/")
def index_page():
    return app.send_static_file("index.html")


@app.post("/api/auth/signup")
def signup():
    data, error = parse_json_body()
    if error:
        return error

    full_name = data.get("full_name", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    role = data.get("role", "student")

    if role not in {"student", "admin"}:
        return jsonify({"error": "Invalid role"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    if not full_name or not email:
        return jsonify({"error": "Full name and email are required"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already exists"}), 409

    user = User(
        full_name=full_name,
        email=email,
        password_hash=generate_password_hash(password),
        role=role,
        preferred_language=data.get("preferred_language", "en"),
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "User created successfully"}), 201


@app.post("/api/auth/login")
def login():
    data, error = parse_json_body()
    if error:
        return error

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid credentials"}), 401

    token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.role, "name": user.full_name, "email": user.email},
        expires_delta=timedelta(hours=12),
    )
    return jsonify({"access_token": token, "role": user.role, "name": user.full_name})


@app.get("/api/profile")
@jwt_required()
def get_profile():
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)
    return jsonify(
        {
            "id": user.id,
            "name": user.full_name,
            "email": user.email,
            "role": user.role,
            "preferred_language": user.preferred_language,
        }
    )


@app.post("/api/exams")
@role_required("admin")
def create_exam():
    user_id = int(get_jwt_identity())
    data, error = parse_json_body()
    if error:
        return error

    exam = Exam(
        title=data.get("title", "").strip(),
        subject=data.get("subject", "General"),
        total_questions=int(data.get("total_questions", 20)),
        negative_marking=float(data.get("negative_marking", 0.0)),
        created_by=user_id,
    )
    if not exam.title:
        return jsonify({"error": "Exam title is required"}), 400

    db.session.add(exam)
    db.session.commit()
    return jsonify({"message": "Exam created", "exam_id": exam.id})


@app.get("/api/exams")
@jwt_required(optional=True)
def list_exams():
    only_published = request.args.get("available") == "1"
    query = Exam.query
    if only_published:
        query = query.filter_by(published=True)

    exams = query.order_by(Exam.created_at.desc()).all()
    payload = []
    for exam in exams:
        payload.append(
            {
                "id": exam.id,
                "title": exam.title,
                "subject": exam.subject,
                "total_questions": exam.total_questions,
                "negative_marking": exam.negative_marking,
                "published": exam.published,
            }
        )
    return jsonify(payload)


@app.post("/api/exams/<int:exam_id>/questions")
@role_required("admin")
def create_questions(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    data, error = parse_json_body()
    if error:
        return error

    questions = data.get("questions", [])
    if not isinstance(questions, list) or not questions:
        return jsonify({"error": "questions list is required"}), 400

    Question.query.filter_by(exam_id=exam.id).delete()
    for q in questions:
        db.session.add(
            Question(
                exam_id=exam.id,
                question_no=int(q["question_no"]),
                question_text=q.get("question_text", "Question"),
                options_json=json.dumps(q.get("options", ["A", "B", "C", "D"])),
                topic=q.get("topic", "General"),
            )
        )
    db.session.commit()
    return jsonify({"message": "Questions saved"})


@app.get("/api/exams/<int:exam_id>/questions")
@jwt_required()
def list_questions(exam_id):
    rows = Question.query.filter_by(exam_id=exam_id).order_by(Question.question_no.asc()).all()
    return jsonify(
        [
            {
                "question_no": q.question_no,
                "question_text": q.question_text,
                "options": json.loads(q.options_json),
                "topic": q.topic,
            }
            for q in rows
        ]
    )


@app.post("/api/exams/<int:exam_id>/answer-key")
@role_required("admin")
def set_answer_key(exam_id):
    Exam.query.get_or_404(exam_id)
    data, error = parse_json_body()
    if error:
        return error

    key_map = data.get("answer_key", {})
    if not key_map:
        return jsonify({"error": "answer_key is required"}), 400

    key_row = AnswerKey.query.filter_by(exam_id=exam_id).first()
    if not key_row:
        key_row = AnswerKey(exam_id=exam_id, key_json=json.dumps(key_map))
        db.session.add(key_row)
    else:
        key_row.key_json = json.dumps(key_map)
    db.session.commit()
    return jsonify({"message": "Answer key saved"})


@app.post("/api/exams/<int:exam_id>/publish")
@role_required("admin")
def publish_result(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    data, error = parse_json_body()
    if error:
        return error

    exam.published = bool(data.get("published", True))
    db.session.commit()

    if exam.published:
        results = Result.query.filter_by(exam_id=exam.id).all()
        for result in results:
            result.status = "published"
        db.session.commit()
        socketio.emit(
            "result_published",
            {"exam_id": exam.id, "message": "Your result is published"},
            to=exam_room(exam.id),
        )

    return jsonify({"message": "Publish status updated", "published": exam.published})


@app.post("/api/exams/<int:exam_id>/submit-online")
@role_required("student")
def submit_online(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    data, error = parse_json_body()
    if error:
        return error

    student = User.query.get_or_404(int(get_jwt_identity()))
    response_map = data.get("responses", {})
    time_taken_sec = int(data.get("time_taken_sec", 0))

    if not isinstance(response_map, dict):
        return jsonify({"error": "responses must be an object"}), 400

    result = evaluate_and_store(exam, student, response_map, "online", time_taken_sec)
    emit_processing(exam.id, student.id, "Completed", {"result": result_to_dict(result)})
    return jsonify({"message": "Submitted", "result": result_to_dict(result)})


@app.post("/api/exams/<int:exam_id>/upload-omr")
@jwt_required()
def upload_omr(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    user = User.query.get_or_404(int(get_jwt_identity()))

    if "file" not in request.files:
        return jsonify({"error": "OMR file is required"}), 400

    file = request.files["file"]
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in {".png", ".jpg", ".jpeg"}:
        return jsonify({"error": "Only PNG/JPG/JPEG files are allowed"}), 400

    file_name = f"{uuid4()}{ext}"
    file_path = os.path.join(UPLOAD_DIR, file_name)
    file.save(file_path)

    student = user
    if user.role == "admin" and request.form.get("student_id"):
        student = User.query.filter_by(id=int(request.form["student_id"]), role="student").first() or student

    emit_processing(exam.id, student.id, "Uploading")
    emit_processing(exam.id, student.id, "Processing")

    detection = process_omr_image(
        image_path=file_path,
        total_questions=exam.total_questions,
        options_per_question=4,
    )

    emit_processing(exam.id, student.id, "Evaluating")
    result = evaluate_and_store(
        exam,
        student,
        detection["responses"],
        source="omr_upload",
        time_taken_sec=0,
        confidence_map=detection["confidence"],
        anomalies=detection["anomalies"],
    )

    emit_processing(exam.id, student.id, "Completed", {"result": result_to_dict(result)})
    return jsonify(
        {
            "message": "OMR processed successfully",
            "detection": {
                "responses": detection["responses"],
                "anomalies": detection["anomalies"],
                "average_confidence": detection["average_confidence"],
            },
            "result": result_to_dict(result),
        }
    )


@app.put("/api/results/<int:result_id>/override")
@role_required("admin")
def override_result(result_id):
    result = Result.query.get_or_404(result_id)
    exam = Exam.query.get_or_404(result.exam_id)
    student = User.query.get_or_404(result.student_id)

    data, error = parse_json_body()
    if error:
        return error

    overrides = data.get("responses", {})
    submission = Submission.query.get_or_404(result.submission_id)
    response_map = json.loads(submission.response_json)
    response_map.update(overrides)
    submission.response_json = json.dumps(response_map)

    answer_key = json.loads(AnswerKey.query.filter_by(exam_id=exam.id).first().key_json)
    stats = evaluate_submission(answer_key, response_map, exam.negative_marking)

    result.score = stats["score"]
    result.correct_count = stats["correct"]
    result.wrong_count = stats["wrong"]
    result.unattempted_count = stats["unattempted"]
    result.accuracy = stats["accuracy"]
    result.feedback_text = build_feedback(result.accuracy, [])
    db.session.commit()

    recalculate_rank_and_percentile(exam.id)
    socketio.emit("result_updated", {"result": result_to_dict(result)}, to=student_room(student.id))
    return jsonify({"message": "Manual override applied", "result": result_to_dict(result)})


@app.get("/api/results/me")
@role_required("student")
def my_results():
    student_id = int(get_jwt_identity())
    rows = Result.query.filter_by(student_id=student_id).order_by(Result.created_at.desc()).all()
    return jsonify([result_to_dict(r) for r in rows])


@app.get("/api/admin/analytics")
@role_required("admin")
def admin_analytics():
    exam_id = request.args.get("exam_id", type=int)
    query = Result.query
    if exam_id:
        query = query.filter_by(exam_id=exam_id)

    results = query.all()
    count = len(results)
    if count == 0:
        return jsonify({"summary": {"students": 0, "avg_score": 0, "avg_accuracy": 0}, "top_results": []})

    avg_score = round(sum(r.score for r in results) / count, 2)
    avg_accuracy = round(sum(r.accuracy for r in results) / count, 2)
    top_results = sorted(results, key=lambda r: r.score, reverse=True)[:10]

    return jsonify(
        {
            "summary": {
                "students": count,
                "avg_score": avg_score,
                "avg_accuracy": avg_accuracy,
            },
            "top_results": [result_to_dict(r) for r in top_results],
        }
    )


@app.get("/api/admin/results/export")
@role_required("admin")
def export_results():
    exam_id = request.args.get("exam_id", type=int)
    rows = Result.query.filter_by(exam_id=exam_id).all() if exam_id else Result.query.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Result ID", "Exam ID", "Student ID", "Score", "Rank", "Percentile", "Accuracy", "Status"])
    for row in rows:
        writer.writerow([row.id, row.exam_id, row.student_id, row.score, row.rank, row.percentile, row.accuracy, row.status])

    file_name = f"results_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    memory_file = io.BytesIO(output.getvalue().encode("utf-8"))
    memory_file.seek(0)
    return send_file(memory_file, mimetype="text/csv", as_attachment=True, download_name=file_name)


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now(timezone.utc).isoformat()})


@socketio.on("connect")
def on_connect():
    emit("connected", {"message": "Socket connected"})


@socketio.on("join")
def on_join(data):
    token = (data or {}).get("token")
    if not token:
        return

    from flask_jwt_extended import decode_token

    try:
        decoded = decode_token(token)
        identity = decoded["sub"]
        join_room(student_room(identity))

        exam_id = (data or {}).get("exam_id")
        if exam_id:
            join_room(exam_room(int(exam_id)))

        emit("joined", {"room": student_room(identity)})
    except Exception:
        emit("error", {"message": "Unable to join socket room"})


def seed_data():
    if User.query.filter_by(email="admin@omr.local").first() is None:
        admin = User(
            full_name="Teacher Admin",
            email="admin@omr.local",
            password_hash=generate_password_hash("admin123"),
            role="admin",
        )
        db.session.add(admin)

    if User.query.filter_by(email="student@omr.local").first() is None:
        student = User(
            full_name="Demo Student",
            email="student@omr.local",
            password_hash=generate_password_hash("student123"),
            role="student",
        )
        db.session.add(student)

    db.session.commit()


with app.app_context():
    db.create_all()
    seed_data()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    allow_unsafe_werkzeug = os.getenv("ALLOW_UNSAFE_WERKZEUG", "1") == "1"
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=debug_mode,
        allow_unsafe_werkzeug=allow_unsafe_werkzeug,
    )
