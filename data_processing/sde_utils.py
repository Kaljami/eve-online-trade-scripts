import os
import pickle
import pandas as pd
import yaml
import json
from sqlalchemy import create_engine
from dotenv import load_dotenv

## These functions work for accessing static data from the SDE, which was imported by data_retrieval/static_data_import.py

def db_connection():
    load_dotenv()
    db_user = os.getenv("mysql_user")
    db_password = os.getenv("mysql_password")
    db_host = os.getenv("mysql_host")
    db_database = os.getenv("mysql_database_fuzzworks")
    engine = create_engine(f'mysql+pymysql://{db_user}:{db_password}@{db_host}/{db_database}')
    return engine

def get_item_names():
    query = f'SELECT typeID, typeName FROM invTypes WHERE published = 1;'
    engine = db_connection()
    df = pd.read_sql_query(query, con=engine)
    dict_df = df.set_index('typeID').to_dict()['typeName']
    return dict_df

def get_type_ids():
    query = f'SELECT typeName, typeID FROM invTypes WHERE published = 1;'
    engine = db_connection()
    df = pd.read_sql_query(query, con=engine)
    dict_df = df.set_index('typeName').to_dict()['typeID']
    return dict_df

def get_item_sizes():
    with open(os.path.join('static', 'sde_sizes.pkl'), 'rb') as fp:
        return pickle.load(fp)

def generate_packaged_volumes():
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