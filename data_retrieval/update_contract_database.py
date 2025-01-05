# Download latest contracts from everef, extract, compare the contract_id's to ones in database and set everything else to finished
import os
import requests
import tarfile
import pandas as pd
import mysql.connector
from dotenv import load_dotenv

load_dotenv()
# MySQL Database:
db_user = os.getenv("mysql_user")
db_password = os.getenv("mysql_password")
db_host = os.getenv("mysql_host")
db_database = os.getenv("mysql_database")

def update_contract_status():
    url = "https://data.everef.net/public-contracts/public-contracts-latest.v2.tar.bz2"
    file_name = "public-contracts-latest.v2.tar.bz2"

    print(f"Downloading {file_name}...")
    response = requests.get(url, stream=True)
    with open(file_name, "wb") as file:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                file.write(chunk)

    # Extract the bz2 file
    extracted_dir = "latest_contracts"

    if not os.path.exists(extracted_dir):
        os.mkdir(extracted_dir)
    print(f"Extracting {file_name}...")
    with tarfile.open(file_name, "r:bz2") as tar:
        tar.extractall(path=extracted_dir)

    # Load the contracts.csv file into a pandas DataFrame
    csv_file_path = os.path.join(extracted_dir, "contracts.csv")

    if os.path.exists(csv_file_path):
        print(f"Loading {csv_file_path} into a DataFrame...")
        df = pd.read_csv(csv_file_path)
        print("DataFrame loaded successfully.")
    else:
        raise FileNotFoundError(f"{csv_file_path} does not exist.")


    db_connection = mysql.connector.connect(
        host=db_host,
        user=db_user,
        password=db_password,
        database=db_database
    )

    cursor = db_connection.cursor()

    # Create a temporary table to hold the new contract IDs
    temp_table_query = """
    CREATE TEMPORARY TABLE temp_contract_ids (
        contract_id BIGINT PRIMARY KEY
    )
    """
    cursor.execute(temp_table_query)

    # Insert contract IDs from the downloaded DataFrame into the temporary table
    temp_insert_query = "INSERT INTO temp_contract_ids (contract_id) VALUES (%s)"
    cursor.executemany(temp_insert_query, [(cid,) for cid in df['contract_id']])
    db_connection.commit()


    # Update the status in the main contracts table for IDs not in the temp table
    update_query = """
    UPDATE contracts
    SET status = 'expired'
    WHERE contract_id NOT IN (SELECT contract_id FROM temp_contract_ids)
    AND status != 'expired'
    """
    cursor.execute(update_query)
    db_connection.commit()

    print(f"Updated {cursor.rowcount} rows to 'expired' status.")

    # Drop the temporary table
    cursor.execute("DROP TEMPORARY TABLE IF EXISTS temp_contract_ids")

    # Close the database connection
    cursor.close()
    db_connection.close()