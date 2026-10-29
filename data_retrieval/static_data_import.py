
import os
import requests
import gzip
from dotenv import load_dotenv
import mysql.connector
import sqlparse

# Download and import EVE Static Data Export SQL dumps from Fuzzwork.
# TODO: Save metadata and download only if a newer version is available.

load_dotenv()
mysql_user = os.getenv("mysql_user")
mysql_password = os.getenv("mysql_password")
mysql_host = os.getenv("mysql_host")
mysql_database = os.getenv("mysql_database_fuzzworks")

url_list = [
    'https://www.fuzzwork.co.uk/dump/latest-mysql.sql.gz'
]


def import_sql_dump(dump_file):
    connection = mysql.connector.connect(
        host=mysql_host,
        port=3306,
        user=mysql_user,
        password=mysql_password,
        database=mysql_database
    )

    try:
        cursor = connection.cursor()

        # Read SQL dump file
        with open(dump_file, 'r', encoding='utf-8') as file:
            sql_commands = file.read()

        # Parse SQL commands
        parsed_commands = sqlparse.split(sql_commands)

        # Execute each command
        for command in parsed_commands:
            command = command.strip()
            if command:
                cursor.execute(command)

        connection.commit()
        print(f"All SQL commands from {dump_file} executed successfully.")

    except Exception as e:
        print(f"Error executing SQL commands: {e}")
        connection.rollback()

    finally:
        connection.close()


for url in url_list:
    downloaded_file = "temp_import.sql.gz"
    extracted_file = "temp_import.sql"

    try:
        # Download the compressed SQL dump
        print(f"Downloading {url}...")
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()

        with open(downloaded_file, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

        response.close()

        # Extract the gzip-compressed SQL dump
        print(f"Extracting {downloaded_file}...")
        with gzip.open(downloaded_file, "rb") as f_in, \
             open(extracted_file, "wb") as f_out:
            for data in iter(lambda: f_in.read(100 * 1024), b''):
                f_out.write(data)

        # Import the extracted SQL
        import_sql_dump(extracted_file)

    except (requests.RequestException, OSError) as e:
        print(f"Error downloading or extracting {url}: {e}")

    finally:
        # Clean up temporary files
        for temp_file in (downloaded_file, extracted_file):
            if os.path.exists(temp_file):
                os.remove(temp_file)
