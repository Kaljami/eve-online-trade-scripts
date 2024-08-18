import pandas as pd
import yaml
import json
import pickle
import os

# TODO: update to work with data from mysql

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

### This ended up being useless since loading all the blueprints is just as fast

import pickle
# First, get groups for blueprints to be checked
def get_blueprint_groups(search_term):
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

    blueprint_groups_df = groups_df.loc[groups_df['categoryID'] == 9] # 9 is blueprints
    #print(blueprint_groups_df)
    ancillary_blueprint_groups_df = blueprint_groups_df.loc[blueprint_groups_df['name'].str.contains(search_term)]
    #print(ancillary_blueprint_groups_df)
    ancillary_blueprint_groups = ancillary_blueprint_groups_df.loc[groups_df['categoryID'] == 9, 'groupID'].tolist()
    return ancillary_blueprint_groups

def get_all_blueprint_groups():
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

    blueprint_groups_df = groups_df.loc[groups_df['categoryID'] == 9] # 9 is blueprints
    #print(blueprint_groups_df)
    #print(ancillary_blueprint_groups_df)
    blueprint_groups = blueprint_groups_df.loc[groups_df['categoryID'] == 9, 'groupID'].tolist()
    return blueprint_groups

def get_blueprint_type_ids(search_terms): 
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

    blueprint_groups = get_all_blueprint_groups()
    blueprint_type_ids = []
    blueprint_type_names = []

    print("Processing types...")
    for type_id, data in types.items():
        try:
            group_id = data.get('group_id', None)
            type_name = data.get('name', None)
            if group_id in blueprint_groups:
                for term in search_terms:
                    if '*' in term:
                        wildcard_term = term.split('*')
                        if type_name.startswith(wildcard_term[0]) and type_name.endswith(wildcard_term[1]):
                        #if wildcard_term.lower() in type_name.lower():
                            blueprint_type_ids.append(int(type_id))
                            blueprint_type_names.append(type_name)
                    else:
                        if term.lower() in type_name.lower():
                            blueprint_type_ids.append(int(type_id))
                            blueprint_type_names.append(type_name)

        except Exception as e:
            print(f"Error when processing type_id {type_id}: {e}")
    blueprint_df = pd.DataFrame({'type_id': blueprint_type_ids, 'type_name': blueprint_type_names})
    print("These blueprints matched the search terms:\n",blueprint_df)

    with open(os.path.join('cache', 'interesting_blueprint_type_ids.pkl'), 'wb') as file: 
            pickle.dump(blueprint_type_ids, file)
            print("interesting_blueprint_type_ids saved as cache/interesting_blueprint_type_ids.pkl")

    return blueprint_type_ids

def get_all_blueprint_type_ids(): 
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

    blueprint_groups = get_all_blueprint_groups()
    blueprint_type_ids = []
    blueprint_type_names = []

    print("Processing types...")
    for type_id, data in types.items():
        try:
            group_id = data.get('group_id', None)
            type_name = data.get('name', None)
            if group_id in blueprint_groups:
                blueprint_type_ids.append(int(type_id))
                blueprint_type_names.append(type_name)

        except Exception as e:
            print(f"Error when processing type_id {type_id}: {e}")
    blueprint_df = pd.DataFrame({'type_id': blueprint_type_ids, 'type_name': blueprint_type_names})
    print("These blueprints matched the search terms:\n",blueprint_df)

    with open(os.path.join('cache', 'all_blueprint_type_ids.pkl'), 'wb') as file: 
            pickle.dump(blueprint_type_ids, file)
            print("all_blueprint_type_ids saved as cache/all_blueprint_type_ids.pkl")

    return blueprint_type_ids