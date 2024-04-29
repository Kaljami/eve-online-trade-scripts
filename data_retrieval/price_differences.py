import pandas as pd

import data_retrieval.order_data as order_data
import data_retrieval.historical_data as historical_data
import data_processing.render as render
from data_processing.sde_utils import get_item_names, get_item_sizes
import os
from datetime import timedelta
pd.set_option('display.float_format', lambda x: '%.2f' % x) # disable scientific notation for floats in the dataframes

def get_prices_from_station(station_name, order_type, cached, sso_session=None) -> pd.Series:
    # Get orders as JSON
    time_since = order_data.check_metadata('prices')
    if time_since < timedelta(minutes=30):
        cached = True
    print(f'Loading {order_type} orders from {station_name} using {"cached data" if cached else "ESI"}...')
    orders_json = order_data.get_all_orders(station_name, order_type, cached, sso_session)
    #print ("get_prices_from_station says: orders_json:",str(orders_json))
    # This sometimes fails for unknown reason. 
    print(f'Got {len(orders_json)} orders!')

    # Convert to DF and find the best price for each typeID
    df = pd.DataFrame.from_records(orders_json)
    #print(df)
    if order_type == "sell":
        return df.groupby('type_id')['price'].min()  # pd.Series
    if order_type == "buy":
        return df.groupby('type_id')['price'].max()  # pd.Series
    
def get_ungrouped_prices_from_station(station_name, order_type, cached, sso_session=None) -> pd.Series:
    # Get orders as JSON. Keep all the orders instead of only the best price available. 
    time_since = order_data.check_metadata('prices')
    if time_since < timedelta(minutes=30):
        cached = True
    print(f'Loading {order_type} orders from {station_name} using {"cached data" if cached else "ESI"}...')
    orders_json = order_data.get_all_orders(station_name, order_type, cached, sso_session) #this could as well be always cached 
    print(f'Got {len(orders_json)} orders!')

    # Convert to DF
    df = pd.DataFrame.from_records(orders_json)
    result_df = df.copy()
    print (str(result_df))
    return result_df
    


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
    print(historical_df)
    if 'date' in historical_df.columns:
        historical_df = historical_df.drop('date', axis='columns')
    historical_df.columns = pd.to_datetime(historical_df.columns, yearfirst=True)
    print('Done!')

    print(f'Pulling out historical volume data for {days} days:')
    v = historical_df.loc[idx[:, 'volume'], historical_df.columns > (pd.Timestamp('today').floor('D') - pd.offsets.Day(int(days)))]
    v = v.fillna(0).mean(axis=1)
    """ FYI TODO
    FutureWarning: Downcasting object dtype arrays on .fillna, .ffill, .bfill is deprecated and will change in a future version. Call result.infer_objects(copy=False) instead. To opt-in to the future behavior, set `pd.set_option('future.no_silent_downcasting', True)`
    v = v.fillna(0).mean(axis=1)
    """
    v = v.droplevel(1, axis=0)

    print(f'Pulling out historical price data for {days} days:')
    p = historical_df.loc[idx[:, 'average'], historical_df.columns > (pd.Timestamp('today').floor('D') - pd.offsets.Day(int(days)))]
    p = p.mean(axis=1)
    p = p.droplevel(1, axis=0)

    print('Done!')
    return v, p


### TODO: 
# give penalty score for competing sellers if settings.dest_order_type == sell
# Add sorting to output html. Maybe output as excel or csv? 
# Maybe add those variables below to settings? 

def price_differences(settings, sso_session):
    
    minimum_margin = 0.1 # 10%
    minimum_profit_per_m3 = 1000

    print('Loading Static Data Export mappings...', end=' ')
    typeIDs_to_names = get_item_names()
    typeIDs_to_sizes = get_item_sizes()
    print('Done!')

    # Results DataFrame
    summary = pd.DataFrame()

    # Order Series
    source_prices = get_prices_from_station(settings.source_hub, settings.source_order_type, settings.cache_all, sso_session)
    dest_prices = get_prices_from_station(settings.dest_hub, settings.dest_order_type, settings.cache_all, sso_session)
    ungrouped_source_prices = get_ungrouped_prices_from_station(settings.source_hub, settings.source_order_type, settings.cache_all, sso_session)
    ungrouped_dest_prices = get_ungrouped_prices_from_station(settings.dest_hub, settings.dest_order_type, settings.cache_all, sso_session)

    # Sell-side costs: Broker fees (~3.5%), Sales tax (~2.25%), Hauling fees (~2%).
    dest_prices_taxed = dest_prices * ((1 - 0.035 - 0.0225) * (1 - 0.02))

    # Series back into output DF columns
    summary['Source price'] = source_prices
    summary['Destination price'] = dest_prices_taxed
    summary['Profit'] = summary['Destination price'] - summary['Source price']
    summary['Margin'] = summary['Profit'] / summary['Source price']

    # Availability calculations
    # Calculate the maximum source price that allows for the specified margin
    if settings.dest_order_type == 'sell':
        summary['max_source_price'] = summary['Destination price'] / (1 + minimum_margin)
    if settings.dest_order_type == 'buy':
        summary['max_source_price'] = summary['Destination price'] / (1 + minimum_margin/2)
        summary['min_dest_price'] = summary['Source price'] * (1 + minimum_margin/2) # No clue if this is at all correct. Idea is to split the profit margin to be flexible on both ends
    

    # Merge max prices from summary to ungrouped 
    ungrouped_max_source_prices = ungrouped_source_prices.merge(summary[['max_source_price']], how='left', on='type_id')
    print("ungrouped_max_source_prices")
    print(str(ungrouped_max_source_prices))
    os.makedirs('exports', exist_ok=True)
    ungrouped_max_source_prices.to_csv('exports/ungrouped_max_source_prices.csv')  
    # Remove rows where the price is higher than the max_source_price
    filtered_source_prices = ungrouped_max_source_prices[ungrouped_max_source_prices['price'] <= ungrouped_max_source_prices['max_source_price']]
    print("filtered_source_prices")
    print(str(filtered_source_prices))
    filtered_source_prices.to_csv('exports/filtered_source_prices.csv')  
    # Group the remaining rows by type_id
    grouped_source_prices = filtered_source_prices.groupby('type_id').agg({'price':'mean','max_source_price':'first','volume_remain':'sum'})
    print("grouped_source_prices")
    print(str(grouped_source_prices))
    grouped_source_prices.to_csv('exports/grouped_source_prices.csv')  
    # Save the total volume_remaining for each type_id
    summary['Units available'] = grouped_source_prices['volume_remain']
    # Save the average price for each type_id
    summary['Mean Sell Price'] = grouped_source_prices['price']
    # Remove rows below margin treshold
    summary = summary[summary['Margin'] >= minimum_margin]

    # Merge min prices from summary to ungrouped 
    ungrouped_min_dest_prices = ungrouped_dest_prices.merge(summary[['min_dest_price']], how='left', on='type_id')
    print("ungrouped_min_dest_prices")
    print(str(ungrouped_min_dest_prices))
    ungrouped_min_dest_prices.to_csv('exports/ungrouped_min_dest_prices.csv')  
    # Remove rows where the price is lower than preferred
    filtered_dest_prices = ungrouped_min_dest_prices[ungrouped_min_dest_prices['price'] >= ungrouped_min_dest_prices['min_dest_price']]
    print("filtered_dest_prices")
    print(str(filtered_dest_prices))
    filtered_dest_prices.to_csv('exports/filtered_dest_prices.csv')  
    # Group the remaining rows by type_id
    grouped_dest_prices = filtered_dest_prices.groupby('type_id').agg({'price':'mean','min_dest_price':'first','volume_remain':'sum'})
    print("grouped_dest_prices")
    print(str(grouped_dest_prices))
    grouped_dest_prices.to_csv('exports/grouped_dest_prices.csv')
    # Save the total volume_remaining for each type_id
    summary['Units on buy orders'] = grouped_dest_prices['volume_remain']
    # Save the average price for each type_id
    summary['Mean Buy Price'] = grouped_dest_prices['price']


    # Print summary DataFrame to check values
    print("summary:")
    print(str(summary))
    # Get historical volume and price for order refinement
    volume, price = get_volume_price_history(settings.dest_hub, summary.index, settings.days_history, settings.cache_all)

    summary['Daily Volume'] = volume

    # Remove orders where the ratio of current price to historic price is too high
    summary = summary[(summary['Destination price'] / price) < float(settings.bogus_threshold)]

    # Finally, calculate expected profit per item by multiplying unit profit by mean daily volume or number of available units, whichever is lower
    if settings.dest_order_type == 'sell':
        summary['Total Profit'] = summary['Profit'] * summary.apply(lambda row: min(row['Units available'], row['Daily Volume']), axis=1)
    if settings.dest_order_type == 'buy':
         summary['Total Profit'] = summary['Profit'] * summary.apply(lambda row: min(row['Units available'], row['Daily Volume']), axis=1) # TODO get amount of units on buy orders 
    # Clean up by dropping NAN rows - Usually this means no volume data or no sell-side orders.
    summary = summary.dropna()

    # Find out which items are already being traded by the player
    """
    player_orders_df = pd.read_csv(order_import.get_player_orders_file()) # this should be updated to use ESI data if it's needed at all
    player_orders_set = set(player_orders_df['typeID'])
    summary['Already Selling'] = summary.index.isin(player_orders_set)

    if settings.hide_existing:
        summary = summary[~summary['Already Selling']]
        summary = summary.drop('Already Selling', axis=1)
    """
    # Calculate item volume required to fulfil daily sale volume
    summary['Haul Size'] = summary['Units available'] * summary.index.map(typeIDs_to_sizes)

    # Profit per item size
    summary['ISK p m3'] = summary['Profit'] / summary.index.map(typeIDs_to_sizes)
    summary = summary[summary['ISK p m3'] >= minimum_profit_per_m3]

    # Sort by profit descending for output
    summary = summary.sort_values(by='Total Profit', ascending=False)

    # Use item names instead of typeIDs
    summary['typeID'] = summary.index
    summary = summary.rename(typeIDs_to_names)
    summary.to_csv('exports/summary.csv') 
    # Output to a pretty table and return URL for further use
    print("Opening result in browser. Result saved as exports/summary.csv")
    url = render.render_to_html(summary)
    return url
