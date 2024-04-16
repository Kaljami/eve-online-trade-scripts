import os
import requests
import aiohttp
import asyncio
import pandas as pd
import nest_asyncio
from sqlalchemy import create_engine, inspect
from tqdm import tqdm
from data_retrieval.price_differences import get_prices_from_station
from datetime import datetime, timezone
import discord
from discord import Embed
import yaml
import json
import logging
from dotenv import load_dotenv

### SETTINGS BEGIN

load_dotenv()
# MySQL Database:
db_user = os.getenv("mysql_user")
db_password = os.getenv("mysql_password")
db_host = os.getenv("mysql_host")
db_database = os.getenv("mysql_database")

# Contracts: 
regions = ["Delve", "Domain", "Placid", "Sinq Laison", "Lonetrek", "The Citadel", "Essence", "Querious", "Fountain", "Period Basis", "Aridia"]
minimum_profit_percentage = 20
minimum_profit_absolute = 30000000 #30 million
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
#    print('request url: ' + res)
#    print(int(res.headers['X-Pages']))

    return int(res.headers['X-Pages'])

async def get_page(session, region_id, page):
    """Async get a page of contracts for a given region."""

    contracts_url = f'https://esi.evetech.net/latest/contracts/public/{region_id}/'

    params = {
        'page': page
    }

    res = await session.get(contracts_url, params=params)
    #print(res.json)
    return await res.json()

#get_page(10000060, 1)

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
        print ("we don't have cache for contracts yet")
    #    print (f"Getting {region_name} {order_type} orders from cached data")
    #    return get_orders_from_cache(region_name, order_type)
    else:
        all_contracts = get_all_contracts_concurrent(region_name)
        #print("all_contracts:",all_contracts)
    #save_orders_to_cache(region_name, all_orders, order_type)

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



def get_all_contracts_from_region(region_name, cached) -> pd.Series:
    prices_dataframe = get_jita_prices(True)
    # Get orders as JSON
    print(f'Loading contracts from {region_name} using {"cached data" if cached else "ESI"}...')
    contracts_json = get_all_contracts(region_name, cached)

    ################################################################### Reduce the amount of data for testing
    #contracts_json = contracts_json[:200]
    ###################################################################

    print(f'Got {len(contracts_json)} contracts!')
    logging.info(f'Got {len(contracts_json)} contracts in {region_name}')
    contracts_df = pd.DataFrame.from_records(contracts_json)
    ie_contracts_df = contracts_df[contracts_df['type'] == 'item_exchange']

    # Run a SQL query to get a list of existing contract_id's
    existing_contract_ids_query = "SELECT contract_id FROM contracts;"
    existing_contract_ids = pd.read_sql_query(existing_contract_ids_query, con=engine)['contract_id'].tolist()
    # Filter ie_contracts_df to exclude contracts with existing contract_id's
    ie_contracts_df = ie_contracts_df[~ie_contracts_df['contract_id'].isin(existing_contract_ids)]

    # Convert date strings to datetime and format them
    ie_contracts_df['date_issued'] = ie_contracts_df['date_issued'].apply(convert_date_string_to_datetime)
    ie_contracts_df['date_expired'] = ie_contracts_df['date_expired'].apply(convert_date_string_to_datetime)

    # Get value and packaged volume of every contract
    contract_values = []
    contract_packaged_volumes = []
    for contract_id in tqdm(ie_contracts_df['contract_id'], desc="Processing Contracts", unit="contracts"):
        try:
            contract_value, contract_packaged_volume = get_contract_items_value(contract_id, prices_dataframe)
            contract_values.append(contract_value)
            contract_packaged_volumes.append(contract_packaged_volume)
        except Exception as e:
            print(f"Error on get_contract_items_value() when processing contract_id {contract_id}:")
            print(e)
            logging.error(f"Error on get_contract_items_value() when processing contract_id {contract_id}: {e}")
            contract_value = 0
            contract_packaged_volume = 0
            contract_values.append(contract_value)
            contract_packaged_volumes.append(contract_packaged_volume)

        


    ie_contracts_df['jita_buy_value'] = contract_values
    ie_contracts_df['packaged_volume'] = contract_packaged_volumes
    ie_contracts_df['region_name'] = region_name
    print(str(ie_contracts_df))
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
            return None  # Skip contracts without a 'type_id'
    
    merged_items_df = items_df.merge(prices_dataframe, left_on='type_id', right_index=True)
    
    #print("prices df: \n", prices_dataframe)
    #print("dataframe before volumes: \n", merged_items_df)
    merged_items_df = merged_items_df.merge(packaged_volumes_dataframe, left_on='type_id', right_index=True)
    if 'is_blueprint_copy' in merged_items_df.columns: # set bpc value at 0
        merged_items_df.loc[merged_items_df['is_blueprint_copy'] == True, 'jita_price'] =  0
    merged_items_df.loc[merged_items_df['is_included'] == False, 'jita_price'] = -abs(merged_items_df['jita_price']) # It's not a good solution, but it's solution. If a contract requests items, mark their value as negative instead. TODO do something smarter.
    merged_items_df['total_price'] = merged_items_df['quantity'] * merged_items_df['jita_price']
    merged_items_df['total_volume'] = merged_items_df['quantity'] * merged_items_df['packaged_volume'] # Calculate total volume
    
    #print(merged_items_df)
    # Calculate the total sum for all rows
    total_sum = merged_items_df['total_price'].sum()
    total_packaged_volume = merged_items_df['total_volume'].sum() # Calculate total volume
    #print(f"Total sum: {total_sum}")
    #print(f"Total volume: {total_packaged_volume}")
    return total_sum, total_packaged_volume



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
    async with aiohttp.ClientSession() as session:
        webhook = discord.Webhook.from_url(webhook_url, session=session)
        await webhook.send(embed=embed, username=sender_name, avatar_url=sender_icon_url)

def send_discord_message(message): # Required to send a ping because embeds can't have tags 
    print(f"Attempting to send a message")
    payload = {
        "content" : message,
        "username" : sender_name,
        "avatar_url": sender_icon_url
    }
    send_to_webhook = requests.post(discord_webhook_url, json = payload)
    try:
        send_to_webhook.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(err) # TODO add delay if 429 rate limit
        logging.error(f"Error on send_discord_message(): {err}")
    else:
        print("Payload delivered successfully, code {}.".format(send_to_webhook.status_code))
        logging.info("Payload delivered successfully, code {}.".format(send_to_webhook.status_code))

def format_discord_embed(discount, discount_pct, difference, str_difference, volume, packaged_volume, region_name, contract_id, p_price, p_difference, age_str, p_jita_buy_value):
    # Create a new embed instance
    if ((discount > 0.4)and (difference > minimum_profit_absolute)): #TODO add setting variable for tags
        print ("found a good profit!", discount)
        send_discord_message(f"Daddy <{discord_contract_notification_tag_id}> I found a good profit margin of {discount_pct}! It's on contract below :3") # tag the recipient in a separate message 
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
    embed.add_field(name="Volume", value=f"{volume}m3", inline=True)
    embed.add_field(name="Packaged volume", value=f"{packaged_volume}m3", inline=True)
    embed.add_field(name="Age", value=age_str, inline=True)

    # Add a link to the contract in the in-game notepad
    embed.add_field(name="Paste to in-game notepad", value=f"<url=contract:30000142//{contract_id}>Contract {contract_id}</url>", inline=False)
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
        packaged_volume = "%.2f" % packaged_volume
        if discount > (minimum_profit_percentage/100) and jita_buy_value > minimum_profit_absolute:
            print(f"Contract ID: {contract_id}, Price: {p_price}, Jita Buy Value: {p_jita_buy_value}, Discount: {discount_pct}, Profit: {p_difference}, Volume: {volume}m3, Issued: {date_issued}, Age: {age_str}")
            print(f"<url=contract:30000142//{contract_id}>Contract {contract_id}</url>")
            print("")
            
            #print(f"Attempting to send a message")
            embed = format_discord_embed(discount, discount_pct, difference, str_difference, volume, packaged_volume, region_name, contract_id, p_price, p_difference, age_str, p_jita_buy_value)
            await send_embed(discord_webhook_url, embed)
            #print ("Message sent")
            n_good_profit_margin += 1
    logging.info(f"{n_good_profit_margin} of the contracts had profit margin above {minimum_profit_percentage}% and buy value above {minimum_profit_absolute} ISK")

async def main():
    await really_send_embed()

packaged_volumes_dataframe = load_json_as_dataframe()
print(packaged_volumes_dataframe)

current_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
for region in regions:
    ie_contracts_df = get_all_contracts_from_region(region, False)
    ie_contracts_df['date_discovered'] = current_timestamp
    try:
        ie_contracts_df.to_sql('contracts', con=engine, if_exists='append', index=False)
    except Exception as e:
        print(e)
        print(f"Saving {region} contracts to database failed. Trying again.")
        logging.error(f"Saving {region} contracts to database failed. Trying again.: {e}")
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
    WHERE date_discovered >= '{current_timestamp}' - INTERVAL 10 MINUTE;
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
