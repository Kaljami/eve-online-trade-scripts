from flask import Flask, render_template, request
import pandas as pd
from io import StringIO
from data_processing.sde_utils import get_item_names
from data_retrieval.order_data import get_prices_from_station
import numpy as np
import locale
import redis
from dotenv import load_dotenv
import os
import pickle
locale.setlocale(locale.LC_ALL, '')

pd.set_option('display.float_format', lambda x: '%.2f' % x)

app = Flask(__name__, template_folder='./render', static_folder='./render/static', )

def redis_connection():
    load_dotenv()
    redis_host = os.getenv("redis_host")
    redis_client = redis.Redis(host=redis_host, port=6379, db=0)
    return redis_client

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

def get_from_cache(cache_key):
    redis_client = redis_connection()
    cached_data = redis_client.get(cache_key)
    if cached_data:
        print (f"Getting {cache_key} from redis cache")
        return pickle.loads(cached_data)
    else:
        print (f"That failed. Getting {cache_key} from local pickle file as last resort")
        cache_file = os.path.join('cache', f'{cache_key}.pkl')
        with open(cache_file, 'rb') as fp:
            return pickle.load(fp)

def get_market_prices(station_name, order_type, cached):
    prices_dataframe = pd.DataFrame()
    market_prices = get_prices_from_station(station_name, order_type, cached) #set False to get updated prices
    prices_dataframe['price'] = market_prices
    prices_dataframe['location'] = station_name
    if cached == False:
        print(f"Fresh {station_name} {order_type} order price data downloaded")
    return prices_dataframe

def get_best_prices(order_type):
    locations_cached = True # Redis cache should be up to date from other scripts

    jita_sell_df = get_market_prices('Jita', order_type, locations_cached)
    amarr_sell_df = get_market_prices('Amarr', order_type, locations_cached)
    delve_sell_df = get_market_prices('1DQ1-A', order_type, locations_cached)
    dodixie_sell_df = get_market_prices('Dodixie', order_type, locations_cached)

    
    # TODO add dodixie and selection for locations
    print("Calculating best prices...")
    # List of DataFrames
    sell_dfs = [jita_sell_df, amarr_sell_df, delve_sell_df, dodixie_sell_df]
    # Combine DataFrames based on 'type_id'
    combined_df = pd.concat(sell_dfs)
    combined_df.reset_index(inplace=True) # Reset index to ensure type_id becomes a column
    
    agg_df = combined_df.groupby('type_id').apply(lambda x: pd.Series({
        'min_price': x['price'].min(),
        'min_price_location': x.loc[x['price'].idxmin(), 'location'],
        'max_price': x['price'].max(),
        'max_price_location': x.loc[x['price'].idxmax(), 'location']
    }))
    # Extract prices from original dataframes and add them to the aggregated dataframe
    agg_df['price_amarr'] = agg_df.index.map(lambda x: amarr_sell_df.loc[x, 'price'] if x in amarr_sell_df.index else None)
    agg_df['price_jita'] = agg_df.index.map(lambda x: jita_sell_df.loc[x, 'price'] if x in jita_sell_df.index else None)
    agg_df['price_delve'] = agg_df.index.map(lambda x: delve_sell_df.loc[x, 'price'] if x in delve_sell_df.index else None)
    agg_df['price_dodixie'] = agg_df.index.map(lambda x: dodixie_sell_df.loc[x, 'price'] if x in dodixie_sell_df.index else None)

    # Rename columns for clarity
    agg_df.columns = ['min_price', 'min_price_location', 'max_price', 'max_price_location',
                        'price_amarr', 'price_jita', 'price_delve', 'price_dodixie']
    agg_df.reset_index(inplace=True) # Reset index again just to be sure
    #print("agg_df:\n",agg_df)

    print("agg_df:\n",agg_df)
    cache_key = f'best_prices_{order_type}'
    print(f"Saving best_prices_{order_type} to redis cache")
    
    save_to_cache(cache_key, agg_df)
    #with open(os.path.join('cache', f'{cache_key}.pkl'), 'wb') as fp:
    #    pickle.dump(agg_df, fp)
    return agg_df

def isNaN(num):
    return num != num

def prettify_num(number):
    pretty_num = f'{int(number):,}' # remove decimals to make ints pretty
    return pretty_num

def format_number(value):
    return "{:,.0f}".format(value)
    #return "{0:n}".format(value) # lol what scientific notation no thx 
    #return value
app.jinja_env.filters['format_number'] = format_number

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process_data', methods=['POST'])
def process_data():
    # Get the pasted data and selected format from the form
    data = request.form['data']
    data_format = request.form['data_format']
    user_wants_to = request.form['user_wants_to']
    order_type = request.form['order_type']
    
    if data_format == 'csv':
        user_df = pd.read_csv(StringIO(data))
        print('raw user input as df:\n', user_df)
        user_df=user_df.rename(columns={'Material':'type_name','Quantity':'quantity','Total m3':'total_volume'})
        user_df=user_df.reindex(columns=['type_name', 'quantity', 'total_volume', 'type_id'])
    elif data_format == 'eve_inventory':
        lines = data.strip().split('\n')
        type_names = []
        quantities = []
        for line in lines:
            # Split each line into type name and quantity
            parts = line.split()
            type_name = ' '.join(parts[:-1])  # Join all parts except the last one as type name
            quantity = int(parts[-1])  # Convert the last part to an integer as quantity
            
            # Append type name and quantity to respective lists
            type_names.append(type_name)
            quantities.append(quantity)

        # Create a pandas DataFrame from the lists
        user_df = pd.DataFrame({'type_name': type_names, 'quantity': quantities})
    else:
        # Handle unsupported data formats or provide an error message
        return "Unsupported data format"

    

    type_names_dict = get_item_names()
    type_ids_dict = {v: k for k, v in type_names_dict.items()}


    user_df['type_id'] = user_df['type_name'].map(type_ids_dict)
    print("User gave us this:\n", user_df)


    cached = True # prices are updated by contracts_data
    
    if cached == True: 
        try:
            cache_key = f'best_prices_{order_type}'
            agg_df = get_from_cache(cache_key)
            print("minimum prices loaded from redis cache")
        except: 
            print(f"Could not read price cache. Calculating again...")
            agg_df = get_best_prices(order_type)
    else: 
        print('Calculating a new list of best prices...')
        agg_df = get_best_prices(order_type)

    print("agg_df is lookin like:\n", agg_df)
    user_df = user_df.merge(agg_df, left_on='type_id', right_on='type_id') # Add prices to the user's list of items
    output_df = user_df

    # t_ means total. price multiplied by quantity
    output_df['t_min_price'] = user_df['min_price'] * user_df['quantity'] 
    output_df['t_max_price'] = user_df['max_price'] * user_df['quantity'] 
    output_df['t_price_jita'] = user_df['price_jita'] * user_df['quantity'] 
    output_df['t_price_amarr'] = user_df['price_amarr'] * user_df['quantity']
    output_df['t_price_delve'] = user_df['price_delve'] * user_df['quantity']
    output_df['t_price_dodixie'] = user_df['price_dodixie'] * user_df['quantity']


    # different display based on what the user is doing:
    if user_wants_to == 'buy':
        output_df['best_price'] = output_df['t_min_price']
        output_df['best_price_location'] = output_df['min_price_location']
    elif user_wants_to == 'sell':
        output_df['best_price'] = output_df['t_max_price']
        output_df['best_price_location'] = output_df['max_price_location']

    # sum of prices
    location_totals = {
        'best':output_df['best_price'].sum(skipna=False),
        'amarr':output_df['t_price_amarr'].sum(skipna=False),
        'jita':output_df['t_price_jita'].sum(skipna=False),
        'delve':output_df['t_price_delve'].sum(skipna=False),
        'dodixie':output_df['t_price_dodixie'].sum(skipna=False),
        }
    
    # add prettier explanation if something is missing from a location
    for value in location_totals:
        if isNaN(location_totals[value])==True:
            if user_wants_to == 'buy':
                if order_type == 'sell': 
                    location_totals[value] = 'Everything not available' 
                if order_type == 'buy:':
                    location_totals[value] = 'No existing buy orders for everything' # if user wants to buy using buy orders, no existing orders isn't really an issue but the data was already nan so 🤷
            if user_wants_to == 'sell':
                if order_type == 'sell':
                    location_totals[value] = 'No existing sell orders for everything' 
                if order_type == 'buy:':
                    location_totals[value] = 'No existing buy orders for everything' # also not an issue
        else:
            location_totals[value] = f"{prettify_num(location_totals[value])} ISK"

    print("Sending to html:\n", output_df)
    print("Total sums:\n", location_totals)
    return render_template(
        'result.html', 
        table=output_df.to_html(index=False), 
        total_best=location_totals['best'], 
        total_jita=location_totals['jita'], 
        total_amarr=location_totals['amarr'],
        total_dodixie=location_totals['dodixie'],
        total_delve=location_totals['delve'],
        result=output_df,
        order_type = order_type,
        price_type = 'lowest' if user_wants_to =='buy' else 'highest'
        )

if __name__ == '__main__':
    app.run(debug=True)
