import os
import sso_utils
import pandas as pd
from sde_utils import get_item_names
from price_differences import get_prices_from_station
import influxdb_client
#from influxdb_client import InfluxDBClient, Point, WritePrecision
#from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb import InfluxDBClient
import logging
import time
import mysql.connector

logging.basicConfig(filename='logs/latest.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')


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
        print ("no market orders found")
        return 0,0

    
def get_pageful_of_assets(session, character_assets_url, page):
    logging.debug('Starting get_pageful_of_assets')
    print(f"grabbing pageful of assets, page number {page}")
    params = {'page': page}
    
    max_retries = 5  # Define the maximum number of retries
    retry_delay = 1  # Define the delay between retries in seconds
    # retry if response is 504 timeout
    for i in range(max_retries):
        response = session.get(character_assets_url, params=params)
        if response.status_code != 504:  
            break
        print("Got timeout when grabbing assets. Retrying...")
        logging.debug(f"Got timeout when grabbing assets. Retrying...")
        time.sleep(retry_delay)
    logging.debug(f"Response status: {response.status_code}")
    logging.debug(f"Response headers: {response.headers}")
    try:
        response_json = response.json()
        logging.debug(f"Response JSON: {response_json}")
        return response_json
    except Exception as json_error:
        print(f"Error parsing JSON: {json_error}")
        logging.debug(f"Error parsing JSON: {json_error}")
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
        return None

def get_character_assets(prices_dataframe):
    character_assets_url = f'https://esi.evetech.net/latest/characters/{character_id}/assets/'

    try:
        with sso_session:
            response = sso_session.get(character_assets_url)
            if response.status_code != 200:
                print(f"Error: {response.status_code} - {response.text}")
                return None
            
            n_asset_pages = int(response.headers.get('x-pages', 0))
            print(f"In total {n_asset_pages} pages of assets")
            
            character_assets_data = asset_getter_really(sso_session, character_assets_url, n_asset_pages)
            merged_asset_df = character_assets_data.merge(prices_dataframe, left_on='type_id', right_index=True)
    except Exception as e:
        print(f"Exception during get_character_assets: {e}")           
 
    # calculate total asset value
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
        print ("no industry jobs found")
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
        db_user = None
        db_password = None
        db_host = None
        db_database = None
        cnx = mysql.connector.connect(user=db_user, password=db_password,
                                      host=db_host, database=db_database)
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

def create_summary_dataframe(character_id, character_name, character_wallet_balance, character_asset_value, character_industry_value, character_sell_order_value, character_buy_order_value, character_implants):
    data = {#'character_id': [character_id], 
            #'character_name': [character_name], 
            'character_wallet_balance': [character_wallet_balance], 
            'character_asset_value': [character_asset_value], 
            'character_industry_value': [float(character_industry_value)],
            'character_sell_order_value': [float(character_sell_order_value)],
            'character_buy_order_value': [float(character_buy_order_value)],
            'character_implants': [float(character_implants)],
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
    def read_influxdb_settings(file_path='influxdb_v1_settings.txt'):
        keys = {}
        try:
            with open(file_path, 'r') as file:
                for line in file:
                    key, value = line.strip().split('=')
                    keys[key] = value
            return keys
        except FileNotFoundError:
            print(f"File '{file_path}' not found.")
            return None

    influxdb_settings = read_influxdb_settings()
    if influxdb_settings:
        host = influxdb_settings.get('host')
        port = influxdb_settings.get('port')
        database = influxdb_settings.get('database')
        username = influxdb_settings.get('username')
        password = influxdb_settings.get('password')

    
    json_body = convert_dataframe_to_influxdb_json(df, measurement, tags, time_column)
    # Connect to InfluxDB and write the data
    client = InfluxDBClient(host=host, port=port, database=database)
    client.write_points(json_body)

    print("Data successfully written to InfluxDB.")



def rotate_all_sessions():
    sessions_directory_stats = 'sessions_stats'
    session_files = [f for f in os.listdir(sessions_directory_stats) if f.endswith('.json')]
    print (session_files)
    char_index = 0

    for session_file in session_files:
        char_index += 1
        global character_id, character_name, prices_dataframe, avg_prices_dataframe, character_sell_order_value, character_buy_order_value, character_asset_value, character_industry_value, character_wallet_balance, character_implants
        print ("Using session file", session_file)
        cycle_sso(session_file)
        character_id = sso_utils.get_character_id(sso_session)
        character_name = sso_utils.get_character(sso_session)
        print(f'SSO Status: {f"Logged in as {character_name}" if character_name else "Not logged in"}')
        if char_index == 1:
            prices_dataframe = get_jita_prices(True) #only get live prices on the first round
            avg_prices_dataframe = get_average_prices()

        character_sell_order_value, character_buy_order_value = get_character_orders()
        character_asset_value = get_character_assets(avg_prices_dataframe)
        character_industry_value = get_character_industry_jobs(prices_dataframe)
        character_wallet_balance = get_character_wallet()
        character_implants = get_character_implants()
        get_character_mining()
        df=create_summary_dataframe(character_id, character_name, character_wallet_balance, character_asset_value, character_industry_value, character_sell_order_value, character_buy_order_value, character_implants)
        write_to_influxdb_v1(df, measurement='character_stats', tags={'character_name': character_name})

rotate_all_sessions()

# other data to get:
# plex wallet (is it possible?)
# implants
# wallet transactions to track most traded items etc
# contract value
# mining ledger
#   in grafana: daily and monthly cumulative mining amounts
#   separate moon mining from others to estimate tax bill 
# TODO generate a table of refined value of each ore type and store in mysql

# TODO move all variables to .env: 
# eve SSO keys
# influxdb
# mysql
