import os
import pickle
import pandas as pd
import yaml
import json
from sqlalchemy import create_engine, MetaData, Table
from dotenv import load_dotenv
import redis

## These functions work for accessing and manipulating static data from the SDE, which was imported by data_retrieval/static_data_import.py

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

def save_to_redis(variable, cache_key):
    try:
        redis_client = redis_connection()
        redis_client.set(cache_key, pickle.dumps(variable)) # Cache the data in Redis
        print(f"Saved {cache_key} to redis cache")
        with open(os.path.join('cache', f'{cache_key}.pkl'), 'wb') as fp:
            pickle.dump(variable, fp)
        print(f"And saved {cache_key} to pickle")

    except Exception as e:
        with open(os.path.join('cache', f'{cache_key}.pkl'), 'wb') as fp:
            pickle.dump(variable, fp)
        print(f"Error while saving {cache_key} to redis: {e}. Saving only as pickle")

def load_from_redis(cache_key):
    redis_client = redis_connection()
    cached_data = redis_client.get(cache_key)
    if cached_data:
        #print (f"Getting {cache_key} from redis cache")
        return pickle.loads(cached_data)
    else:
        print (f"No data found in redis for key {cache_key}. Trying to load from pickle...")
        cache_file = os.path.join('cache', f'{cache_key}.pkl')
        with open(cache_file, 'rb') as fp:
            return pickle.load(fp)

def get_item_names():
    query = f'SELECT typeID, typeName FROM invTypes;'
    engine = db_connection(fuzz=True)
    df = pd.read_sql_query(query, con=engine)
    dict_df = df.set_index('typeID').to_dict()['typeName']
    return dict_df

def get_type_ids():
    query = f'SELECT typeName, typeID FROM invTypes WHERE published = 1;'
    engine = db_connection(fuzz=True)
    df = pd.read_sql_query(query, con=engine)
    dict_df = df.set_index('typeName').to_dict()['typeID']
    return dict_df

def get_item_sizes(): # TODO update to read from database
    with open(os.path.join('static', 'sde_sizes.pkl'), 'rb') as fp:
        return pickle.load(fp)
    
def get_region_ids():
    region_ids = load_from_redis('region_ids')
    return region_ids

def get_system_ids():
    system_ids = load_from_redis('system_ids')
    return system_ids
get_system_ids()

def generate_packaged_volumes(): # TODO update to read from database
    try:
        with open('static/types.en-us.json', 'r') as file:
            print("loading types from json into memory...")
            types = json.load(file)

    except FileNotFoundError:
        # If the JSON files don't exist, load the YAML files and convert them to JSON
        with open('static/types.en-us.yaml', 'r', encoding='utf-8') as file:
            print("loading types from yaml into memory...")
            types = yaml.safe_load(file)

        # Save the data as JSON for faster loading next time
        with open('static/types.en-us.json', 'w') as file:
            json.dump(types, file)

    packaged_volumes = []
    print("processing packaged_volumes...")
    for type_id, data in types.items():
        try:
            # Extract packaged volume for each type
            packaged_volume = data.get('packaged_volume', None)
            if packaged_volume is not None:
                packaged_volumes.append({
                    'type_id': type_id,
                    'packaged_volume': packaged_volume
                })
        except Exception as e:
            print(f"Error when processing type_id {type_id}: {e}")

    packaged_volumes_df = pd.DataFrame(packaged_volumes)
    packaged_volumes_dfm = packaged_volumes_df.set_index('type_id')
    print(packaged_volumes_df)
    print(packaged_volumes_dfm)
    dictionary = packaged_volumes_dfm.to_dict()
    print(dictionary)
    with open("static/types_packaged_volumes.json", 'w') as file:
        json.dump(dictionary, file)

def generate_region_ids():
    engine = db_connection(fuzz=True)
    metadata = MetaData()
    map_regions_table = Table('mapRegions', metadata, autoload_with=engine)

    with engine.connect() as connection:
        query = connection.execute(
            map_regions_table.select()
            .with_only_columns(
                map_regions_table.c.regionName, 
                map_regions_table.c.regionID
            )
        )

        # Construct dictionary from the query result
        region_dict = {row.regionName: row.regionID for row in query}
    print("Region dictionary created")
    # Save the dictionary to redis
    save_to_redis(region_dict, 'region_ids')

def generate_system_ids():
    engine = db_connection(fuzz=True)
    metadata = MetaData()
    table = Table('mapSolarSystems', metadata, autoload_with=engine)

    with engine.connect() as connection:
        query = connection.execute(
            table.select()
            .with_only_columns(
                table.c.solarSystemName, 
                table.c.solarSystemID
            )
        )

        # Construct dictionary from the query result
        system_dict = {row.solarSystemName: row.solarSystemID for row in query}
    print("System id dictionary created")
    # Save the dictionary to redis
    save_to_redis(system_dict, 'system_ids')