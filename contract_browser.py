from flask import Flask, render_template, request
import pandas as pd
from io import StringIO
from data_processing.sde_utils import get_item_names
from data_retrieval.order_data import get_prices_from_station

app = Flask(__name__)

def get_market_prices(station_name, order_type, cached):
    prices_dataframe = pd.DataFrame()
    market_prices = get_prices_from_station(station_name, order_type, cached) #set False to get updated prices
    prices_dataframe['price'] = market_prices
    prices_dataframe['location'] = station_name
    if cached == False:
        print(f"Fresh {station_name} {order_type} order price data downloaded")
    return prices_dataframe

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process_data', methods=['POST'])
def process_data():
    csv_data = request.form['csv_data']
    # Convert the CSV data to a Pandas DataFrame
    user_df = pd.read_csv(StringIO(csv_data))

    type_names_dict = get_item_names()
    type_ids_dict = {v: k for k, v in type_names_dict.items()}

    user_df['type_id'] = user_df['Material'].map(type_ids_dict)
    # Render a new template with the DataFrame displayed
    type_names_dict = get_item_names()
    type_ids_dict = {v: k for k, v in type_names_dict.items()}


    user_df['type_id'] = user_df['Material'].map(type_ids_dict)
    user_df=user_df.reindex(columns=['Material', 'Quantity', 'Total m3', 'type_id'])

    order_type = 'sell'
    cached = True

    jita_sell_df = get_market_prices('Jita', 'sell', cached)
    amarr_sell_df = get_market_prices('Amarr', 'sell', cached)

    # List of DataFrames
    sell_dfs = [jita_sell_df, amarr_sell_df]
    # Combine DataFrames based on 'type_id'
    combined_df = pd.concat(sell_dfs).groupby('type_id')

    # Initialize empty list to store result rows
    result_rows = []

    # Iterate over grouped DataFrames
    for type_id, group in combined_df:
        # Initialize dictionary to store results for current 'type_id'
        result_dict = {'type_id': type_id}
        
        # Find the minimum price across all locations
        min_price = group['price'].min()
        
        # Find the location of the minimum price across all locations
        min_price_location = group.loc[group['price'] == min_price, 'location'].iloc[0]
        
        # Add columns for minimum price and location across all locations
        result_dict['min_price'] = min_price
        result_dict['min_price_location'] = min_price_location
        
        # Iterate over unique locations in the group
        for location in group['location'].unique():
            # Filter group by location
            location_group = group[group['location'] == location]
            
            # Find the minimum price for the location
            min_price_location = location_group['price'].min()
            
            # Add column for minimum price in the current location
            result_dict[f'price_{location.replace(" ", "_")}'] = min_price_location
        
        # Append result_dict to result_rows
        result_rows.append(result_dict)

    # Convert result_rows to DataFrame
    min_sell_df = pd.DataFrame(result_rows)

    #print(min_sell_df)

    user_df = user_df.merge(min_sell_df, left_on='type_id', right_on='type_id')

    #print(user_df)
    user_df2 = user_df
    user_df2['min_price'] = user_df['min_price'] * user_df['Quantity'] 
    user_df2['price_Jita'] = user_df['price_Jita'] * user_df['Quantity'] 
    user_df2['price_Amarr'] = user_df['price_Amarr'] * user_df['Quantity']
    user_df2.loc[user_df2['price_Amarr'] == None, 'price_Amarr'] = user_df2['min_price']
    #print(user_df2)
    total_jita = user_df['price_Jita'].sum()
    #print(total_jita)






    return render_template('result.html', table=user_df2.to_html())

if __name__ == '__main__':
    app.run(debug=True)
