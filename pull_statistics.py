import os
import sso_utils
import pandas as pd
from sde_utils import get_item_names
from price_differences import get_prices_from_station
import influxdb_client
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS


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
        
        print("Sell orders:")
        print(str(sell_orders_f))
        print("Buy orders:")
        print(str(buy_orders_f))
        return sell_order_total_value, buy_order_total_value
    else:
        print ("no market orders found")
        return 0,0

    
def get_pageful_of_assets(session, character_assets_url, page):
    print(f"grabbing pageful of assets, page number {page}")
    params = {'page': page}
    response = session.get(character_assets_url, params=params) # TODO why does something around here fail randomly? Add better error reporting.
    #print(f"Response status: {response.status_code}")
    #print(f"Response headers: {response.headers}")
    try:
        response_json = response.json()
        #print(f"Response JSON: {response_json}")
        return response_json
    except Exception as json_error:
        print(f"Error parsing JSON: {json_error}")
        return None

def get_all_assets(session, character_assets_url, pages):
    print(f"task is to get {pages} of assets from {character_assets_url}")
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
        print("Merged DataFrame:")
        print(merged_df)
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
    print("Assets:")
    print(str(merged_asset_df)) #only up to 1000, is this paginated? 
    print(f"Total asset value: {total_asset_value}")
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
        # Multiply the 'runs' column by the 'Jita price' column
        merged_industry_df['total_price'] = merged_industry_df['runs'] * merged_industry_df['Jita price']
        # Calculate the total sum for all rows
        total_sum = merged_industry_df['total_price'].sum()
        print(f"Total industry job outputs: {total_sum}")
        return total_sum
    else:
        print ("no industry jobs found")
        return 0
    

def get_character_wallet():
    character_wallet_url = f'https://esi.evetech.net/latest/characters/{character_id}/wallet/'
    character_wallet_response = sso_session.get(character_wallet_url)
    character_wallet_data = character_wallet_response.json()
    print("Wallet balance:")
    print(character_wallet_data)
    return character_wallet_data

def get_jita_prices():
    prices_dataframe = pd.DataFrame()
    jita_prices = get_prices_from_station("Jita", "sell", True) #set False to get updated prices
    prices_dataframe['Jita price'] = jita_prices
    print("Jita price data downloaded")
    #print(str(prices_dataframe))
    return prices_dataframe

def get_average_prices():
    avg_prices_url = f"https://esi.evetech.net/latest/markets/prices/?datasource=tranquility"
    avg_prices_response = sso_session.get(avg_prices_url)
    avg_prices_data = avg_prices_response.json()
    avg_prices_dataframe = pd.DataFrame(avg_prices_data)
    avg_prices_dataframe.set_index('type_id', inplace=True)
    print(str(avg_prices_dataframe))
    return avg_prices_dataframe

def create_summary_dataframe(character_id, character_name, character_wallet_balance, character_asset_value, character_industry_value, character_sell_order_value, character_buy_order_value):
    data = {'character_id': [character_id], 
            'character_name': [character_name], 
            'character_wallet_balance': [character_wallet_balance], 
            'character_asset_value': [character_asset_value], 
            'character_industry_value': [character_industry_value],
            'character_sell_order_value': [character_sell_order_value],
            'character_buy_order_value': [float(character_buy_order_value)],
            }
    
    point = (
        Point("character_data")
        .tag("character_id", character_id)
        .tag("character_name", character_name)
        .field("character_wallet_balance", character_wallet_balance)
        .field("character_asset_value", character_asset_value)
        .field("character_industry_value", float(character_industry_value))
        .field("character_sell_order_value", float(character_sell_order_value))
        .field("character_buy_order_value", float(character_buy_order_value))
    )
    
    summary_dataframe = pd.DataFrame(data)
    print(str(summary_dataframe))
    return (point)

def write_to_influxdb():
    def read_influxdb_settings(file_path='influxdb_settings.txt'):
        keys = {}
        try:
            with open(file_path, 'r') as file:
                for line in file:
                    key, value = line.strip().split('===')
                    keys[key] = value
            return keys
        except FileNotFoundError:
            print(f"File '{file_path}' not found.")
            return None

    influxdb_settings = read_influxdb_settings()
    if influxdb_settings:
        bucket = influxdb_settings.get('bucket')
        org = influxdb_settings.get('org')
        token = influxdb_settings.get('token')
        url = influxdb_settings.get('url')

        if bucket:
            print("Influxdb settings found, proceeding.")
        else:
            print("Error: missing settings in influxdb_settings.txt")

    client = influxdb_client.InfluxDBClient(
        url = url,
        token = token,
        org = org
    )
    point = create_summary_dataframe(character_id, character_name, character_wallet_balance, character_asset_value, character_industry_value, character_sell_order_value, character_buy_order_value)
    
    write_api = client.write_api(write_options=SYNCHRONOUS)
    write_api.write(bucket=bucket, org=org, record=point)
    
def rotate_all_sessions():
    sessions_directory_stats = 'sessions_stats'
    session_files = [f for f in os.listdir(sessions_directory_stats) if f.endswith('.json')]
    print (session_files)
    #sso_session = sso_utils.temp_test_oauth_session()

    for session_file in session_files:
        global character_id, character_name, prices_dataframe, avg_prices_dataframe, character_sell_order_value, character_buy_order_value, character_asset_value, character_industry_value, character_wallet_balance
        print ("Using session file", session_file)
        cycle_sso(session_file)
        character_id = sso_utils.get_character_id(sso_session)
        character_name = sso_utils.get_character(sso_session)
        print(f'SSO Status: {f"Logged in as {character_name}" if character_name else "Not logged in"}')
        prices_dataframe = get_jita_prices() #TODO: only get live prices on the first round around and use cache for next ones
        avg_prices_dataframe = get_average_prices()

        character_sell_order_value, character_buy_order_value = get_character_orders()
        character_asset_value = get_character_assets(avg_prices_dataframe)
        character_industry_value = get_character_industry_jobs(prices_dataframe)
        character_wallet_balance = get_character_wallet()
        write_to_influxdb()

rotate_all_sessions()

# other data to get:
# plex wallet (is it possible?)
# implants
# wallet transactions to track most traded items etc



