# Telemetry Coverage Dashboard

A comprehensive web application for managing and viewing telemetry metric coverage for test cases. This tool allows users to track which test cases cover specific Glean and Legacy metrics, view reports, plan future test coverage, and perform robust data management tasks through a clean, role-based web interface.

## Core Features

### 1. Data Management (`/manage`)
- **Centralized Data Input**: A single, admin-only page for all data creation and bulk import tasks.
- **Coverage Management**:
  - Create single test case coverage entries, linking a TCID to one or more telemetry metrics with optional `Region` and `Engine` context.
  - Bulk upload coverage data from a CSV file, which respects the exception list.
- **Metric Management**:
  - Add individual Glean or Legacy metrics with their properties.
  - Bulk upload Glean or Legacy metric definitions from a CSV file.
- **Exception Management**:
  - Add specific TCIDs to a global exception list to exclude them from all imports and data views.
  - View and soft-delete existing exceptions.
- **Data Extraction Tools**:
  - **Probe Extraction**: Upload a test case CSV (e.g., from TestRail) and download an enriched version with "Found Probes", "Found Region", and "Found Engine" columns appended. Empty values are populated with "N/A".
  - **Rotation Extraction**: Upload a specialized CSV (`tcsid`, `title`, `rotation`) and download an enriched version with "Found Region", "Found Engine", "Found Metric Type", and "Found Metrics" columns appended. Empty values are populated with "N/A".
- **Engine Management**: Add or delete supported search engines used for data extraction.

### 2. View Metrics (`/metrics`)
- **Three Collapsible Tables**:
  - **Test Case Coverage**: Lists all metrics that have test coverage. Rows are expandable to show a detailed breakdown of covering TCIDs by region and engine.
  - **Glean Metrics**: A detailed list of all defined Glean metrics.
  - **Legacy Metrics**: A detailed list of all defined Legacy metrics.
- **Global Search**: A real-time search bar to filter all three tables by metric name, TCID, region, or engine.
- **Soft Delete**: Admins can mark any Glean or Legacy metric as "deleted" without removing it from the database.

### 3. Metric Reports (`/reports`)
- **General Breakdown**: High-level statistics cards showing total metrics and coverage counts, excluding excepted TCIDs.
- **Metric Coverage Details Table**:
  - A unified list of all Glean and Legacy metrics with differentiating badges.
  - A count of how many TCIDs cover each metric.
- **Filtered Search**: A global search bar combined with a dropdown to filter the report by "All", "Glean", or "Legacy" metric types.

### 4. Coverage Planning (`/planning`)
- **Unified Planning Grid**: A central view of all metrics showing existing coverage counts (TCIDs, Regions, Engines), excluding excepted TCIDs.
- **Role-Based Interaction**:
  - Admins and Editors can set metric priorities, add notes, and manage planned entries.
  - Read-only users can view all data but cannot make changes.
- **Plan Future Coverage**:
  - Add "planned" entries for a metric with a specific region or engine.
  - Promote a planned entry to full coverage by adding a TCID.

### 5. Metric Status Page (`/<metric_type>/<metric_name>/status`)
- **Publicly Shareable**: A read-only public page designed to be shared with stakeholders, accessible without a login.
- **Complete Snapshot**: Displays all known information for a single metric, including:
  - Primary details like type, priority, and description.
  - A full list of existing test case coverage.
  - A list of all planned coverage entries.
  - Any notes or comments associated with the metric.
- **Context-Aware Navigation**: Shows a minimal "Login" link for public users and the full navigation bar for logged-in users.

### 6. User Management & Roles (`/users`)
- **Role-Based Access Control**: The application supports three distinct user roles:
  - `admin`: Full access to all features, including data management and user management.
  - `editor`: Can view all data and interact with the Coverage Planning page (set priorities, add notes, etc.). Cannot access Data or User Management.
  - `readonly`: Can view all data on all pages but cannot make any changes.
- **User Administration**: Admins can create, edit (including password resets), and delete user accounts.
- **Activity Log**: A searchable, admin-only page that logs all significant user actions.

---

## User Workflows (Happy Paths)

### 1. Admin Login & Basic Navigation
1.  Navigate to the `/auth/login` page.
2.  Enter valid administrator credentials (`username` and `password`).
3.  Upon success, be redirected to the "View Metrics" page.
4.  Successfully navigate between "Data Management", "Activity Log", "View Metrics", "Metric Reports", "Coverage Planning", and "User Management" using the navigation links.
5.  Click "Logout" to be securely logged out and redirected to the login page.

### 2. Data Management: Adding & Importing
1.  **Add Single Metric**: As an admin, navigate to `/manage`. Fill out the "Add New Glean Metric" form and submit. A success message appears, and the new metric is visible on the "View Metrics" page.
2.  **Bulk Import Coverage**: As an admin, navigate to `/manage`. Upload a valid CSV file using the "Bulk Import Coverage from CSV" form. A success message appears, summarizing the number of links created and errors/exceptions encountered. The new coverage is visible on the "View Metrics" page.
3.  **Add and Use an Exception**:
    1.  As an admin, navigate to `/manage`. Add a TCID (e.g., "12345") to the "Add New Exception" form and submit. The TCID appears in the "View Current Exceptions" table.
    2.  Attempt to add coverage for TCID "12345" using the "Create New Coverage Entry" form. The action fails with an error message stating the TCID is on the exception list.

### 3. Data Management: Using Extraction Tools
1.  **Probe Extraction**: As an admin, navigate to `/manage`. Upload a valid TestRail export CSV to the "Probe Extraction Tool". The browser initiates a download of a new CSV file (`extracted_probes.csv`) containing the original data plus "Found Probes", "Found Region", and "Found Engine" columns.
2.  **Rotation Extraction**: As an admin, navigate to `/manage`. Upload a valid rotation CSV to the "Extract from Rotation" tool. The browser initiates a download of a new CSV file (`rotation_extraction_output.csv`) containing the original data plus "Found Region", "Found Engine", "Found Metric Type", and "Found Metrics" columns.

### 4. Data Viewing and Interaction
1.  **Filter Metrics**: On the `/metrics` page, type a search term into the global search bar. All three tables (Coverage, Glean, Legacy) filter in real-time to show only matching rows.
2.  **Plan Coverage**: As an editor or admin on the `/planning` page:
    1.  Click on a metric row to expand its details.
    2.  In the "Add Plan" form at the bottom, enter a region/engine and click "Add Plan". A new "planned" entry appears in the sub-table.
    3.  Change the priority of a metric using its dropdown. The change is saved automatically.
    4.  In a planned entry row, enter a new TCID and click "Save". The planned entry is removed and a new, permanent coverage link appears in its place. The "TCID Count" in the main row increments.

### 5. View a Public Metric Status Page
1.  Navigate directly to a URL for a specific metric, for example: `/glean/browser.engagement.active_ticks/status`.
2.  The page loads successfully without requiring a login.
3.  The page displays a comprehensive, read-only summary of the metric's details, existing coverage, and planned coverage.
4.  The navigation bar is minimal, showing only a "Login" link.

---

## Technical Specifications

- **Backend**: Python 3 with Flask
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Database**: SQLite 3
- **Authentication**: Session-based with password hashing (scrypt)

## Local Setup and Installation

Follow these steps to get the application running on your local machine.

### 1. Prerequisites
- Python 3.8 or newer
- `pip` (Python package installer)

### 2. Clone the Repository
Open your terminal and navigate to your desired directory to clone the project.

### 3. Create and Activate a Virtual Environment
From the project's root directory (`pythonProject`), create and activate a virtual environment.

### 4. Install Dependencies
Install all the required Python packages using the `requirements.txt` file.

### 5. Set Up the Database
The application uses a `schema.sql` file to define its structure. To initialize or reset the database, run the following command from the project root directory: flask init-db
This will create an `instance/metrics.db` file with the correct schema, triggers, and a default admin user.

### 6. Configure Environment Variables
The application is configured to run in development mode via the `.flaskenv` file. No further configuration is needed for local development.

### 7. Run the Application
Start the Flask development server. flash run
The application will be available at `http://127.0.0.1:5000`.

