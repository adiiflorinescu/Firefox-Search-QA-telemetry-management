-- C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/schema.sql

-- Drop tables in reverse order of dependency to avoid foreign key errors.
DROP TABLE IF EXISTS edit_history;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS coverage_to_metric_link;
DROP TABLE IF EXISTS planning;
DROP TABLE IF EXISTS coverage;
DROP TABLE IF EXISTS glean_metrics;
DROP TABLE IF EXISTS legacy_metrics;
DROP TABLE IF EXISTS supported_engines;

-- NEW: Table for user accounts and roles
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    -- Refinement: 'editor' matches the UI, 'planning' was a mismatch.
    role TEXT NOT NULL CHECK(role IN ('admin', 'editor', 'readonly')),
    -- Use TIMESTAMP so sqlite3 auto-converts it to a datetime object.
    created_at TIMESTAMP DEFAULT (datetime('now'))
);

-- NEW: Table for logging all data modifications
CREATE TABLE edit_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    timestamp TIMESTAMP DEFAULT (datetime('now')),
    action TEXT NOT NULL, -- e.g., 'add_coverage', 'set_priority'
    table_name TEXT,
    record_pk TEXT, -- The primary key of the affected record
    details TEXT, -- A description of the change, e.g., "Set priority to P1"
    FOREIGN KEY (user_id) REFERENCES users (user_id)
);

-- Table for Glean metrics definitions
CREATE TABLE glean_metrics (
    glean_name TEXT PRIMARY KEY,
    metric_type TEXT,
    expiration TEXT,
    description TEXT,
    search_metric BOOLEAN,
    legacy_correspondent TEXT,
    priority TEXT,
    notes TEXT,
    is_deleted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT (datetime('now')),
    updated_at TIMESTAMP DEFAULT (datetime('now'))
);

-- Table for Legacy metrics definitions
CREATE TABLE legacy_metrics (
    legacy_name TEXT PRIMARY KEY,
    metric_type TEXT,
    expiration TEXT,
    description TEXT,
    search_metric BOOLEAN,
    glean_correspondent TEXT,
    priority TEXT,
    notes TEXT,
    is_deleted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT (datetime('now')),
    updated_at TIMESTAMP DEFAULT (datetime('now'))
);

-- Table for individual test cases
CREATE TABLE coverage (
    coverage_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tc_id TEXT NOT NULL UNIQUE,
    tcid_title TEXT,
    is_deleted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT (datetime('now')),
    updated_at TIMESTAMP DEFAULT (datetime('now'))
);

-- Link table to associate test cases with metrics
CREATE TABLE coverage_to_metric_link (
    link_id INTEGER PRIMARY KEY AUTOINCREMENT,
    coverage_id INTEGER NOT NULL,
    metric_name TEXT NOT NULL,
    metric_type TEXT NOT NULL, -- 'glean' or 'legacy'
    region TEXT,
    engine TEXT,
    is_deleted BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (coverage_id) REFERENCES coverage (coverage_id) ON DELETE CASCADE,
    UNIQUE (coverage_id, metric_name, metric_type, region, engine)
);

-- Table for planned, un-promoted coverage entries
CREATE TABLE planning (
    planning_id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name TEXT NOT NULL,
    metric_type TEXT NOT NULL, -- 'glean' or 'legacy'
    tc_id TEXT, -- This will be null for planned entries
    region TEXT,
    engine TEXT,
    is_deleted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT (datetime('now')),
    updated_at TIMESTAMP DEFAULT (datetime('now')),
    UNIQUE (metric_name, metric_type, tc_id, region, engine)
);

-- Table for supported search engines for extraction
CREATE TABLE supported_engines (
    name TEXT PRIMARY KEY NOT NULL
);

-- Table for exception TCs

CREATE TABLE exceptions (
    exception_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tc_id TEXT NOT NULL UNIQUE,
    title TEXT,
    metrics TEXT,
    user_id INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES users (user_id)
);

-- Pre-populate with default engines
INSERT INTO supported_engines (name) VALUES ('google'), ('bing'), ('duckduckgo'), ('yahoo'), ('ecosia'), ('qwant');

-- Pre-populate with default admin user
-- Password is 'aflorinescu@mozilla.com'
INSERT INTO users (username, email, password_hash, role) VALUES
('aflorinescu', 'aflorinescu@mozilla.com', 'scrypt:32768:8:1$dT8ObNeWdzQebexM$571dbd27cc8784e4af7a4259d4d24a701107350293b64abe186d9041eb6440b014d95cce2f24771ea512283324ac3be54d1398430d22ac376dcb6527ef1f87e1', 'admin');


-- Triggers to auto-update the 'updated_at' column
CREATE TRIGGER update_glean_metrics_updated_at
AFTER UPDATE ON glean_metrics FOR EACH ROW
BEGIN
    UPDATE glean_metrics SET updated_at = datetime('now') WHERE glean_name = OLD.glean_name;
END;

CREATE TRIGGER update_legacy_metrics_updated_at
AFTER UPDATE ON legacy_metrics FOR EACH ROW
BEGIN
    UPDATE legacy_metrics SET updated_at = datetime('now') WHERE legacy_name = OLD.legacy_name;
END;

CREATE TRIGGER update_coverage_updated_at
AFTER UPDATE ON coverage FOR EACH ROW
BEGIN
    UPDATE coverage SET updated_at = datetime('now') WHERE coverage_id = OLD.coverage_id;
END;

CREATE TRIGGER update_planning_updated_at
AFTER UPDATE ON planning FOR EACH ROW
BEGIN
    UPDATE planning SET updated_at = datetime('now') WHERE planning_id = OLD.planning_id;
END;

-- At the end of migrations/v1.sql
PRAGMA user_version = 1;
    
