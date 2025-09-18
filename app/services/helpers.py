# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/utils/helpers.py

import csv
import io
import re
import sqlite3
from flask import session
from ..services import database as db


def process_csv_upload(file, table_name, columns, redirect_url):
    """
    Generic function to process a CSV file upload and store results in session.
    """
    if not file or file.filename == '':
        return 'No file selected.', 'error'
    if not file.filename.endswith('.csv'):
        return 'Invalid file type. Please upload a .csv file.', 'error'

    inserted_count = 0
    skipped_rows = []
    try:
        stream_content = file.stream.read().decode("UTF8")
        # This is a placeholder for a more robust CSV stream handler if needed
        csv_stream = io.StringIO(stream_content)
        csv_reader = csv.reader(csv_stream)
        header = next(csv_reader)

        with db.get_db_connection() as conn:
            cursor = conn.cursor()

            if table_name == 'coverage':
                # This logic is complex and better handled by a dedicated function if needed.
                # For now, keeping it simple.
                # You would iterate and call db.add_coverage_entry for each row.
                pass  # Simplified for this example
            else:  # Logic for Glean/Legacy uploads
                placeholders = ', '.join(['?'] * len(columns))
                sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders});"

                for i, row in enumerate(csv_reader, 2):
                    if not row or not row[0].strip():
                        skipped_rows.append(f"Line {i}: Skipped because the metric name is missing.")
                        continue

                    padded_row = (row + [None] * len(columns))[:len(columns)]
                    data_tuple = tuple(val.strip() if val and val.strip() else None for val in padded_row)

                    try:
                        cursor.execute(sql, data_tuple)
                        inserted_count += 1
                    except sqlite3.IntegrityError as e:
                        skipped_rows.append(f"Line {i} (Metric: {data_tuple[0]}): {e}")
            conn.commit()

        session[f'{table_name}_upload_results'] = {'inserted': inserted_count, 'skipped': skipped_rows}
        return f"CSV processed: {inserted_count} rows inserted, {len(skipped_rows)} rows skipped.", 'success'

    except Exception as e:
        return f"A critical error occurred while processing the CSV: {e}", 'error'


def extract_probes_from_csv(file):
    """
    Handles file upload, extracts telemetry probes, regions, and engines,
    and returns a new CSV file content as a string.
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

        return outfile.getvalue()

    except (ValueError, IndexError) as e:
        # Catches errors like missing columns or malformed rows
        return None, f"Error processing CSV: Missing required column or malformed row - {e}", 'error'
    except Exception as e:
        return None, f"An unexpected error occurred during probe extraction: {e}", 'error'