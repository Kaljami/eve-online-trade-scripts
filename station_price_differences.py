import pandas as pd

import order_data
import historical_data
import order_import
import render
from sde_utils import get_item_names, get_item_sizes
import os
from price_differences import get_prices_from_station, get_ungrouped_prices_from_station, get_volume_price_history



### basically a duplicate of price_differences.py. There is probably a better way to do this.  
# give penalty score for competing sellers if settings.dest_order_type == sell
# Add sorting to output html. Maybe output as excel or csv? 
# Maybe add those variables below to settings? 

def price_differences(settings):
    
    minimum_margin = 0.1 # 10%
    minimum_profit_per_m3 = 1000


    print('Loading Static Data Export mappings...', end=' ')
    typeIDs_to_names = get_item_names()
    typeIDs_to_sizes = get_item_sizes()
    print('Done!')

    # Results DataFrame
    summary = pd.DataFrame()

    # Order Series
    source_prices = get_prices_from_station(settings.source_hub, "buy", settings.cache_all)
    dest_prices = get_prices_from_station(settings.source_hub, "sell", settings.cache_all)
    ungrouped_source_prices = get_ungrouped_prices_from_station(settings.source_hub, "buy", settings.cache_all)
    ungrouped_dest_prices = get_ungrouped_prices_from_station(settings.source_hub, "buy", settings.cache_all)
    #print(str(source_prices))
    #print(str(ungrouped_source_prices))



    # Sell-side costs: Broker fees (~3.5%), Sales tax (~2.25%), Hauling fees (~2%).
    dest_prices_taxed = dest_prices * ((1 - 0.035 - 0.0225) * (1 - 0.02))

    # Series back into output DF columns
    summary['Source price'] = source_prices
    summary['Destination price'] = dest_prices_taxed
    summary['Profit'] = summary['Destination price'] - summary['Source price']
    summary['Margin'] = summary['Profit'] / summary['Source price']

    # Availability calculations
    # Calculate the maximum source price that allows for the specified margin
    summary['max_source_price'] = summary['Destination price'] / (1 + minimum_margin)

    # Calculate the maximum source price that allows for the specified margin
    #ungrouped_source_prices['max_source_price'] = summary['Destination price'] / (1 - minimum_margin)
    #print("ungrouped_source_prices")
    #print(str(ungrouped_source_prices))

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
    summary['Average Price'] = grouped_source_prices['price']
    # Remove rows below margin treshold
    summary = summary[summary['Margin'] >= minimum_margin]

    # Print summary DataFrame to check values
    print("summary:")
    print(str(summary))
    # Get historical volume and price for order refinement
    volume, price = get_volume_price_history(settings.source_hub, summary.index, settings.days_history, settings.cache_all)

    summary['Daily Volume'] = volume

    # Remove orders where the ratio of current price to historic price is too high
    summary = summary[(summary['Destination price'] / price) < float(settings.bogus_threshold)]

    # Finally, calculate expected profit per item by multiplying unit profit by mean daily volume or number of available units, whichever is lower
    summary['Total Profit'] = summary['Profit'] * summary.apply(lambda row: min(row['Units available'], row['Daily Volume']), axis=1)

    # Clean up by dropping NAN rows - Usually this means no volume data or no sell-side orders.
    summary = summary.dropna()

    # Find out which items are already being traded by the player
    player_orders_df = pd.read_csv(order_import.get_player_orders_file())
    player_orders_set = set(player_orders_df['typeID'])
    summary['Already Selling'] = summary.index.isin(player_orders_set)

    if settings.hide_existing:
        summary = summary[~summary['Already Selling']]
        summary = summary.drop('Already Selling', axis=1)

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
    url = render.render_to_html(summary)
    return url
