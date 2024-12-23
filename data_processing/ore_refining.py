import pandas as pd
import yaml
import json
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()
db_user = os.getenv("mysql_user")
db_password = os.getenv("mysql_password")
db_host = os.getenv("mysql_host")
db_database = os.getenv("mysql_database")

def get_asteroid_groups():
    with open('static/groupIDs.yaml', 'r', encoding='utf-8') as file:
        groupIDs = yaml.safe_load(file)
    groups_data = []
    for group, details in groupIDs.items():
        groups_data.append({
            'groupID': group,
            'categoryID': details['categoryID'],
            'name': details['name']['en'] if 'name' in details and 'en' in details['name'] else None
        })
    groups_df = pd.DataFrame(groups_data)

    asteroid_groups = groups_df.loc[groups_df['categoryID'] == 25, 'groupID'].tolist()
    return asteroid_groups


def generate_refined_values(prices_dataframe):
    
    asteroid_groups = get_asteroid_groups()
    try:
        with open('static/typeMaterials.json', 'r') as file:
            print("loading typeMaterials from json into memory...")
            typeMaterials = json.load(file)

        with open('static/typeIDs.json', 'r') as file:
            print("loading typeIDs from json into memory...")
            typeIDs = json.load(file)
    except FileNotFoundError:
        # If the JSON files don't exist, load the YAML files and convert them to JSON
        with open('static/typeMaterials.yaml', 'r', encoding='utf-8') as file:
            print("loading typeMaterials from yaml into memory...")
            typeMaterials = yaml.safe_load(file)
        with open('static/typeIDs.yaml', 'r', encoding='utf-8') as file:
            print("loading typeIDs from yaml into memory. This may take few minutes on the first run...") 
            typeIDs = yaml.safe_load(file)

        # Save the data as JSON for faster loading next time
        with open('static/typeMaterials.json', 'w') as file:
            json.dump(typeMaterials, file)
        with open('static/typeIDs.json', 'w') as file:
            json.dump(typeIDs, file)

    materials_data = []
    print("processing materials_data...")
    for type_id, materials in typeMaterials.items():
        for material in materials['materials']:
            materials_data.append({
                'type_id': type_id,
                'materialTypeID': material['materialTypeID'],
                'quantity': material['quantity']
            })
    materials_df = pd.DataFrame(materials_data)

    type_ids_data = []
    print("processing type_ids_data...")
    for type_id, details in typeIDs.items():
        type_ids_data.append({
            'type_id': type_id,
            'groupID': details['groupID'],
            'marketGroupID': details.get('marketGroupID'),
            'volume': details.get('volume'),
            'portionSize': details.get('portionSize'),
            'name': details['name']['en']
        })
    type_ids_df = pd.DataFrame(type_ids_data)

    # Merge the dataframes
    df = pd.merge(materials_df, type_ids_df, on='type_id')

    # Get price for every materialTypeID from prices_dataframe
    df = df.merge(prices_dataframe, left_on='materialTypeID', right_index=True)

    # Calculate reprocessed_value
    df['reprocessed_value'] = df['quantity'] * df['price']
    df['reprocessed_value'] = df['reprocessed_value'] / df['portionSize']
    def adjust_reprocessed_value(row):
        if row['groupID'] in asteroid_groups:
            return row['reprocessed_value'] * 0.9 # 90% efficiency for ores
        else:
            return row['reprocessed_value'] * 0.5 # 50% for everything else

    df['reprocessed_value'] = df.apply(adjust_reprocessed_value, axis=1)

    df['type_id'] = df['type_id'].astype(int)
    df['groupID'] = df['groupID'].astype(int)

    # separate dataframe for reprocessed values per type
    reprocessed_value_df = df.groupby('type_id')['reprocessed_value'].sum().reset_index()
    name_df = df[['type_id', 'name']].drop_duplicates()
    reprocessed_value_df = pd.merge(reprocessed_value_df, name_df, on='type_id')


    engine = create_engine(f'mysql+pymysql://{db_user}:{db_password}@{db_host}/{db_database}')
    reprocessed_value_df.to_sql('refined_value', con=engine, if_exists='replace', index=False)


#generate_refined_values()