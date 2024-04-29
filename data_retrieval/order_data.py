import os
import pickle
import aiohttp
import asyncio
import requests
import pandas as pd
import json
from dotenv import load_dotenv
from sqlalchemy import create_engine
import redis
from tqdm import tqdm
from datetime import datetime, timezone, timedelta
from data_retrieval.sso_utils import temp_test_oauth_session
from data_processing.sde_utils import get_item_names
import logging
logging.basicConfig(filename='logs/general.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def db_connection(fuzz=False):
    load_dotenv()
    db_user = os.getenv("mysql_user")
    db_password = os.getenv("mysql_password")
    db_host = os.getenv("mysql_host")
    if fuzz:
        db_database = os.getenv("mysql_database_fuzzworks")
    else:
        db_database = os.getenv("mysql_database")
    engine = create_engine(f'mysql+pymysql://{db_user}:{db_password}@{db_host}/{db_database}')
    return engine

def redis_connection():
    load_dotenv()
    redis_host = os.getenv("redis_host")
    redis_client = redis.Redis(host=redis_host, port=6379, db=0)
    return redis_client

def get_prices_from_station(station_name, order_type, cached, sso_session=None) -> pd.Series:
    # Get orders as JSON
    print(f'Loading {order_type} orders from {station_name} using {"cached data" if cached else "ESI"}...')
    orders_json = get_all_orders(station_name, order_type, cached, sso_session)
    #print ("get_prices_from_station says: orders_json:",str(orders_json))
    # This sometimes fails for unknown reason. 
    print(f'Got {len(orders_json)} orders!')

    # Convert to DF and find the best price for each typeID
    df = pd.DataFrame.from_records(orders_json)
    #print(df)
    if order_type == "sell":
        return df.groupby('type_id')['price'].min()  # pd.Series
    if order_type == "buy":
        return df.groupby('type_id')['price'].max()  # pd.Series
    
def get_ungrouped_prices_from_station(station_name, order_type, cached, sso_session=None) -> pd.Series:
    # Get orders as JSON. Keep all the orders instead of only the best price available. 
    print(f'Loading {order_type} orders from {station_name} using {"cached data" if cached else "ESI"}...')
    orders_json = get_all_orders(station_name, order_type, cached, sso_session) #this could as well be always cached if it's always called alongside with get_prices_from_station
    print(f'Got {len(orders_json)} orders!')

    # Convert to DF
    df = pd.DataFrame.from_records(orders_json)
    result_df = df.copy()
    print (str(result_df))
    return result_df

def get_num_pages(region_id, order_type, sso_session):
    params = {'order_type': order_type}
    
    if region_id == 10000060:
        structure_id = 1030049082711
        orders_url = f'https://esi.evetech.net/latest/markets/structures/{structure_id}/'
        if sso_session == None:
            raise Exception("Must authenticate with SSO to access market on player structures.")
        res = sso_session.get(orders_url, params=params)
    else:
        orders_url = f'https://esi.evetech.net/latest/markets/{region_id}/orders/'
        res = requests.get(orders_url, params=params)

    #print('request url: ' + res)
    #print(f"Json: {res.json()} Headers: {res.headers}")
    #print("pages:",int(res.headers['X-Pages']))

    return int(res.headers['X-Pages'])


def citadel_get_page(structure_id, page, order_type, sso_session):
    orders_url = f'https://esi.evetech.net/latest/markets/structures/{structure_id}/'
    params = {
        'page': page,
        'order_type': order_type
    }
    res = sso_session.get(orders_url, params=params)
    res.raise_for_status()
    return res.json()

async def get_page(session, region_id, page, order_type):
    orders_url = f'https://esi.evetech.net/latest/markets/{region_id}/orders/'
    params = {
        'page': page,
        'order_type': order_type
    }
    res = await session.get(orders_url, params=params)
    return await res.json()

def citadel_get_all_orders(station_id, pages, order_type, sso_session):
    orders = []
    for page in tqdm(range(1, pages + 1), desc='Loading orders', unit="pages", total=pages):
        page_orders = citadel_get_page(station_id, page, order_type, sso_session)
        orders.extend(page_orders)
    return orders

async def async_get_all_orders(region_id, pages, order_type):

    async with aiohttp.ClientSession() as session:
        tasks = [
            get_page(session, region_id, page, order_type)
            for page in
            range(1, pages + 1)
        ]
        return await asyncio.gather(*tasks)

def get_all_orders(system_name, order_type, cached, sso_session):
    if cached == True:
        return get_orders_from_cache(system_name, order_type)
    else:
        all_orders = get_all_orders_concurrent(system_name, order_type, sso_session)
        save_orders_to_cache(system_name, all_orders, order_type)
        return all_orders



def get_all_orders_concurrent(system_name, order_type, sso_session):
    #Master function to control async loop and process results

    names_to_id = {'Amarr': 10000043, 'Jita': 10000002, 'Dodixie': 10000032, 'Rens': 10000030, 'Hek': 10000042, '1DQ1-A': 10000060}
    names_to_stn = {'Amarr': 60008494, 'Jita': 60003760, 'Dodixie': 60011866, 'Rens': 60004588, 'Hek': 60005686, '1DQ1-A': 1030049082711}

    region_id = names_to_id[system_name]
    station_id = names_to_stn[system_name]

    pages = get_num_pages(region_id, order_type, sso_session)
    if region_id == 10000060:
        all_orders = citadel_get_all_orders(station_id, pages, order_type, sso_session) # If looking for orders in player-owned structures we need an SSO login with access to the structure
        if order_type == "sell":
            sell_orders = [order for order in all_orders if not order["is_buy_order"]]
            return sell_orders
        if order_type == "buy":
            buy_orders = [order for order in all_orders if order["is_buy_order"]]
            return buy_orders
        
    else:
        loop = asyncio.get_event_loop()
        try:
            if order_type == "sell":
                sell_orders = loop.run_until_complete(async_get_all_orders(region_id, pages, order_type))
                output = [order for page in sell_orders for order in page if order.get('location_id', 0) == station_id]
                return output
            
            if order_type == "buy":
                buy_orders = loop.run_until_complete(async_get_all_orders(region_id, pages, order_type))
                return [order for page in buy_orders for order in page if order.get('location_id', 0) == station_id]
        except Exception as e:
            print (e)


def save_orders_to_cache(system_name, orders, order_type): # Save to redis, and pickle for redundancy
    cache_key = f'orders_{system_name}_{order_type}'
    try:
        print(f"Saving {system_name} {order_type} orders to redis cache")
        redis_client = redis_connection()
        
        redis_client.set(cache_key, pickle.dumps(orders)) # Cache the data in Redis
        with open(os.path.join('cache', f'{cache_key}.pkl'), 'wb') as fp:
            pickle.dump(orders, fp)
    except Exception as e:
        print("error while saving cache to redis:", e, "Saving only as pickle")
        pickle_file = cache_key
        with open(os.path.join('cache', f'{pickle_file}.pkl'), 'wb') as fp:
            pickle.dump(orders, fp)

def get_orders_from_cache(system_name, order_type):
    redis_client = redis_connection()
    cache_key = f'orders_{system_name}_{order_type}'
    cached_data = redis_client.get(cache_key)
    if cached_data:
        print (f"Getting {system_name} {order_type} orders from redis cache")
        return pickle.loads(cached_data)
    else:
        print (f"That failed. Getting {system_name} {order_type} orders from local pickle file as last resort")
        cache_file = os.path.join('cache', f'{system_name}_orders_{order_type}.pkl')
        with open(cache_file, 'rb') as fp:
            return pickle.load(fp)


def get_average_prices(cached):
    system_name = 'Universe'
    order_type = 'average'
    if cached:
        print (f"Getting {system_name} {order_type} prices from cached data")
        avg_prices_data = get_orders_from_cache(system_name, order_type)
    if not cached:
        print (f"Getting {system_name} {order_type} prices from ESI")
        avg_prices_url = f"https://esi.evetech.net/latest/markets/prices/?datasource=tranquility"
        avg_prices_response = requests.get(avg_prices_url)
        avg_prices_data = avg_prices_response.json()
        save_orders_to_cache(system_name, avg_prices_data, order_type)
    avg_prices_dataframe = pd.DataFrame(avg_prices_data)
    avg_prices_dataframe = avg_prices_dataframe.reindex(columns=['type_id','average_price'])
    avg_prices_dataframe = avg_prices_dataframe.rename(columns={'average_price':'price'})
    avg_prices_dataframe.set_index('type_id', inplace=True)
    #print(str(avg_prices_dataframe))
    return avg_prices_dataframe

def update_metadata(prices=False, blueprints=False, expired_contracts=False):
    current_timestamp = datetime.now()
    if prices:
        redis_key = 'price_cache_updated'
    if blueprints:
        redis_key = 'blueprint_values_updated'
    if expired_contracts:
        redis_key = 'expired_contracts_checked'
    redis_client = redis_connection()
    redis_client.set(redis_key, pickle.dumps(current_timestamp)) # Cache the data in Redis
    print(f"Status updated to redis cache")


def check_metadata(data_type):
    redis_client = redis_connection()
    current_timestamp = datetime.now()
    try:
        if data_type == 'prices':
            cached_data = pickle.loads(redis_client.get('price_cache_updated'))
        if data_type == 'blueprints':
            cached_data = pickle.loads(redis_client.get('blueprint_values_updated'))
        if data_type == 'expired_contracts':
            cached_data = pickle.loads(redis_client.get('expired_contracts_checked'))
        time_since = current_timestamp - cached_data
        return time_since
    except TypeError:
        print(f'No timestamp entry found for last {data_type} update')

def update_caches(force=False):
    load_dotenv()
    sso_file = os.getenv("default_character_session_file")
    time_since_prices = check_metadata('prices')
    if time_since_prices > timedelta(hours=2) or force == True:
        print("it's time to update prices!")
        sso_session = temp_test_oauth_session(sso_file)
        locations = ['Jita', 'Amarr', '1DQ1-A']
        types = ['buy', 'sell']

        for location in locations:
            for order_type in types:
                print(f"Location: {location}, Type: {order_type}")
                get_all_orders(location, order_type, False, sso_session)
        get_average_prices(False)
        update_metadata(prices=True)
    else:
        print(f"it's been {time_since_prices} since prices were updated")

    time_since_blueprints = check_metadata('blueprints')
    if time_since_blueprints > timedelta(hours=24) or force == True:
        print("it's time to update blueprints!")
        update_contract_values()
        update_metadata(blueprints=True)
    else:
        print(f"it's been {time_since_blueprints} since blueprint values were updated")

# This is here because I got stuck in circular imports 😭
def update_contract_values():
    prices_dataframe_sell = get_prices_from_station('Jita','sell', True)
    prices_dataframe_buy = get_prices_from_station('Jita','buy', True)

    engine = db_connection()
    engine_fuzz = db_connection(fuzz=True)

    blueprint_materials_query = "SELECT typeID, activityID, materialTypeID, quantity FROM industryActivityMaterials;"
    blueprint_materials_df = pd.read_sql_query(blueprint_materials_query, con=engine_fuzz)
    blueprint_materials_df = blueprint_materials_df[blueprint_materials_df['activityID']== 1 ] # Only manufacturing jobs
    #blueprint_materials_df = blueprint_materials_df.rename(columns={'typeID':'type_id','activityID':'activity_id'})

    merged_materials_df = blueprint_materials_df.merge(prices_dataframe_sell, left_on='materialTypeID', right_index=True) # use minsell price for input materials
    merged_materials_df['material_price'] = merged_materials_df['quantity'] * merged_materials_df['price']

    print(merged_materials_df)

    grouped_materials_df = merged_materials_df.groupby('typeID')['material_price'].sum().reset_index()
    print(grouped_materials_df)
    #print(grouped_materials_df[grouped_materials_df['typeID'] == 41638])
    print("---products---")
    blueprint_products_query = "SELECT typeID, activityID, productTypeID, quantity FROM industryActivityProducts;"
    blueprint_products_df = pd.read_sql_query(blueprint_products_query, con=engine_fuzz)
    blueprint_products_df = blueprint_products_df[blueprint_products_df['activityID']== 1 ] # Only manufacturing jobs

    merged_products_df = blueprint_products_df.merge(prices_dataframe_buy, left_on='productTypeID', right_index=True) # max jita buy price for outputs
    merged_products_df['product_price'] = merged_products_df['quantity'] * merged_products_df['price']
    print("merged_products_df:\n",merged_products_df)
    grouped_products_df = merged_products_df.groupby('typeID')['product_price'].sum().reset_index()
    print("grouped_products_df:\n",grouped_products_df)
    #print(grouped_products_df[grouped_products_df['typeID'] == 41638])

    blueprint_values_df = grouped_products_df.merge(grouped_materials_df, left_on='typeID',right_on='typeID')
    print("\nblueprint_values_df before merging productTypeID:\n", blueprint_values_df)
    blueprint_values_df = blueprint_values_df.merge(blueprint_products_df[['typeID', 'productTypeID']], on='typeID')
    print("\nblueprint_values_df after merging productTypeID:\n", blueprint_values_df)
    blueprint_values_df = blueprint_values_df.rename(columns={'typeID':'blueprint_type_id','productTypeID':'product_type_id'})
    blueprint_values_df['blueprint_type_name'] = blueprint_values_df['blueprint_type_id'].map(get_item_names())
    blueprint_values_df = blueprint_values_df.reindex(columns=['blueprint_type_id', 'blueprint_type_name', 'material_price', 'product_type_id', 'product_price'])
    blueprint_values_df.set_index('blueprint_type_id', inplace=True)
    blueprint_values_df['blueprint_profit'] = blueprint_values_df['product_price'] - blueprint_values_df['material_price']
    blueprint_values_df['profit_margin'] = blueprint_values_df['blueprint_profit'] / blueprint_values_df['material_price']

    blueprint_values_df.loc[blueprint_values_df['blueprint_profit'] <= 0 , 'blueprint_profit'] = 0


    print("\nfinally, blueprint_values_df:\n", blueprint_values_df)

    try:
        blueprint_values_df.to_sql('blueprint_values', con=engine, if_exists='replace')
        print("Blueprint values dataframe saved to database.")
        logging.info(f"Blueprint values dataframe saved to database.")
    except Exception as e:
        print(e)
        print(f"Error saving blueprint values to database. Aborting.")
        logging.error(f"Error saving blueprint values to database. Aborting. \n{e}")