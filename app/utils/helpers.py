# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/utils/helpers.py

import csv
import io
import re
from flask import flash, session
from ..services import database as db # Helpers can also use the database service

def process_csv_upload(file, table_name, columns, redirect_url):
    """Generic function to process a CSV file upload and store results in session."""
    # This is where the logic from your old 'process_csv_upload' function goes.
    # It's a good practice to keep it separate from the routes.
    flash("CSV processed successfully!", "success") # Placeholder
    pass

def extract_probes_from_csv(file):
    """
    Handles file upload, extracts telemetry probes, regions, and engines,
    and returns a new CSV file content as a string.
    """
    # This is where the logic from your old 'extract_probes' function goes.
    # It should return the CSV content, not a Flask Response.
    flash("Probes extracted successfully!", "success") # Placeholder
    return "col1,col2\nval1,val2" # Placeholder