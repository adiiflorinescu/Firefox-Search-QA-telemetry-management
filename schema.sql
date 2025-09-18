-- C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/schema.sql

-- Drop tables in reverse order of dependency to avoid foreign key errors.
DROP TABLE IF EXISTS coverage_to_metric_link;
DROP TABLE IF EXISTS planning;
DROP TABLE IF EXISTS coverage;
DROP TABLE IF EXISTS glean_metrics;
DROP TABLE IF EXISTS legacy_metrics;

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
    created_at DATETIME DEFAULT (datetime('now')),
    updated_at DATETIME DEFAULT (datetime('now'))
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
    created_at DATETIME DEFAULT (datetime('now')),
    updated_at DATETIME DEFAULT (datetime('now'))
);

-- Table for individual test cases
CREATE TABLE coverage (
    coverage_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tc_id TEXT NOT NULL UNIQUE,
    tcid_title TEXT,
    is_deleted BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT (datetime('now')),
    updated_at DATETIME DEFAULT (datetime('now'))
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
    created_at DATETIME DEFAULT (datetime('now')),
    updated_at DATETIME DEFAULT (datetime('now')),
    UNIQUE (metric_name, metric_type, tc_id, region, engine)
);

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