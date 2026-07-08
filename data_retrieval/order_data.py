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
from data_retrieval.sso_utils import reuse_oauth_session
from data_processing.sde_utils import get_item_names
from data_retrieval.update_contract_database import update_contract_status
import logging
import data_retrieval.historical_data as historical_data


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
    load_attempts = 0
    while load_attempts < 10: 
        print(f'Loading {order_type} orders from {station_name} using {"cached data" if cached else "ESI"}. Attempt {load_attempts+1}...')
        orders_json = get_all_orders(station_name, order_type, cached, sso_session)
        #print ("get_prices_from_station says: orders_json:",str(orders_json))
        # This sometimes fails for unknown reason. 
        try:
            print(f'Got {len(orders_json)} orders!')
            break
        except Exception as e:
            print(f"Loading prices from station {station_name} failed. Error:\n {e}")
            load_attempts += 1

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
    #sprint (str(result_df))
    return result_df

def get_num_pages(region_id, order_type, sso_session):
    params = {'order_type': order_type}
    
    if region_id == 10000060: # TODO move to separate citadel version 
        structure_id = 1030049082711
        orders_url = f'https://esi.evetech.net/latest/markets/structures/{structure_id}/'
        if sso_session == None:
            raise Exception("Must authenticate with SSO to access market on player structures. Log in with option 6.")
        res = sso_session.get(orders_url, params=params)
    else:
        orders_url = f'https://esi.evetech.net/latest/markets/{region_id}/orders/'
        res = requests.get(orders_url, params=params)

    #print('request url: ' + res)
    #print(f"Json: {res.json()} Headers: {res.headers}")
    #print("pages:",int(res.headers['X-Pages']))

    return int(res.headers['X-Pages'])

def get_num_pages_citadel(structure_id, order_type, sso_session):
    params = {'order_type': order_type}
    
    orders_url = f'https://esi.evetech.net/latest/markets/structures/{structure_id}/'
    if sso_session == None:
        raise Exception("Must authenticate with SSO to access market on player structures. Log in with option 6.")
    res = sso_session.get(orders_url, params=params)

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
        try:
            if len(all_orders) > 1: # don't save to redis if getting prices was unsuccessful. This might fail because of type error...
                save_orders_to_cache(system_name, all_orders, order_type)
        except:
            print(f"Looks like getting {system_name} {order_type} orders failed. Not saving to Redis. ")
        return all_orders



def get_all_orders_concurrent(system_name, order_type, sso_session):
    #Master function to control async loop and process results
    sso_file = os.getenv("default_character_session_file")
    print(f'Loading {system_name} {order_type} orders using sso_file {sso_file}...')
    names_to_id = {'Amarr': 10000043, 'Jita': 10000002, 'Dodixie': 10000032, 'Rens': 10000030, 'Hek': 10000042, '1DQ1-A': 10000061, 'Tenerifis': 10000060}
    names_to_stn = {'Amarr': 60008494, 'Jita': 60003760, 'Dodixie': 60011866, 'Rens': 60004588, 'Hek': 60005686, '1DQ1-A': 1030049082711, 'Tenerifis': 1046664001931}


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
        
    if region_id == 10000002: # In The Forge, get prices from Jita + Perimeter citadels
        sso_session = reuse_oauth_session(sso_file)
        print("Getting orders from Jita and Perimeter citadels")
        perimeter_citadels = [1042508032148, 1044752365771] # structure ID's to look for market orders. 
        all_orders = []
        for citadel in perimeter_citadels:
            print(f"Getting orders from citadel {citadel}")
            pages = get_num_pages_citadel(citadel, order_type, sso_session)
            citadel_orders = citadel_get_all_orders(citadel, pages, order_type, sso_session)
            if order_type == "sell":
                citadel_orders_filtered = [order for order in citadel_orders if not order["is_buy_order"]]
            if order_type == "buy":
                citadel_orders_filtered = [order for order in citadel_orders if order["is_buy_order"]]
            all_orders = all_orders + citadel_orders_filtered
            print(f"Orders from citadel {citadel} added to Jita orders")
        loop = asyncio.get_event_loop()
        pages = get_num_pages(region_id, order_type, sso_session)
        try:
            if order_type == "sell":
                sell_orders_jita = loop.run_until_complete(async_get_all_orders(region_id, pages, order_type))
                output_jita = [order for page in sell_orders_jita for order in page if order.get('location_id', 0) == station_id] # TODO this should not be necessary
                all_orders = all_orders + output_jita
                return all_orders
            
            if order_type == "buy":
                buy_orders_jita = loop.run_until_complete(async_get_all_orders(region_id, pages, order_type))
                output_jita = [order for page in buy_orders_jita for order in page if order.get('location_id', 0) == station_id] # TODO this should not be necessary
                all_orders = all_orders + output_jita
                return all_orders
        except Exception as e:
            print (e)


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

def update_metadata(prices=False, blueprints=False, expired_contracts=False, appraisal_prices=False):
    current_timestamp = datetime.now()
    if prices:
        redis_key = 'price_cache_updated'
    if blueprints:
        redis_key = 'blueprint_values_updated'
    if expired_contracts:
        redis_key = 'expired_contracts_checked'
    if appraisal_prices:
        redis_key = 'appraisal_prices_updated'
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
        #this might need some more thought on error handling
#        try:
            print("it's time to update prices!")
            logging.info("Starting to update price caches")
            sso_session = reuse_oauth_session(sso_file)
            locations = ['Jita', 'Amarr', 'Tenerifis', 'Dodixie']
            types = ['buy', 'sell']

            for location in locations:
                try:
                    for order_type in types:
                        print(f"Loading prices from location: {location}, Type: {order_type}")
                        logging.info(f"Loading prices from location: {location}, Type: {order_type}")
                        get_all_orders(location, order_type, False, sso_session)
                except Exception as e:
                    logging.error(f"Failed loading prices from location: {location}, Type: {order_type}. Error: {e}")
            get_average_prices(False)
            update_metadata(prices=True)
            update_appraisal_prices()
            update_metadata(appraisal_prices=True)
            update_contract_status() # todo give this a separate update frequency
#        except Exception as e:
#            print(f"Error while running the cache update (in order_data.py): \n {e.with_traceback}")
#            logging.error(f"Error while running the cache update (in order_data.py): \n {e.with_traceback}")
    else:
        print(f"it's been {time_since_prices} since prices were updated")

    time_since_blueprints = check_metadata('blueprints')
    if time_since_blueprints > timedelta(hours=24) or force == True:
        print("it's time to update blueprints!")
        update_blueprint_values()
        update_metadata(blueprints=True)
    else:
        print(f"it's been {time_since_blueprints} since blueprint values were updated")

# This is here because I got stuck in circular imports 😭
# TODO maybe automate downloading new SDE versions from https://www.fuzzwork.co.uk/dump/latest/
def update_blueprint_values():

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


def update_appraisal_prices():
    locations_cached = False # market orders were already fetched previously
    print("Starting update_appraisal_prices ----------")
    sso_file = os.getenv("default_character_session_file")
    sso_session = reuse_oauth_session(sso_file)
    for order_type in ['sell', 'buy']:
        jita_sell_df = get_market_prices('Jita', order_type, locations_cached)
        amarr_sell_df = get_market_prices('Amarr', order_type, locations_cached)
        #tenerifis_sell_df = get_market_prices('Tenerifis', order_type, locations_cached, sso_session)
        dodixie_sell_df = get_market_prices('Dodixie', order_type, locations_cached)
        
        
        # TODO add dodixie and selection for locations
        print("Calculating best prices...")
        # List of DataFrames
        sell_dfs = [jita_sell_df, amarr_sell_df, dodixie_sell_df]
        # Combine DataFrames based on 'type_id'
        combined_df = pd.concat(sell_dfs)
        combined_df.reset_index(inplace=True) # Reset index to ensure type_id becomes a column
        
        agg_df = combined_df.groupby('type_id').apply(lambda x: pd.Series({
            'min_price': x['price'].min(),
            'min_price_location': x.loc[x['price'].idxmin(), 'location'],
            'min_price_volume': x.loc[x['price'].idxmin(), 'daily_volume'],
            'max_price': x['price'].max(),
            'max_price_location': x.loc[x['price'].idxmax(), 'location'],
            'max_price_volume': x.loc[x['price'].idxmax(), 'daily_volume']
        }))
        #print(agg_df)
        # Extract prices from original dataframes and add them to the aggregated dataframe
        agg_df['price_amarr'] = agg_df.index.map(lambda x: amarr_sell_df.loc[x, 'price'] if x in amarr_sell_df.index else None)
        agg_df['price_jita'] = agg_df.index.map(lambda x: jita_sell_df.loc[x, 'price'] if x in jita_sell_df.index else None)
        agg_df['price_dodixie'] = agg_df.index.map(lambda x: dodixie_sell_df.loc[x, 'price'] if x in dodixie_sell_df.index else None)
        
        cache_key = f'best_prices_{order_type}'
        print(f"Saving best_prices_{order_type} to redis cache. Result df was: \n{agg_df}")
        
        save_to_cache(cache_key, agg_df)

def get_market_prices(station_name, order_type, cached, sso_session=None):
    prices_dataframe = pd.DataFrame()
    market_prices = get_prices_from_station(station_name, order_type, cached, sso_session) #set False to get updated prices
    prices_dataframe['price'] = market_prices
    prices_dataframe['location'] = station_name
    if cached == False:
        print(f"Fresh {station_name} {order_type} order price data downloaded")

    historical_volume, historical_price, order_count = get_volume_price_history(station_name, prices_dataframe.index, 7, False)
    prices_dataframe = prices_dataframe.merge(historical_volume.rename('daily_volume'), how='left', left_on='type_id', right_index=True)
    return prices_dataframe

def save_to_cache(cache_key, variable): # Save to redis, and pickle for redundancy
    try:
        print(f"Saving {cache_key} orders to redis cache")
        redis_client = redis_connection()
        
        redis_client.set(cache_key, pickle.dumps(variable)) # Cache the data in Redis
        with open(os.path.join('cache', f'{cache_key}.pkl'), 'wb') as fp:
            pickle.dump(variable, fp)
    except Exception as e:
        print("error while saving cache to redis:", e, "Saving only as pickle")
        pickle_file = cache_key
        with open(os.path.join('cache', f'{pickle_file}.pkl'), 'wb') as fp:
            pickle.dump(variable, fp)


def get_volume_price_history(station_name, typeIDs, days, cached) -> tuple[pd.Series]:
    """Get historical data for each given typeID"""

    idx = pd.IndexSlice

    print(f'Loading market history in {station_name} for {len(typeIDs)} items...')
    history_json = historical_data.get_all_history(station_name, typeIDs, cached=cached)
    print('Success!')

    print(f'Processing history content into dataframe...')
    typeID_history_dict = {
        typeID: pd.DataFrame.from_records(data, index=['date'])
        for typeID, data
        in history_json.items()
    }

    historical_df = pd.concat(typeID_history_dict, axis=1).T
    #print(historical_df)
    if 'date' in historical_df.columns:
        historical_df = historical_df.drop('date', axis='columns')
    historical_df.columns = pd.to_datetime(historical_df.columns, yearfirst=True)
    print('Done!')

    print(f'Pulling out historical volume data for {days} days...')
    v = historical_df.loc[idx[:, 'volume'], historical_df.columns > (pd.Timestamp('today').floor('D') - pd.offsets.Day(int(days)))]
    #print(v)
    v = v.fillna(0).mean(axis=1)
    """ FYI TODO
    FutureWarning: Downcasting object dtype arrays on .fillna, .ffill, .bfill is deprecated and will change in a future version. Call result.infer_objects(copy=False) instead. To opt-in to the future behavior, set `pd.set_option('future.no_silent_downcasting', True)`
    v = v.fillna(0).mean(axis=1)
    """
    v = v.droplevel(1, axis=0)

    print(f'Pulling out historical price data for {days} days...')
    p = historical_df.loc[idx[:, 'average'], historical_df.columns > (pd.Timestamp('today').floor('D') - pd.offsets.Day(int(days)))]
    p = p.mean(axis=1)
    p = p.droplevel(1, axis=0)

    print(f'Pulling out historical order count data for {days} days...')
    order_count = historical_df.loc[idx[:, 'order_count'], historical_df.columns > (pd.Timestamp('today').floor('D') - pd.offsets.Day(int(days)))]
    order_count = order_count.mean(axis=1)
    order_count = order_count.droplevel(1, axis=0)

    print('Done!')
    return v, p, order_count