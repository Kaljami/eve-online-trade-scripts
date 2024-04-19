import os
import requests
import aiohttp
import asyncio
import pandas as pd
import nest_asyncio
from sqlalchemy import create_engine, inspect
from tqdm import tqdm
from data_retrieval.price_differences import get_prices_from_station
from data_processing.types_in_group import get_rig_type_ids
from datetime import datetime, timezone
from time import sleep
import discord
from discord import Embed
discord.VoiceClient.warn_nacl = False # gets rid of warning in logging
import yaml
import json
import logging
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

### SETTINGS BEGIN

load_dotenv()
# MySQL Database:
db_user = os.getenv("mysql_user")
db_password = os.getenv("mysql_password")
db_host = os.getenv("mysql_host")
db_database = os.getenv("mysql_database")

# Contracts: 
regions = ["The Forge", "Delve", "Domain", "Placid", "Sinq Laison", "Lonetrek", "The Citadel", "Essence", "Querious", "Fountain", "Period Basis", "Aridia"]
minimum_profit_percentage = 15
good_profit_percentage = 30
minimum_profit_absolute = 30000000 # 30 million
good_profit_absolute = 150000000 # 150 million. Send notification if profit is above this treshold even if percentage is lower. 
maximum_volume_br = 13000
maximum_volume_dst = 60000
maximum_volume_freighter = 500000
maximum_volume = maximum_volume_freighter

# Discord:
sender_name = os.getenv("discord_sender_name")
sender_icon_url = os.getenv("discord_sender_icon_url")
discord_webhook_url = os.getenv("discord_webhook_url")
discord_contract_notification_tag_id = os.getenv("discord_contract_notification_tag_id")

### SETTINGS END

logging.basicConfig(filename='logs/contracts_data.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
load_dotenv()
engine = create_engine(f'mysql+pymysql://{db_user}:{db_password}@{db_host}/{db_database}')
intents = discord.Intents.default() 
intents.members = True
intents.message_content = True
client = discord.Client(intents=intents)

def get_num_pages(region_id):
    """Use requests to grab a page of contracts, returning the X-Pages header from the response."""

    contracts_url = f'https://esi.evetech.net/latest/contracts/public/{region_id}/'

    params = {}

    res = requests.get(contracts_url, params=params)

    return int(res.headers['X-Pages'])

async def get_page(session, region_id, page):
    """Async get a page of contracts for a given region."""

    contracts_url = f'https://esi.evetech.net/latest/contracts/public/{region_id}/'

    params = {
        'page': page
    }

    res = await session.get(contracts_url, params=params)
    return await res.json()


async def async_get_all_contracts(region_id, pages):
    """Async get all pages of contracts for a given region."""

    async with aiohttp.ClientSession() as session:
        tasks = [
            get_page(session, region_id, page)
            for page in
            range(1, pages + 1)
        ]

        return await asyncio.gather(*tasks)
    
def get_all_contracts_concurrent(region_name):
    """Master function to control async loop and process results."""

    names_to_id = {'Domain': 10000043, 'The Forge': 10000002, 'Sinq Laison': 10000032, 'Heimatar': 10000030, 'Metropolis': 10000042, 'Delve': 10000060, 'Placid': 10000048, 'Essence': 10000064, 'The Citadel': 10000033, 'Lonetrek': 10000016, 'Querious':10000050, 'Period Basis':10000063, 'Fountain':10000058, 'Aridia':10000054}
    #names_to_stn = {'Amarr': 60008494, 'Jita': 60003760, 'Dodixie': 60011866, 'Rens': 60004588, 'Hek': 60005686, '1DQ-1A': 1030049082711}

    region_id = names_to_id[region_name]
    #station_id = names_to_stn[region_name]

    pages = get_num_pages(region_id)  
    # Fix for Jupyter notebook
    nest_asyncio.apply()

    try:
        loop = asyncio.get_event_loop()
        contracts = loop.run_until_complete(async_get_all_contracts(region_id, pages))
        return [contract for page in contracts for contract in page]
    except Exception as e:
        print(e)


def get_all_contracts(region_name, cached):
    if cached == True:
        print ("we don't have cache for contracts")
    else:
        all_contracts = get_all_contracts_concurrent(region_name)

    return all_contracts

def convert_date_string_to_datetime(date_string):
    # Parse the date string into a datetime object
    date_obj = datetime.strptime(date_string, '%Y-%m-%dT%H:%M:%SZ')
    # Format the datetime object into the desired string format
    formatted_date = date_obj.strftime('%Y-%m-%d %H:%M:%S')
    return formatted_date

def get_jita_prices(cached):
    prices_dataframe = pd.DataFrame()
    jita_prices = get_prices_from_station("Jita", "buy", cached) #set False to get updated prices
    prices_dataframe['jita_price'] = jita_prices
    print("jita_price data downloaded")
    print(str(prices_dataframe))
    return prices_dataframe

def load_json_as_dataframe():
    # Load JSON data from file
    with open("static/types_packaged_volumes.json", 'r') as file:
        data_dict = json.load(file)
    
    # Convert dictionary to dataframe
    dataframe = pd.DataFrame.from_dict(data_dict)
    dataframe.index = dataframe.index.astype(int)
    return dataframe



def process_contract(contract_id, prices_dataframe):
    try:
        contract_value, contract_packaged_volume = get_contract_items_value(contract_id, prices_dataframe)
        return contract_value, contract_packaged_volume
    except Exception as e:
        logging.error(f"Error on get_contract_items_value() when processing contract_id {contract_id}: {e}")
        return 0, 0

def get_all_contracts_from_region(region_name, cached) -> pd.Series:
    prices_dataframe = get_jita_prices(True)
    print(f'Loading contracts from {region_name} using {"cached data" if cached else "ESI"}...')
    contracts_json = get_all_contracts(region_name, cached)
    print(f'Got {len(contracts_json)} contracts!')
    logging.debug(f'Got {len(contracts_json)} contracts in {region_name}')
    contracts_df = pd.DataFrame.from_records(contracts_json)
    ie_contracts_df = contracts_df[contracts_df['type'] == 'item_exchange']

    existing_contract_ids_query = "SELECT contract_id FROM contracts;"
    existing_contract_ids = pd.read_sql_query(existing_contract_ids_query, con=engine)['contract_id'].tolist()
    ie_contracts_df = ie_contracts_df[~ie_contracts_df['contract_id'].isin(existing_contract_ids)]

    ie_contracts_df['date_issued'] = ie_contracts_df['date_issued'].apply(convert_date_string_to_datetime)
    ie_contracts_df['date_expired'] = ie_contracts_df['date_expired'].apply(convert_date_string_to_datetime)

    contract_values = []
    contract_packaged_volumes = []
    
    # Multithreading for fetching data
    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(process_contract, contract_id, prices_dataframe) for contract_id in ie_contracts_df['contract_id']]
        for future in tqdm(futures, desc="Processing Contracts", unit="contracts", total=len(futures)):
            contract_value, contract_packaged_volume = future.result()
            contract_values.append(contract_value)
            contract_packaged_volumes.append(contract_packaged_volume)

    ie_contracts_df['jita_buy_value'] = contract_values
    ie_contracts_df['packaged_volume'] = contract_packaged_volumes
    ie_contracts_df['region_name'] = region_name

    return ie_contracts_df

def get_contract_items(contract_id):
    contract_items_url = f'https://esi.evetech.net/latest/contracts/public/items/{contract_id}/'
    res = requests.get(contract_items_url)
    #print(res.headers)
    #print(res.json())
    try:
        items = res.json()
    except Exception as e:
        print(f"Error on get_contract_items() when processing contract_id {contract_id}")
        print(e)
        logging.error(f"Error on get_contract_items() when processing contract_id {contract_id}: {e}")
        empty_json = '{}'
        return empty_json
    return items

### TODO ignore fitted rig value
### Use data in static/types.en-us.yaml to get packaged volumes 
### Get rig group from static/typeIDs.yaml into a list and do a "if type_id in rigs" 
def get_contract_items_value(contract_id, prices_dataframe):
    try:
        items = get_contract_items(contract_id)
        items_df = pd.DataFrame.from_records(items)
        
    except Exception as e:
        print(f"Error on get_contract_items_value() when processing contract_id {contract_id}")
        print(e)
        logging.error(f"Error on get_contract_items_value() when processing contract_id {contract_id}: {e}")
        return None
    if 'type_id' not in items_df.columns:
            logging.error(f"Error on get_contract_items_value() when processing contract_id {contract_id}. The contract did not have a type_id column.")
            return None  # Skip contracts without a 'type_id'
    
    merged_items_df = items_df.merge(prices_dataframe, left_on='type_id', right_index=True)
    
    #print("prices df: \n", prices_dataframe)
    #print("dataframe before volumes: \n", merged_items_df)
    merged_items_df = merged_items_df.merge(packaged_volumes_dataframe, left_on='type_id', right_index=True)
    if 'is_blueprint_copy' in merged_items_df.columns: # set bpc value at 0
        merged_items_df.loc[merged_items_df['is_blueprint_copy'] == True, 'jita_price'] =  0
    # If items are requested (is_included == False), add their total value to the column "requested_price"
    merged_items_df.loc[merged_items_df['is_included'] == False, 'requested_price'] = merged_items_df['quantity'] * merged_items_df['jita_price']
    # If items requested also set their value as 0 in the contract
    merged_items_df.loc[merged_items_df['is_included'] == False, 'jita_price'] = 0
    merged_items_df.loc[merged_items_df['type_id'].isin(rig_type_ids), 'jita_price'] = 0
    merged_items_df['total_price'] = merged_items_df['quantity'] * merged_items_df['jita_price']
    merged_items_df['total_volume'] = merged_items_df['quantity'] * merged_items_df['packaged_volume'] # Calculate total volume
    
    #print(merged_items_df)
    # Calculate the total sum for all rows
    total_sum = merged_items_df['total_price'].sum()
    if merged_items_df['requested_price'].sum() > 0:
        total_requested_price = merged_items_df['requested_price'].sum()
    else:
        total_requested_price = 0
    total_packaged_volume = merged_items_df['total_volume'].sum() # Calculate total volume
    #print(f"Total sum: {total_sum}")
    #print(f"Total volume: {total_packaged_volume}")
    return total_sum, total_packaged_volume, total_requested_price



def prettify_num(number):
    pretty_num = f'{int(number):,}' # trying this to remove decimals
    return pretty_num
def prettify_age(age):
    # Get the components of the timedelta object (days, hours, minutes)
    days = age.days
    hours = age.seconds // 3600
    minutes = (age.seconds % 3600) // 60
    # Construct a human-readable string
    age_str = ""
    if days > 0:
        age_str += f"{days} days "
    if hours > 0:
        age_str += f"{hours} hours "
    if minutes > 0:
        age_str += f"{minutes} minutes"
    #print("Contract Age:", age_str)
    return age_str

def num_to_string(number):
    # Define the suffixes for large numbers
    suffixes = ['', 'thousand', 'million', 'billion', 'trillion', 'quadrillion', 'quintillion']
    
    # Determine the appropriate suffix for the given number
    suffix_index = 0
    while number >= 1000:
        number /= 1000
        suffix_index += 1
    
    # Format the number with the appropriate suffix
    formatted_number = f'{number:.0f} {suffixes[suffix_index]}'
    return formatted_number


async def send_embed(webhook_url, embed):
    try: 
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(webhook_url, session=session)
            await webhook.send(embed=embed, username=sender_name, avatar_url=sender_icon_url)
    except Exception as e:
        logging.error(f"Error {e} while sending embed: {embed}")

def send_discord_message(message): # Required to send a ping as a separate message because embeds can't have tags 
    print(f"Attempting to send a message")
    payload = {
        "content" : message,
        "username" : sender_name,
        "avatar_url": sender_icon_url
    }
    send_to_webhook = requests.post(discord_webhook_url, json = payload)
    try:
        send_to_webhook.raise_for_status()
        sleep(2) # add a small delay to prevent hitting discord rate limit
    except requests.exceptions.HTTPError as err:
        print(f"Error on send_discord_message(): {err}. Waiting 15 seconds before next message.")
        logging.error(f"Error on send_discord_message(): {err}. Waiting 15 seconds before next message.")
        sleep(15)
    else:
        print("Payload delivered successfully, code {}.".format(send_to_webhook.status_code))
        logging.debug("Notification message delivered successfully, code {}.".format(send_to_webhook.status_code))

def format_discord_embed(discount, discount_pct, difference, str_difference, volume, packaged_volume, p_packaged_volume, region_name, contract_id, p_price, p_difference, age_str, p_jita_buy_value): # Create a new embed instance to be sent
    
    if (
    (discount > (good_profit_percentage/100)) and
    (difference > minimum_profit_absolute) 
    or
    (difference > good_profit_absolute)
    ):
        print ("found a good profit!", discount)
        send_discord_message(f"Daddy <{discord_contract_notification_tag_id}> I found a good profit of {p_difference} ISK! It's on contract below :3") # tag the recipient in a separate message 
        embed = Embed(title=f"{str_difference} profit in {region_name}", color=discord.Color.green())
    if volume > 200000:
        embed = Embed(title=f"{str_difference} profit in {region_name}", color=discord.Color.red())
    else:
        embed = Embed(title=f"{str_difference} profit in {region_name}", color=discord.Color.blue())

    # Add fields to the embed
    embed.add_field(name="Contract ID", value=contract_id, inline=True)
    embed.add_field(name="Price", value=p_price, inline=True)
    embed.add_field(name="Discount", value=discount_pct, inline=True)
    embed.add_field(name="Jita Buy", value=p_jita_buy_value, inline=True)
    #embed.add_field(name="Volume", value=f"{volume} m3", inline=True)
    embed.add_field(name="Packaged volume", value=f"{p_packaged_volume} m3", inline=True)
    embed.add_field(name="Age", value=age_str, inline=True)

    # Add a link to the contract to be used in the in-game notepad
    embed.add_field(name="Paste to in-game notepad", value=f"<url=contract:30000142//{contract_id}>Contract {contract_id}</url>", inline=False)
    
    #additionally can be used to set different icons or such
    #embed.set_author(name=sender_name, icon_url=sender_icon_url) 
    return embed



async def really_send_embed():
    n_good_profit_margin = 0
    for index, row in result_df.iterrows():
        # Get data from the database for the console output
        contract_id = row['contract_id']
        price = row['price']
        jita_buy_value = row['jita_buy_value']
        volume = row['volume']
        date_issued = pd.to_datetime(row['date_issued'], utc=True)
        region_name = row['region_name']
        packaged_volume = row['packaged_volume']

        # Calculations
        discount = 1 - price/jita_buy_value
        #discount = round(discount, 3)
        discount_pct = format(discount, ".1%")
        difference = jita_buy_value - price
        p_difference=prettify_num(difference)
        p_price=prettify_num(price)
        str_difference=num_to_string(difference)
        p_jita_buy_value=prettify_num(jita_buy_value)
        age = current_timestamp - date_issued
        age_str = prettify_age(age)
        p_packaged_volume=prettify_num(packaged_volume)
        packaged_volume = "%.2f" % packaged_volume
        if discount > (minimum_profit_percentage/100) and jita_buy_value > minimum_profit_absolute:
            print(f"Contract ID: {contract_id}, Price: {p_price}, Jita Buy Value: {p_jita_buy_value}, Discount: {discount_pct}, Profit: {p_difference}, Volume: {p_packaged_volume} m3, Age: {age_str}")
            print(f"<url=contract:30000142//{contract_id}>Contract {contract_id}</url>")
            print("")
            
            #print(f"Attempting to send a message")
            embed = format_discord_embed(discount, discount_pct, difference, str_difference, volume, packaged_volume, p_packaged_volume, region_name, contract_id, p_price, p_difference, age_str, p_jita_buy_value)
            await send_embed(discord_webhook_url, embed)
            #print ("Message sent")
            n_good_profit_margin += 1
    logging.info(f"{n_good_profit_margin} of the contracts had profit margin above {minimum_profit_percentage}% and buy value above {minimum_profit_absolute} ISK")

async def main():
    await really_send_embed()

packaged_volumes_dataframe = load_json_as_dataframe()
rig_type_ids = get_rig_type_ids()

current_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
for region in regions:
    ie_contracts_df = get_all_contracts_from_region(region, False)
    ie_contracts_df['date_discovered'] = current_timestamp
    try:
        ie_contracts_df.to_sql('contracts', con=engine, if_exists='append', index=False)
    except Exception as e:
        print(e)
        print(f"Saving {region} contracts to database failed. Trying again.")
        logging.warning(f"Saving {region} contracts to database failed. Trying again.: {e}")
        try:
            ie_contracts_df.to_sql('contracts', con=engine, if_exists='append', index=False)
            print("New contracts saved to database!")
        except Exception as e:
            print(e)
            print(f"Saving {region} contracts to database failed again. Skipping.")
            logging.error(f"Saving {region} contracts to database failed again. Skipping. {e}")


# Run a SQL query to select entries where 'price' is lower than 'jita_buy_value'
query = f"""
    SELECT *
    FROM (
        SELECT *
        FROM contracts
        WHERE price < jita_buy_value
    ) AS recent_contracts
    WHERE date_discovered >= '{current_timestamp}' - INTERVAL 9 MINUTE;
"""

current_timestamp = datetime.now(timezone.utc)

# Execute the query and print the results
result_df = pd.read_sql_query(query, con=engine)
n_new_profitable_contracts = len(result_df.index)
logging.info(f"This run found {n_new_profitable_contracts} new contracts priced below Jita buy price.")
#print("here's the result_df")
#print(result_df)
# Iterate through rows and print contract_id, price, and jita_buy_value

asyncio.run(main())

logging.info(f"Script finished successfully.")
