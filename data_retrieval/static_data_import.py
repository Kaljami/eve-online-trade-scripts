import os
import requests
import bz2
from dotenv import load_dotenv
import mysql.connector
import sqlparse

# Here we download copies of the EVE Static Data Export kindly formatted to SQL dumps by FuzzySteve and import them to a database

load_dotenv()
mysql_user = os.getenv("mysql_user")
mysql_password = os.getenv("mysql_password")
mysql_host = os.getenv("mysql_host")
mysql_database = os.getenv("mysql_database_fuzzworks")

url_list = [
    'https://www.fuzzwork.co.uk/dump/latest/invTypes.sql.bz2', # type id's and names 
    'https://www.fuzzwork.co.uk/dump/latest/invVolumes.sql.bz2', # these are packaged volumes! 
    'https://www.fuzzwork.co.uk/dump/latest/invTypeMaterials.sql.bz2', # refine materials 
    'https://www.fuzzwork.co.uk/dump/latest/industryActivity.sql.bz2', # industry activity times 
    'https://www.fuzzwork.co.uk/dump/latest/industryActivityProducts.sql.bz2', # blueprint outputs
    'https://www.fuzzwork.co.uk/dump/latest/industryActivityMaterials.sql.bz2', # blueprint inputs
    'https://www.fuzzwork.co.uk/dump/latest/industryBlueprints.sql.bz2', # type id's and maximum runs
    'https://www.fuzzwork.co.uk/dump/latest/invCategories.sql.bz2', # pretty self explanatory, category, group and market group id's for type_id's
    'https://www.fuzzwork.co.uk/dump/latest/invGroups.sql.bz2',
    'https://www.fuzzwork.co.uk/dump/latest/invMarketGroups.sql.bz2',
    'https://www.fuzzwork.co.uk/dump/latest/mapSolarSystems.sql.bz2',
    'https://www.fuzzwork.co.uk/dump/latest/mapRegions.sql.bz2'
    ]

def import_sql_dump(dump_file):
    connection = mysql.connector.connect(
        host=mysql_host,
        port=3306,
        user=mysql_user,
        password=mysql_password,
        database=mysql_database
    )

    cursor = connection.cursor()

    # Read SQL dump file
    with open(dump_file, 'r', encoding='utf-8') as file:
        sql_commands = file.read()

    # Parse SQL commands
    parsed_commands = sqlparse.split(sql_commands)

    # Execute each command in the opened file 
    try:
        for command in parsed_commands:
            command = command.strip()  # Remove leading/trailing whitespace
            if command:
                #print("Executing SQL command:", command)
                cursor.execute(command)
        connection.commit()
        print(f"All SQL commands from {dump_file} executed successfully.")
    except Exception as e:
        print("Error executing SQL commands:", e)
        connection.rollback()

    connection.close()

for url in url_list:
    # Path to save the downloaded file
    downloaded_file = "temp_import.sql.bz2"
    # Path to save the extracted SQL file
    extracted_file = "temp_import.sql"

    # Download the file
    response = requests.get(url)
    with open(downloaded_file, "wb") as f:
        f.write(response.content)

    # Extract the downloaded file
    with open(extracted_file, "wb") as f_out, bz2.BZ2File(downloaded_file, "rb") as f_in:
        for data in iter(lambda : f_in.read(100 * 1024), b''):
            f_out.write(data)
    import_sql_dump(extracted_file)
    os.remove(downloaded_file)
    os.remove(extracted_file)


