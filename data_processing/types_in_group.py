import pandas as pd
import yaml
import json
import pickle
import os

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


def get_rig_groups():
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

    ship_module_groups_df = groups_df.loc[groups_df['categoryID'] == 7] # 7 is ship modules
    rig_groups_df = ship_module_groups_df.loc[ship_module_groups_df['name'].str.contains('Rig ')]
    rig_groups = rig_groups_df.loc[groups_df['categoryID'] == 7, 'groupID'].tolist()
    return rig_groups


def get_rig_type_ids():
    try:
        with open(os.path.join('static', 'rig_type_ids.pkl'), 'rb') as file:
            rig_type_ids = pickle.load(file)
            rig_type_ids = [int(x) for x in rig_type_ids] # Loading the pickle turns the values into strings for some reason
            return rig_type_ids
    except FileNotFoundError:
        print("Could not find pre-made list of rig type_ids. Creating a new one.")
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
        rig_groups = get_rig_groups()
        rig_type_ids = []
        print ("Processing types...")
        for type_id, data in types.items():
            try:
                # Extract packaged volume for each type
                group_id = data.get('group_id', None)
                if group_id in rig_groups:
                    rig_type_ids.append(int(type_id))
            except Exception as e:
                print(f"Error when processing type_id {type_id}: {e}")
        
        with open(os.path.join('static', 'rig_type_ids.pkl'), 'wb') as file: 
            pickle.dump(rig_type_ids, file)
            print("rig_type_ids saved as rig_type_ids.pkl")
        return rig_type_ids


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

