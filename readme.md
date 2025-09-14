# Telemetry Coverage Dashboard

A web application for managing and viewing telemetry metric coverage for test cases. This tool allows users to track which test cases cover specific Glean and Legacy metrics, view reports, and perform data management tasks through a clean web interface.

## Project Features

### 1. Data Management (`/`)
- **Centralized Data Input**: A single page for all data creation and bulk import tasks.
- **Coverage Management**:
  - Create single test case coverage entries, linking a TCID to one or more telemetry metrics.
  - Bulk upload coverage data from a CSV file.
- **Metric Management**:
  - Add individual Glean or Legacy metrics with their properties.
  - Bulk upload Glean or Legacy metric definitions from a CSV file.
- **Probe Extraction Tool**:
  - Upload a CSV of test cases (`extract_data.csv`).
  - The tool parses the 'Steps' and 'Steps (Expected Result)' columns to find and extract telemetry probes (`browser.*`, `urlbar.*`, `contextservices.*`).
  - Returns a new downloadable CSV with a "Found Probes" column appended.
- **Hidden by Default**: The Data Management tab is hidden to provide a cleaner view for most users. It can be toggled with the `Ctrl+Shift+Z` keyboard shortcut.

### 2. View Metrics (`/metrics`)
- **Three Collapsible Tables**:
  - **Test Case Coverage**: Lists all TCIDs, their titles (on hover), and all associated metrics.
  - **Glean Metrics**: A detailed list of all defined Glean metrics.
  - **Legacy Metrics**: A detailed list of all defined Legacy metrics.
- **Global Search**: A real-time search bar to filter all three tables by TCID or metric name.
- **Soft Delete**: Ability to mark any entry as "deleted" without removing it from the database. This is activated with the `Ctrl+Shift+D` keyboard shortcut.

### 3. Metric Reports (`/reports`)
- **General Breakdown**: High-level statistics cards showing:
  - Total Glean Metrics
  - Total TCIDs covering Glean Metrics
  - Total Legacy Metrics
  - Total TCIDs covering Legacy Metrics
- **Metric Coverage Details Table**:
  - A unified list of all Glean and Legacy metrics.
  - A badge (`G`/`L`) to differentiate metric types.
  - A count of how many TCIDs cover each metric.
  - A collapsible "Show Details" section listing all associated TCIDs for each metric.
- **Filtered Search**: A global search bar combined with a dropdown to filter the report by "All", "Glean", or "Legacy" metric types.

## Technical Specifications

- **Backend**: Python 3 with Flask
- **Frontend**: HTML5, CSS3, vanilla JavaScript
- **Database**: SQLite 3
- **WSGI Server (Production)**: Gunicorn

## Local Setup and Installation

1.  **Clone the Repository**:
    