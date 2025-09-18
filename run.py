# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/run.py

from app import create_app

# Create an app instance using the factory
app = create_app()

if __name__ == '__main__':
    # For development, run with the built-in server
    # For production, this file would be used by a WSGI server like Gunicorn
    app.run(debug=True)