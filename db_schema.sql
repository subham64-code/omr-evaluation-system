CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    preferred_language TEXT DEFAULT 'en',
    created_at DATETIME
);

CREATE TABLE exams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    subject TEXT NOT NULL,
    total_questions INTEGER NOT NULL,
    negative_marking REAL NOT NULL DEFAULT 0,
    published BOOLEAN DEFAULT 0,
    created_by INTEGER NOT NULL,
    created_at DATETIME,
    FOREIGN KEY(created_by) REFERENCES users(id)
);

CREATE TABLE questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER NOT NULL,
    question_no INTEGER NOT NULL,
    question_text TEXT NOT NULL,
    options_json TEXT NOT NULL,
    topic TEXT,
    FOREIGN KEY(exam_id) REFERENCES exams(id)
);

CREATE TABLE answer_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER UNIQUE NOT NULL,
    key_json TEXT NOT NULL,
    updated_at DATETIME,
    FOREIGN KEY(exam_id) REFERENCES exams(id)
);

CREATE TABLE submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    response_json TEXT NOT NULL,
    time_taken_sec INTEGER DEFAULT 0,
    pattern_hash TEXT NOT NULL,
    created_at DATETIME,
    FOREIGN KEY(exam_id) REFERENCES exams(id),
    FOREIGN KEY(student_id) REFERENCES users(id)
);

CREATE TABLE results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    submission_id INTEGER NOT NULL,
    score REAL NOT NULL,
    correct_count INTEGER NOT NULL,
    wrong_count INTEGER NOT NULL,
    unattempted_count INTEGER NOT NULL,
    percentile REAL DEFAULT 0,
    rank INTEGER DEFAULT 0,
    accuracy REAL DEFAULT 0,
    status TEXT DEFAULT 'draft',
    confidence_avg REAL DEFAULT 0,
    anomalies_json TEXT DEFAULT '[]',
    feedback_text TEXT DEFAULT '',
    created_at DATETIME,
    FOREIGN KEY(exam_id) REFERENCES exams(id),
    FOREIGN KEY(student_id) REFERENCES users(id),
    FOREIGN KEY(submission_id) REFERENCES submissions(id)
);

CREATE TABLE detection_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id INTEGER NOT NULL,
    question_no INTEGER NOT NULL,
    predicted_option TEXT NOT NULL,
    confidence REAL NOT NULL,
    flagged BOOLEAN DEFAULT 0,
    FOREIGN KEY(result_id) REFERENCES results(id)
);
