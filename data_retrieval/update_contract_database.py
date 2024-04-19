import os
import requests
import pandas as pd
from sqlalchemy import create_engine, inspect, text
from tqdm import tqdm
from datetime import datetime, timezone, timedelta
from time import sleep
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor


### SETTINGS BEGIN

load_dotenv()
# MySQL Database:
db_user = os.getenv("mysql_user")
db_password = os.getenv("mysql_password")
db_host = os.getenv("mysql_host")
db_database = os.getenv("mysql_database")

### SETTINGS END

load_dotenv()
engine = create_engine(f'mysql+pymysql://{db_user}:{db_password}@{db_host}/{db_database}')


def check_contract_status(contract_id, date_expired):
    if current_timestamp > date_expired: 
        return False # Contract has already expired 
    contract_items_url = f'https://esi.evetech.net/latest/contracts/public/items/{contract_id}/'
    res = requests.get(contract_items_url)
    #error_limit = int(res.headers.get('X-Esi-Error-Limit-Remain'))
    error_limit = res.headers.get('X-Esi-Error-Limit-Remain')
    limit_reset_seconds = res.headers.get('X-Esi-Error-Limit-Reset')
    contract_expires = pd.to_datetime(res.headers.get('Expires'), utc=True)
    #print(f"headers: {res.headers}")
    #print(f"Status: {res.status_code}. Error limit remaining: {error_limit}. Error limit resets in {limit_reset_seconds} seconds")
    try: 
        if res.status_code == 200:
            return True # Contract is still active
        if int(error_limit) < 20:
            print(f"ESI error_limit at {error_limit}. Chilling for 5 seconds. Limit will reset in {limit_reset_seconds} seconds.")
            sleep(5)
        elif 20 < int(error_limit) < 50:
            print(f"ESI error_limit at {error_limit}. Chilling for 1 second. Limit will reset in {limit_reset_seconds} seconds.")
            sleep(1)
        if res.status_code == 403 or res.status_code == 404: # Contract has been deleted or otherwise is not accessible
            return False
        if contract_expires-timedelta(hours=1) < current_timestamp: # If there is less than an hour until contract expires
            return False # Contract has been deleted by the creator and will be removed from esi within an hour 
        else: 
            return False # Something weird has happened
    except Exception as e:
        print(f"Error while running check_contract_status() for contract {contract_id}. Error: {e}\nType of error_limit: {type(error_limit)} \nESI http headers: {res.status_code}, {res.headers}")
        sleep(5)

current_timestamp = datetime.now(timezone.utc)
def update_existing_contracts():
    active_contracts = []
    expired_contracts = []
    existing_contract_ids_query = "SELECT contract_id, date_expired FROM contracts WHERE status='active';"
    existing_contract_ids_df = pd.read_sql_query(existing_contract_ids_query, con=engine)
    existing_contract_ids_df.set_index('contract_id', inplace = True)
    print(existing_contract_ids_df)
    active_contracts = []
    expired_contracts = []
    for contract_id in tqdm(existing_contract_ids_df.index, desc="Processing Contracts", unit="contracts", total=len(existing_contract_ids_df.index), maxinterval=2):
        date_expired = pd.to_datetime(existing_contract_ids_df.loc[contract_id, 'date_expired'], utc=True)
        if check_contract_status(contract_id, date_expired) == False:
            expired_contracts.append(contract_id)
        else:
            active_contracts.append(contract_id)
    print(f"Check finished. {len(expired_contracts)} contracts have expired or finished since last check. {len(active_contracts)} remain active.")
    conn = engine.connect()
    trans = conn.begin()
    expired_contracts_str = ', '.join(map(str, expired_contracts))
    sql_query = f"UPDATE contracts SET status='expired' WHERE contract_id IN ({expired_contracts_str});"
    
    try:
        conn = engine.connect()
        trans = conn.begin()
        conn.execute(text(sql_query))
        trans.commit()
        print(f"Status of {len(expired_contracts)} contracts succesfully updated in the database.")
    except Exception as e:
        if 'conn' in locals():
            trans.rollback()
            conn.close()
        raise e


update_existing_contracts()