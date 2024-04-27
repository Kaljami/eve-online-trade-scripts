import os
import pickle

import aiohttp
import asyncio
import requests
import pandas as pd
import json


def get_num_pages(region_id, order_type, sso_session):
    params = {'order_type': order_type}
    
    if region_id == 10000060:
        structure_id = 1030049082711
        orders_url = f'https://esi.evetech.net/latest/markets/structures/{structure_id}/'
        if sso_session == None:
            raise Exception("Must authenticate with SSO to access market on player structures.")
        res = sso_session.get(orders_url, params=params)
    else:
        orders_url = f'https://esi.evetech.net/latest/markets/{region_id}/orders/'
        res = requests.get(orders_url, params=params)

    #print('request url: ' + res)
    #print(f"Json: {res.json()} Headers: {res.headers}")
    #print("pages:",int(res.headers['X-Pages']))

    return int(res.headers['X-Pages'])


def citadel_get_page(structure_id, page, order_type, sso_session):
    orders_url = f'https://esi.evetech.net/latest/markets/structures/{structure_id}/'
    params = {
        'page': page,
        'order_type': order_type
    }
    res = sso_session.get(orders_url, params=params)
    res.raise_for_status()
    return res.json()

async def get_page(session, region_id, page, order_type):
    orders_url = f'https://esi.evetech.net/latest/markets/{region_id}/orders/'
    params = {
        'page': page,
        'order_type': order_type
    }
    res = await session.get(orders_url, params=params)
    return await res.json()

def citadel_get_all_orders(station_id, pages, order_type, sso_session):
    orders = []
    for page in range(1, pages + 1):
        page_orders = citadel_get_page(station_id, page, order_type, sso_session)
        orders.extend(page_orders)
    return orders

async def async_get_all_orders(region_id, pages, order_type):

    async with aiohttp.ClientSession() as session:
        tasks = [
            get_page(session, region_id, page, order_type)
            for page in
            range(1, pages + 1)
        ]
        return await asyncio.gather(*tasks)

def get_all_orders(system_name, order_type, cached, sso_session):
    if cached == True:
        print (f"Getting {system_name} {order_type} orders from cached data")
        return get_orders_from_cache(system_name, order_type)
    all_orders = get_all_orders_concurrent(system_name, order_type, sso_session)
    save_orders_to_cache(system_name, all_orders, order_type)
    out_file = open(f"exports/debug_{system_name}.json", "w") 
    json.dump(all_orders, out_file, indent = 6) 
    out_file.close() 
    return all_orders



def get_all_orders_concurrent(system_name, order_type, sso_session):
    #Master function to control async loop and process results

    names_to_id = {'Amarr': 10000043, 'Jita': 10000002, 'Dodixie': 10000032, 'Rens': 10000030, 'Hek': 10000042, '1DQ1-A': 10000060}
    names_to_stn = {'Amarr': 60008494, 'Jita': 60003760, 'Dodixie': 60011866, 'Rens': 60004588, 'Hek': 60005686, '1DQ1-A': 1030049082711}

    region_id = names_to_id[system_name]
    station_id = names_to_stn[system_name]

    pages = get_num_pages(region_id, order_type, sso_session)
    if region_id == 10000060:
        all_orders = citadel_get_all_orders(station_id, pages, order_type, sso_session)
        if order_type == "sell":
            sell_orders = [order for order in all_orders if not order["is_buy_order"]]
            return sell_orders
        if order_type == "buy":
            buy_orders = [order for order in all_orders if order["is_buy_order"]]
            return buy_orders
        
    else:
        loop = asyncio.get_event_loop()
        try:
            if order_type == "sell":
                sell_orders = loop.run_until_complete(async_get_all_orders(region_id, pages, order_type))
                output = [order for page in sell_orders for order in page if order.get('location_id', 0) == station_id]
                return output
            
            if order_type == "buy":
                buy_orders = loop.run_until_complete(async_get_all_orders(region_id, pages, order_type))
                return [order for page in buy_orders for order in page if order.get('location_id', 0) == station_id]
        except Exception as e:
            print (e)


def get_orders_from_cache(system_name, order_type):
   cache_file = os.path.join('cache', f'{system_name}_orders_{order_type}.pkl')
   with open(cache_file, 'rb') as fp:
       return pickle.load(fp)


def save_orders_to_cache(system_name, orders, order_type):
    with open(os.path.join('cache', f'{system_name}_orders_{order_type}.pkl'), 'wb') as fp:
        pickle.dump(orders, fp)


def get_average_prices(cached):
    system_name = 'Universe'
    order_type = 'average'
    if cached:
        print (f"Getting {system_name} {order_type} prices from cached data")
        avg_prices_data = get_orders_from_cache(system_name, order_type)
    if not cached:
        print (f"Getting {system_name} {order_type} prices from ESI")
        avg_prices_url = f"https://esi.evetech.net/latest/markets/prices/?datasource=tranquility"
        avg_prices_response = requests.get(avg_prices_url)
        avg_prices_data = avg_prices_response.json()
        save_orders_to_cache(system_name, avg_prices_data, order_type)
    avg_prices_dataframe = pd.DataFrame(avg_prices_data)
    avg_prices_dataframe = avg_prices_dataframe.reindex(columns=['type_id','average_price'])
    avg_prices_dataframe = avg_prices_dataframe.rename(columns={'average_price':'price'})
    avg_prices_dataframe.set_index('type_id', inplace=True)
    #print(str(avg_prices_dataframe))
    return avg_prices_dataframe
