# Telemetry Coverage Dashboard

A web application for managing and viewing telemetry metric coverage for test cases. This tool allows users to track which test cases cover specific Glean and Legacy metrics, view reports, plan future test coverage, and perform data management tasks through a clean web interface.

## Project Features

### 1. Data Management (`/manage`)
- **Centralized Data Input**: A single page for all data creation and bulk import tasks.
- **Coverage Management**:
  - Create single test case coverage entries, linking a TCID to one or more telemetry metrics with optional `Region` and `Engine` context.
  - Bulk upload coverage data from a CSV file.
- **Metric Management**:
  - Add individual Glean or Legacy metrics with their properties.
  - Bulk upload Glean or Legacy metric definitions from a CSV file.
- **Probe Extraction Tool**:
  - Upload a CSV of test cases (e.g., from TestRail).
  - The tool parses the 'Title', 'Steps', and 'Steps (Expected Result)' columns to find and extract telemetry probes, regions, and search engines.
  - Returns a new downloadable CSV with "Found Probes", "Found Region", and "Found Engine" columns appended.
- **Hidden by Default**: The Data Management tab is hidden to provide a cleaner view for most users. It can be toggled with the `Ctrl+Shift+Z` keyboard shortcut.

### 2. View Metrics (`/metrics`)
- **Three Collapsible Tables**:
  - **Test Case Coverage**: Lists all metrics that have test coverage. Rows are expandable to show a detailed breakdown of covering TCIDs by region and engine.
  - **Glean Metrics**: A detailed list of all defined Glean metrics.
  - **Legacy Metrics**: A detailed list of all defined Legacy metrics.
- **Global Search**: A real-time search bar to filter all three tables by metric name, TCID, region, or engine.
- **Soft Delete**: Ability to mark any Glean or Legacy metric as "deleted" without removing it from the database. This is activated with the `Ctrl+Shift+D` keyboard shortcut.

### 3. Metric Reports (`/reports`)
- **General Breakdown**: High-level statistics cards showing:
  - Total Glean & Legacy Metrics
  - Total Tests Covering Glean & Legacy Metrics
- **Metric Coverage Details Table**:
  - A unified list of all Glean and Legacy metrics.
  - A badge (`G`/`L`) to differentiate metric types.
  - A count of how many TCIDs cover each metric.
  - A collapsible "Show TCIDs" section listing all associated test cases for each metric, along with their region/engine context.
- **Filtered Search**: A global search bar combined with a dropdown to filter the report by "All", "Glean", or "Legacy" metric types.

### 4. Coverage Planning (`/planning`)
- **Unified Planning Grid**: A central view of all metrics (Glean and Legacy) showing existing coverage counts (TCIDs, Regions, Engines).
- **Priority Management**: Set a priority (P1-P5) for each metric directly from the grid. Changes are saved instantly.
- **Plan Future Coverage**:
  - Add "planned" entries for a metric with a specific region or engine.
  - Promote a planned entry to full coverage by adding a TCID.
- **Interactive Filtering**: Filter the entire planning grid by metric name, priority, or whether a metric has planned entries.

## Project Architecture

The application follows a modular and scalable structure, separating concerns into distinct packages.


## Technical Specifications

- **Backend**: Python 3 with Flask
- **Frontend**: HTML5, CSS3, vanilla JavaScript
- **Database**: SQLite 3
- **WSGI Server (Production)**: Gunicorn

## Local Setup and Installation

Follow these steps to get the application running on your local machine.

### 1. Prerequisites
- Python 3.8 or newer
- `pip` (Python package installer)

### 2. Clone the Repository
Open your terminal, navigate to your desired directory, and clone the project repository.

### 3. Create and Activate a Virtual Environment
It is highly recommended to use a virtual environment to manage project dependencies. From the `pythonProject` directory:

**On Windows:**


### 4. Install Dependencies
Install all the required Python packages using the `requirements.txt` file.


### 5. Set Up the Database
Run the setup script from the `pythonProject` directory to create a fresh SQLite database in the `instance` folder with the correct schema and triggers.


This will create an `instance/metrics.db` file. If the file already exists, it will prompt you before overwriting.

### 6. Configure Environment Variables
The application uses a `.env` file for configuration. Create a file named `.env` in the `pythonProject` directory and add a secret key.

You can also customize the `TC_BASE_URL` in `config.py` to point to your test case management system.

### 7. Run the Application
Start the Flask development server by running `run.py`.

The application will be available at `http://127.0.0.1:5000`.
