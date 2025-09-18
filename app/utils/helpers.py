# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/utils/helpers.py

import csv
import io
import re
import sqlite3
from flask import session, current_app
from ..services import database as db


def process_csv_upload(file, table_name, columns, redirect_url):
    """
    Generic function to process a CSV file upload and store results in session.
    Returns a tuple of (message, category).
    """
    if not file or file.filename == '':
        return 'No file selected.', 'error'
    if not file.filename.endswith('.csv'):
        return 'Invalid file type. Please upload a .csv file.', 'error'

    inserted_count = 0
    skipped_rows = []
    try:
        stream_content = file.stream.read().decode("UTF8")
        csv_stream = io.StringIO(stream_content)

        # --- DEFINITIVE FIX: Manually build the list of dictionaries ---
        reader = csv.reader(csv_stream)
        try:
            header = next(reader)
        except StopIteration:
            return "Cannot process an empty CSV file.", "error"

        # Normalize: lowercase, replace spaces with underscores
        normalized_header = [h.strip().lower().replace(' ', '_') for h in header]

        # Manually create a list of dictionaries
        dict_list = [dict(zip(normalized_header, row)) for row in reader]
        # --- END DEFINITIVE FIX ---

        with db.get_db_connection() as conn:
            # The transaction is managed by the 'with' block, commit happens on exit
            if table_name == 'coverage':
                # Handle complex coverage CSV upload
                for i, row in enumerate(dict_list, 2): # Iterate over our new list
                    # The service function expects specific keys, which we now have from normalization
                    success, message = db.add_coverage_entry(row)
                    if success:
                        inserted_count += 1
                    else:
                        skipped_rows.append(f"Line {i} (TCID: {row.get('tc_id', 'N/A')}): {message}")
            else:  # Logic for Glean/Legacy uploads
                pk_column = 'glean_name' if table_name == 'glean_metrics' else 'legacy_name'

                if pk_column not in normalized_header:
                    return f"CSV file is missing the required primary key column: '{pk_column}'", 'error'

                valid_columns = [col for col in columns if col in normalized_header]
                if not valid_columns:
                    return "CSV header does not contain any valid columns for this table.", 'error'

                processed_in_this_file = set()

                for i, row in enumerate(dict_list, 2): # Iterate over our new list
                    pk_value_raw = row.get(pk_column, '').strip()
                    if not pk_value_raw:
                        skipped_rows.append(f"Line {i}: Skipped because the primary key ('{pk_column}') is missing.")
                        continue

                    pk_value_clean = pk_value_raw.split(' ')[0]
                    row[pk_column] = pk_value_clean

                    if pk_value_clean in processed_in_this_file:
                        skipped_rows.append(
                            f"Line {i} (Metric: {pk_value_clean}): Skipped, as this metric was already processed in this file.")
                        continue

                    success, message = db.add_single_metric(table_name.split('_')[0], row)

                    if success:
                        inserted_count += 1
                        processed_in_this_file.add(pk_value_clean)
                    else:
                        skipped_rows.append(
                            f"Line {i} (Metric: {pk_value_clean}): Skipped, this metric already exists in the database.")
                        processed_in_this_file.add(pk_value_clean)

            conn.commit()

        session[f'{table_name}_upload_results'] = {'inserted': inserted_count, 'skipped': skipped_rows}
        return f"CSV processed: {inserted_count} rows inserted, {len(skipped_rows)} rows skipped.", 'success'

    except Exception as e:
        current_app.logger.error(f"A critical error occurred while processing the CSV: {e}")
        return f"A critical error occurred while processing the CSV: {e}", 'error'


def extract_probes_from_csv(file):
    """
    Handles file upload, extracts telemetry probes, regions, and engines,
    and returns a tuple of (csv_content, message, category).
    """
    probe_regex = re.compile(r'(?:browser|urlbar|contextservices)\.[\w.-]+')
    region_regex = re.compile(r'\b(US|DE|CA|CN)\b', re.IGNORECASE)
    engine_regex = re.compile(r'(google|duckduckgo|ecosia|qwant|bing|wikipedia|baidu)', re.IGNORECASE)

    try:
        stream_content = file.stream.read().decode("UTF8")
        infile = io.StringIO(stream_content)
        reader = csv.reader(infile)

        outfile = io.StringIO()
        writer = csv.writer(outfile)

        header = next(reader)
        # Ensure required columns exist
        required_cols = ['Title', 'Steps', 'Steps (Expected Result)']
        if not all(col in header for col in required_cols):
            return None, f"CSV is missing one or more required columns: {', '.join(required_cols)}", 'error'

        writer.writerow(header + ['Found Probes', 'Found Region', 'Found Engine'])

        title_col_index = header.index('Title')
        steps_col_index = header.index('Steps')
        expected_steps_col_index = header.index('Steps (Expected Result)')

        for row in reader:
            if len(row) <= max(title_col_index, steps_col_index, expected_steps_col_index):
                writer.writerow(row + ['malformed row', '', ''])
                continue

            title_text = row[title_col_index]
            steps_text = row[steps_col_index] + " " + row[expected_steps_col_index]

            found_probes = set(probe_regex.findall(steps_text))
            probes_result = ', '.join(sorted(list(found_probes))) if found_probes else 'nothing found'

            found_region = region_regex.search(title_text)
            region_result = found_region.group(1).upper() if found_region else 'NoRegion'

            found_engine = engine_regex.search(title_text)
            engine_result = found_engine.group(1).lower() if found_engine else 'NoEngine'

            writer.writerow(row + [probes_result, region_result, engine_result])

        return outfile.getvalue(), "Probes extracted successfully.", "success"

    except (ValueError, IndexError) as e:
        # Catches errors like missing columns or malformed rows
        return None, f"Error processing CSV: Missing required column or malformed row - {e}", 'error'
    except Exception as e:
        current_app.logger.error(f"An unexpected error occurred during probe extraction: {e}")
        return None, f"An unexpected error occurred during probe extraction: {e}", 'error'