import os
import data_retrieval.sso_utils as sso_utils
import pandas as pd
from data_processing.sde_utils import get_item_names
from data_retrieval.order_data import get_prices_from_station
import influxdb_client
#from influxdb_client import InfluxDBClient, Point, WritePrecision
#from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb import InfluxDBClient
import logging
import time
import mysql.connector
from dotenv import load_dotenv
from sqlalchemy import create_engine, exc

logging.basicConfig(filename='logs/pull_statistics.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
load_dotenv()

### Setting begin

influxdb_host = os.getenv("influxdb_host")
influxdb_port = os.getenv("influxdb_port")
influxdb_database = os.getenv("influxdb_database")
influxdb_username = os.getenv("influxdb_username")
influxdb_password = os.getenv("influxdb_password")

mysql_user = os.getenv("stats_mysql_user")
mysql_password = os.getenv("stats_mysql_password")
mysql_host = os.getenv("stats_mysql_host")
mysql_database = os.getenv("stats_mysql_database")

### Settings end

engine = create_engine(f'mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}/{mysql_database}')

def cycle_sso(session_file):
    global sso_session
    #sessions_directory_stats = 'sessions_stats'
    #session_files = [f for f in os.listdir(sessions_directory_stats) if f.endswith('.json')]
    #print (session_files)
    sso_session = sso_utils.temp_test_oauth_session(session_file)

def get_character_orders():
    character_orders_url = f'https://esi.evetech.net/latest/characters/{character_id}/orders/'
    character_orders_response = sso_session.get(character_orders_url)
    character_orders_data = character_orders_response.json()
    #print ("current player sell orders from ESI:",character_orders_data) 
    if character_orders_data: 
        sell_orders = pd.DataFrame(character_orders_data)
        buy_orders = pd.DataFrame(character_orders_data)
        sell_orders.set_index('type_id', inplace=True)
        buy_orders.set_index('type_id', inplace=True)
        sell_orders['is_buy_order'] = sell_orders['is_buy_order'].fillna(False)
        typeIDs_to_names = get_item_names()
        sell_orders['type_name'] = sell_orders.index.map(typeIDs_to_names)
        buy_orders['type_name'] = buy_orders.index.map(typeIDs_to_names)

        sell_orders_f = sell_orders[sell_orders['is_buy_order'] == False]
        buy_orders_f = buy_orders[buy_orders['is_buy_order'] == True]
        sell_orders_f['total_value'] = sell_orders_f['price'] * sell_orders_f['volume_remain']
        sell_order_total_value = sell_orders_f['total_value'].sum()
        print("Sell order total value:", sell_order_total_value)
        buy_order_total_value = buy_orders_f['escrow'].sum()
        print("Buy order total value:", buy_order_total_value)
        
        #print("Sell orders:")
        #print(str(sell_orders_f))
        #print("Buy orders:")
        #print(str(buy_orders_f))
        return sell_order_total_value, buy_order_total_value
    else:
        print ("No character market orders found")
        return 0,0

    
def get_pageful_of_assets(session, character_assets_url, page):
    logging.debug('Starting get_pageful_of_assets')
    print(f"grabbing pageful of assets, page number {page}")
    params = {'page': page}
    
    max_retries = 5  
    retry_delay = 1  # delay between retries in seconds
    # retry if response is 504 timeout
    for i in range(max_retries):
        response = session.get(character_assets_url, params=params)
        if response.status_code != 504:  
            break # if not a timeout, continue as normal
        print("Got timeout when grabbing assets. Retrying...")
        logging.warning(f"Got timeout when grabbing assets with get_pageful_of_assets(). Retrying...")
        time.sleep(retry_delay)
    logging.info(f"get_pageful_of_assets response status: {response.status_code}")
    logging.debug(f"Response headers: {response.headers}")
    try:
        response_json = response.json()
        logging.debug(f"Response JSON for get_pageful_of_assets(): {response_json}")
        return response_json
    except Exception as json_error:
        print(f"Error parsing JSON: {json_error}")
        logging.error(f"Error parsing JSON in get_pageful_of_assets(): {json_error}")
        return None

def get_all_assets(session, character_assets_url, pages):
    print(f"task is to get {pages} pages of assets from {character_assets_url}")
    assets_data_list = []  # List to store results from each page
    for page in range(1, pages + 1):
        page_data = get_pageful_of_assets(session, character_assets_url, page)
        if page_data:
            assets_data_list.append(pd.DataFrame(page_data))
            #page_dataframe = pd.DataFrame(page_data)
            #print(str(page_dataframe))
    return assets_data_list

def asset_getter_really(sso_session, character_assets_url, n_asset_pages):
    assets_data_list = get_all_assets(sso_session, character_assets_url, n_asset_pages)
    try:
        # Concatenate all DataFrames into a single DataFrame
        merged_df = pd.concat(assets_data_list, ignore_index=True)
        #print("Merged DataFrame:")
        #print(merged_df)
        return merged_df
    except ValueError as ve:
        print(f"ValueError: {ve}")
        logging.error(f"Error in asset_getter_really(): {ve}")
        return None

def get_character_assets(prices_dataframe):
    character_assets_url = f'https://esi.evetech.net/latest/characters/{character_id}/assets/'
    max_retries = 5  
    retry_delay = 1  # delay between retries in seconds, not implenented so far
    any_retry_successful = False

    try:
        for i in range(max_retries):
            with sso_session:
                response = sso_session.get(character_assets_url)
                if response.status_code == 200:
                    n_asset_pages = int(response.headers.get('x-pages', 0))
                    print(f"In total {n_asset_pages} pages of assets")
                    
                    character_assets_data = asset_getter_really(sso_session, character_assets_url, n_asset_pages)
                    merged_asset_df = character_assets_data.merge(prices_dataframe, left_on='type_id', right_index=True)
                    any_retry_successful = True
                    break # if not a timeout or other error, continue as normal
                else:
                    print(f"Error: {response.status_code} - {response.text} in get_character_assets")
                    logging.warning(f"Error: {response.status_code} - {response.text} in get_character_assets. Trying again.")
                
    except Exception as e:
        print(f"Exception during get_character_assets: {e}")
        logging.error(f"Error in get_character_assets(): {e}")

    if not any_retry_successful:
        return None
 
    # calculate total asset value
    if 'is_blueprint_copy' in merged_asset_df.columns:
        merged_asset_df.loc[merged_asset_df['is_blueprint_copy'] == True, 'average_price'] =  0
    merged_asset_df['total_value'] = merged_asset_df['quantity'] * merged_asset_df['average_price']
    merged_asset_df['type_name'] = merged_asset_df['type_id'].map(get_item_names())
    total_asset_value = merged_asset_df['total_value'].sum()
    #print("Assets:")
    #print(str(merged_asset_df))
    #print(f"Total asset value: {total_asset_value}")
    #merged_asset_df.to_csv('merged_asset_df.csv', index=False)
    #merged_asset_df.to_excel('merged_asset_df.xlsx')
    return total_asset_value

def get_corporation_assets(prices_dataframe):
    corporation_assets_url = f'https://esi.evetech.net/latest/corporations/{corporation_id}/assets/'
    max_retries = 5  
    retry_delay = 1  # delay between retries in seconds, not implenented so far
    any_retry_successful = False

    try:
        for i in range(max_retries):
            with sso_session:
                response = sso_session.get(corporation_assets_url)
                if response.status_code == 200:
                    n_asset_pages = int(response.headers.get('x-pages', 0))
                    print(f"In total {n_asset_pages} pages of assets")
                    
                    corporation_assets_data = asset_getter_really(sso_session, corporation_assets_url, n_asset_pages)
                    logging.debug(f"Got {len(corporation_assets_data.index)} lines of corporation assets")
                    merged_asset_df = corporation_assets_data.merge(prices_dataframe, left_on='type_id', right_index=True)
                    any_retry_successful = True
                    break # if not a timeout or other error, continue as normal
                else:
                    print(f"Error: {response.status_code} - {response.text} in get_corporation_assets")
                    logging.warning(f"Error: {response.status_code} - {response.text} in get_corporation_assets. Trying again.")
                
    except Exception as e:
        print(f"Exception during get_corporation_assets: {e}")
        logging.error(f"Error in get_corporation_assets(): {e}")

    if not any_retry_successful:
        return None
 
    # calculate total asset value
    if 'is_blueprint_copy' in merged_asset_df.columns:
        merged_asset_df.loc[merged_asset_df['is_blueprint_copy'] == True, 'average_price'] =  0
    merged_asset_df['total_value'] = merged_asset_df['quantity'] * merged_asset_df['average_price']
    merged_asset_df['type_name'] = merged_asset_df['type_id'].map(get_item_names())
    total_asset_value = merged_asset_df['total_value'].sum()
    #print("Assets:")
    #print(str(merged_asset_df))
    #print(f"Total asset value: {total_asset_value}")
    #merged_asset_df.to_csv('merged_asset_df.csv', index=False)
    #merged_asset_df.to_excel('merged_asset_df.xlsx')
    logging.debug(f"Got total corp asset value of {total_asset_value}")
    return total_asset_value

def get_character_industry_jobs(prices_dataframe):
    character_industry_jobs_url = f'https://esi.evetech.net/latest/characters/{character_id}/industry/jobs/'
    character_industry_jobs_response = sso_session.get(character_industry_jobs_url)
    character_industry_jobs_data = character_industry_jobs_response.json()
    #print(character_industry_jobs_data)
    if character_industry_jobs_data:
        character_industry_jobs = pd.DataFrame(character_industry_jobs_data)
        #print("Industry jobs:")
        #print(str(character_industry_jobs))

        # get value of industry job outputs
        # Merge price data on the 'product_type_id' field
        merged_industry_df = character_industry_jobs.merge(prices_dataframe, left_on='product_type_id', right_index=True)
        # Multiply the 'runs' column by the 'jita_price' column
        merged_industry_df['total_price'] = merged_industry_df['runs'] * merged_industry_df['jita_price']
        # Calculate the total sum for all rows
        total_sum = merged_industry_df['total_price'].sum()
        #print(f"Total industry job outputs: {total_sum}")
        return total_sum
    else:
        print ("no character industry jobs found")
        return 0
    
def get_corporation_industry_jobs(prices_dataframe):
    corporation_industry_jobs_url = f'https://esi.evetech.net/latest/corporations/{corporation_id}/industry/jobs/'
    corporation_industry_jobs_response = sso_session.get(corporation_industry_jobs_url)
    logging.debug(f"corp industry jobs response: {corporation_industry_jobs_response}")
    logging.debug(f"corp industry jobs response headers: {corporation_industry_jobs_response.headers}")
    logging.debug(f"corp industry jobs response json content: {corporation_industry_jobs_response.json()}")
    corporation_industry_jobs_data = corporation_industry_jobs_response.json()
    #print("corporation_industry_jobs_data:", corporation_industry_jobs_data)
    if corporation_industry_jobs_data:
        corporation_industry_jobs = pd.DataFrame(corporation_industry_jobs_data)
        #print("Industry jobs:")
        #print(str(corporation_industry_jobs))

        # get value of industry job outputs
        # Merge price data on the 'product_type_id' field
        merged_industry_df = corporation_industry_jobs.merge(prices_dataframe, left_on='product_type_id', right_index=True)
        # Multiply the 'runs' column by the 'jita_price' column
        merged_industry_df['total_price'] = merged_industry_df['runs'] * merged_industry_df['jita_price']
        # Calculate the total sum for all rows
        total_sum = merged_industry_df['total_price'].sum()
        #print(f"Total industry job outputs: {total_sum}")
        logging.debug(f"Total corporation industry job outputs: {total_sum}")
        return total_sum
    else:
        logging.debug(f"no corporation industry jobs found")
        print ("no corporation industry jobs found")
        return 0
    
def get_character_implants(): #TODO add the current clone implants to this
    clones_url= f"https://esi.evetech.net/latest/characters/{character_id}/clones/"
    clones_response = sso_session.get(clones_url)
    clones_data = clones_response.json()
    if clones_data:
        #print("character clones:", clones_data)
        implants = [implant for clone in clones_data['jump_clones'] for implant in clone['implants']]
        # Create a DataFrame from the implants list
        clones_df = pd.DataFrame(implants, columns=['implant'])
        merged_clones_df = clones_df.merge(prices_dataframe, left_on='implant', right_index=True)
        # Calculate the total sum for all rows
        total_sum = merged_clones_df['jita_price'].sum()
        #print(str(merged_clones_df))
        print(f"Total clone implant value: {total_sum}")
        return total_sum
    else:
        print ("no clones found")
        return 0

def get_character_mining():
    mining_url = f'https://esi.evetech.net/latest/characters/{character_id}/mining/'
    mining_response = sso_session.get(mining_url)
    mining_data = mining_response.json()
    if mining_data:
        #print(mining_response.headers)
        #print(mining_data)
        cnx = mysql.connector.connect(user=mysql_user, password=mysql_password,
                                      host=mysql_host, database=mysql_database)
        cursor = cnx.cursor()
        # Iterate over the mining data and insert each record into the MySQL database
        # If a recordd already exists, update it, to prevent duplicates
        for record in mining_data:
            add_mining = ("""
                INSERT INTO Mining 
                (date, quantity, solar_system_id, type_id, character_id, character_name) 
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                quantity = IF(VALUES(quantity) > quantity, VALUES(quantity), quantity)
            """)
            data_mining = (record['date'], record['quantity'], record['solar_system_id'], record['type_id'], character_id, character_name)
            cursor.execute(add_mining, data_mining)
        cnx.commit()
        cursor.close()
        cnx.close()

def get_character_wallet():
    character_wallet_url = f'https://esi.evetech.net/latest/characters/{character_id}/wallet/'
    character_wallet_response = sso_session.get(character_wallet_url)
    character_wallet_data = character_wallet_response.json()
    #print("Wallet balance:")
    #print(character_wallet_data)
    return character_wallet_data

def get_character_journal():
    from datetime import datetime
    journal_url = f'https://esi.evetech.net/latest/characters/{character_id}/wallet/journal/'
    response = sso_session.get(journal_url)
    journal = response.json()
    #print (response.headers)
    #print ("journal:", journal)
    journal_dataframe = pd.DataFrame(journal)
    print(journal_dataframe)
    if not journal_dataframe.empty:
        journal_dataframe['date'] = pd.to_datetime(journal_dataframe['date'])
        journal_dataframe['date'] = journal_dataframe['date'].dt.strftime('%Y-%m-%d %H:%M:%S')
        journal_dataframe['character_id'] = character_id
        journal_dataframe['character_name'] = character_name
        #journal_dataframe.to_sql('journal', con=engine, if_exists='append', index=False)
        existing_entries_query = "SELECT id FROM journal"
        existing_entries = pd.read_sql(existing_entries_query, con=engine)
        journal_dataframe.drop_duplicates(subset='id', keep='first', inplace=True) # might be needed for "ref_type": "bounty_surcharge" since it has duplicate ID. 
        new_entries = journal_dataframe[~journal_dataframe['id'].isin(existing_entries['id'])]
        try:
            new_entries.to_sql('journal', con=engine, if_exists='append', index=False, method='multi', chunksize=1000)
            print(f"Wallet journal for {character_name} saved in MySQL")
        except Exception as e:
            print(f"Unable to save wallet journal for {character_name} in MySQL. CSV dump saved as exports/debug_journal.csv. Error:")
            print(e)
            new_entries.to_csv('exports/debug_journal.csv')
            logging.error(f"Unable to save wallet journal for {character_name} in MySQL. CSV dump saved as exports/debug_journal.csv. Error: {e}")
    else: 
        print(f"Journal for {character_id} was empty")


def get_character_transactions():
    from datetime import datetime
    transactions_url = f'https://esi.evetech.net/latest/characters/{character_id}/wallet/transactions/'
    response = sso_session.get(transactions_url)
    transactions = response.json()
    if transactions: 
        #print (response.headers)
        #print ("transactions:", transactions)
        transactions_dataframe = pd.DataFrame(transactions)
        #print(f"Transactions for {character_name} {character_id}:")
        #print(transactions_dataframe)
        transactions_dataframe['date'] = pd.to_datetime(transactions_dataframe['date'])
        transactions_dataframe['date'] = transactions_dataframe['date'].dt.strftime('%Y-%m-%d %H:%M:%S')
        transactions_dataframe['character_id'] = character_id
        transactions_dataframe['character_name'] = character_name
        #print(transactions_dataframe)
        existing_entries_query = "SELECT journal_ref_id FROM transactions"
        existing_entries = pd.read_sql(existing_entries_query, con=engine)
        new_entries = transactions_dataframe[~transactions_dataframe['journal_ref_id'].isin(existing_entries['journal_ref_id'])]
        new_entries.to_sql('transactions', con=engine, if_exists='append', index=False, method='multi', chunksize=1000)
        print(f"Market transactions for {character_name} saved in MySQL")
    else: 
        print(f"No market transactions found for {character_name}")

def get_character_contracts():
    character_contracts_data = sso_session.get(f'https://esi.evetech.net/latest/characters/{character_id}/contracts/').json()
    #print(character_contracts_data)
    if character_contracts_data:
        character_contracts = pd.DataFrame(character_contracts_data)

       # Here "all" means all contracts created by this character
        all_contracts = character_contracts[character_contracts['issuer_id'] == character_id] 
        all_contracts.set_index('contract_id', inplace=True)

        ### set one as finished for testing
        #all_contracts.at[203677843, 'status'] = 'finished'
        ### 
        
        try: # check if character_contracts exist:
            existing_entries_query = f"SELECT * FROM character_contracts WHERE issuer_id = {character_id}"
            existing_entries = pd.read_sql(existing_entries_query, con=engine)
            existing_entries.set_index('contract_id', inplace=True)
            print("existing character contracts:", existing_entries)

            # Find rows where the status is not equal in these dataframes
            
            comparison_mask = all_contracts['status'].loc[existing_entries.index] != existing_entries['status']
            unequal_rows = comparison_mask[comparison_mask].index
            recently_finished = all_contracts.loc[unequal_rows]

            # Send messages for contracts that have now finished
            for index, row in recently_finished.iterrows():
                status = row['status']
                contract_id = index
                price = row['price']
                if status == 'finished':
                    print(f"{character_name}'s contract {contract_id} has finished! We got {prettify_num(price)} ISK for it.")
                else: 
                    print(f'Contract id {contract_id} status has changed to {status}')

            new_entries = all_contracts[~all_contracts.index.isin(existing_entries.index)]
            new_entries.to_sql('character_contracts', con=engine, if_exists='append', index=True, method='multi', chunksize=1000)


        except Exception as e:
            logging.error(f'Error while saving character contracts: {e}')
            logging.debug('Created a new table character_contracts in mysql')
            all_contracts.to_sql('character_contracts', con=engine, if_exists='replace', index=True, method='multi', chunksize=1000)
        print(f"Contracts from {character_name} saved in MySQL")



        # for outstanding value, only get ones where status is 'outstanding'
        outstanding_contracts = character_contracts[character_contracts['status'] == 'outstanding']
        #print (outstanding_contracts)
        total_sum = outstanding_contracts['price'].sum()
        print(f"Total outstanding contract value: {total_sum}")
        n_outstanding_contracts = len(outstanding_contracts)
        print(f"Number of outstanding contracts: {n_outstanding_contracts}")
        return total_sum, n_outstanding_contracts
    else:
        print ("no character contracts found")
        return 0, 0

def get_jita_prices(cached):
    prices_dataframe = pd.DataFrame()
    jita_prices = get_prices_from_station("Jita", "sell", cached) #set False to get updated prices
    prices_dataframe['jita_price'] = jita_prices
    print("jita_price data downloaded")
    #print(str(prices_dataframe))
    return prices_dataframe

def get_average_prices():
    avg_prices_url = f"https://esi.evetech.net/latest/markets/prices/?datasource=tranquility"
    avg_prices_response = sso_session.get(avg_prices_url)
    avg_prices_data = avg_prices_response.json()
    avg_prices_dataframe = pd.DataFrame(avg_prices_data)
    avg_prices_dataframe.set_index('type_id', inplace=True)
    #print(str(avg_prices_dataframe))
    return avg_prices_dataframe

def create_summary_dataframe(character_id, character_name, character_wallet_balance, character_asset_value, character_industry_value, character_sell_order_value, character_buy_order_value, character_implants, corporation_asset_value, corporation_industry_value, character_contract_value, character_contract_amount):
    data = {#'character_id': [character_id], 
            #'character_name': [character_name], 
            'character_wallet_balance': [character_wallet_balance], 
            'character_asset_value': [character_asset_value], 
            'character_industry_value': [float(character_industry_value)],
            'character_sell_order_value': [float(character_sell_order_value)],
            'character_buy_order_value': [float(character_buy_order_value)],
            'character_implants': [float(character_implants)],
            'corporation_asset_value': [int(corporation_asset_value)],
            'corporation_industry_value': [int(corporation_industry_value)],
            'character_contract_value': [int(character_contract_value)],
            'character_contract_amount': [int(character_contract_amount)],
            }
    summary_dataframe = pd.DataFrame(data)
    #print(str(summary_dataframe))
    return (summary_dataframe)

def convert_dataframe_to_influxdb_json(df, measurement, tags, time_column='time'):

    if time_column not in df.columns:
        df[time_column] = pd.to_datetime('now', utc=True)

    # Convert DataFrame to InfluxDB JSON format
    json_body = []
    for _, row in df.iterrows():
        point = {
            "measurement": measurement,
            "tags": tags,
            "time": row[time_column],
            "fields": {column: row[column] for column in df.columns if column != time_column}
        }
        json_body.append(point)
    logging.debug(f"sent json to influxdb: {json_body}")
    return json_body

def write_to_influxdb_v1(df, measurement, tags, time_column='time'):
    json_body = convert_dataframe_to_influxdb_json(df, measurement, tags, time_column)
    # Connect to InfluxDB and write the data
    client = InfluxDBClient(host=influxdb_host, port=influxdb_port, database=influxdb_database)
    client.write_points(json_body)

    print("Data successfully written to InfluxDB.")

def prettify_num(number):
    pretty_num = f'{int(number):,}' # remove decimals to make ints pretty
    return pretty_num

def rotate_all_sessions():
    sessions_directory_stats = 'sessions_stats'
    session_files = [f for f in os.listdir(sessions_directory_stats) if f.endswith('.json')]
    #print (session_files)
    char_index = 0

    for session_file in session_files: #TODO add tqdm progress bar
        char_index += 1
        global character_id, character_name, corporation_id, corporation_name, prices_dataframe, avg_prices_dataframe, character_sell_order_value, character_buy_order_value, character_asset_value, character_industry_value, character_wallet_balance, character_implants
        print ("Using session file", session_file)
        cycle_sso(session_file)
        character_id = sso_utils.get_character_id(sso_session)
        character_name = sso_utils.get_character(sso_session)
        corporation_id = sso_utils.get_corporation_id(sso_session, character_id)
        corporation_ceo_id = sso_utils.get_corporation_ceo(corporation_id)
        corporation_name = sso_utils.get_corporation_name(corporation_id)
        logging.debug(f"-----------------\nStarting to pull statistics for character {character_name}")
        print(f'SSO Status: {f"Logged in as {character_name}" if character_name else "Not logged in"}')
        if char_index == 1:
            prices_dataframe = get_jita_prices(False) #only get live prices on the first round
            avg_prices_dataframe = get_average_prices()

        character_sell_order_value, character_buy_order_value = get_character_orders()
        character_asset_value = get_character_assets(avg_prices_dataframe)
        character_industry_value = get_character_industry_jobs(prices_dataframe)
        character_wallet_balance = get_character_wallet()
        character_implants = get_character_implants()
        get_character_mining()
        get_character_journal()
        get_character_transactions()
        character_contract_value, character_contract_amount = get_character_contracts()
        if character_id == corporation_ceo_id:
            logging.debug(f"{character_name} is CEO of corporation ID {corporation_id}. Getting corporation data.")
            corporation_asset_value = get_corporation_assets(avg_prices_dataframe)
            corporation_industry_value = get_corporation_industry_jobs(prices_dataframe)
            df=create_summary_dataframe(character_id, character_name, character_wallet_balance, character_asset_value, character_industry_value, character_sell_order_value, character_buy_order_value, character_implants, corporation_asset_value, corporation_industry_value, character_contract_value, character_contract_amount)
            write_to_influxdb_v1(df, measurement='character_stats', tags={'character_name': character_name, 'corporation_name': corporation_name})
        else: 
            corporation_asset_value = 0
            corporation_industry_value = 0
            df=create_summary_dataframe(character_id, character_name, character_wallet_balance, character_asset_value, character_industry_value, character_sell_order_value, character_buy_order_value, character_implants, corporation_asset_value, corporation_industry_value, character_contract_value, character_contract_amount)
            write_to_influxdb_v1(df, measurement='character_stats', tags={'character_name': character_name})

rotate_all_sessions()

# other data to get:
# plex wallet (is it possible?)
# implants currently in head
# wallet transactions to track most traded items etc
    # should item names be added to the same table? 
# contract value
