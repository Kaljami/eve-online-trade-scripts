import os
import pickle

import aiohttp
import asyncio
import requests


def get_num_pages(region_id, order_type):
    """Use requests to grab a page of market orders, returning the X-Pages header from the response."""

    orders_url = f'https://esi.evetech.net/latest/markets/{region_id}/orders/'

    params = {'order_type': order_type}

    res = requests.get(orders_url, params=params)
#    print('request url: ' + res)
#    print(int(res.headers['X-Pages']))

    return int(res.headers['X-Pages'])


async def get_page(session, region_id, page, order_type):
    """Async get a page of market orders for a given region."""

    orders_url = f'https://esi.evetech.net/latest/markets/{region_id}/orders/'

    params = {
        'page': page,
        'order_type': order_type
    }

    res = await session.get(orders_url, params=params)

    return await res.json()


async def async_get_all_orders(region_id, pages, order_type):
    """Async get all pages of market orders for a given region."""

    async with aiohttp.ClientSession() as session:
        tasks = [
            get_page(session, region_id, page, order_type)
            for page in
            range(1, pages + 1)
        ]

        return await asyncio.gather(*tasks)


def get_all_orders_concurrent(system_name, order_type):
    """Master function to control async loop and process results."""

    names_to_id = {'Amarr': 10000043, 'Jita': 10000002, 'Dodixie': 10000032, 'Rens': 10000030, 'Hek': 10000042, '1DQ-1A': 10000060}
    names_to_stn = {'Amarr': 60008494, 'Jita': 60003760, 'Dodixie': 60011866, 'Rens': 60004588, 'Hek': 60005686, '1DQ-1A': 1030049082711}

    region_id = names_to_id[system_name]
    station_id = names_to_stn[system_name]

    pages = get_num_pages(region_id, order_type)

    loop = asyncio.get_event_loop()
    try:
        if order_type == "sell":
            sell_orders = loop.run_until_complete(async_get_all_orders(region_id, pages, order_type))
            return [order for page in sell_orders for order in page if order.get('location_id', 0) == station_id]
        if order_type == "buy":
            buy_orders = loop.run_until_complete(async_get_all_orders(region_id, pages, order_type))
            return [order for page in buy_orders for order in page if order.get('location_id', 0) == station_id]
    except Exception as e:
        print (e)


def get_orders_from_cache(system_name, order_type):
   """Return the latest cached copy of market orders, useful for debugging."""
   cache_file = os.path.join('cache', f'{system_name}_orders_{order_type}.pkl')

   with open(cache_file, 'rb') as fp:
       return pickle.load(fp)


def save_orders_to_cache(system_name, orders, order_type):
    """Save the given set of results to file using Pickle."""

    with open(os.path.join('cache', f'{system_name}_orders_{order_type}.pkl'), 'wb') as fp:
        pickle.dump(orders, fp)


def get_all_orders(system_name, order_type, cached):
    """Given one of 'Jita'/'Amarr', return all of the sell orders in the region."""
    if cached == True:
        print (f"Getting {system_name} {order_type} orders from cached data")
        return get_orders_from_cache(system_name, order_type)

    all_orders = get_all_orders_concurrent(system_name, order_type)
    save_orders_to_cache(system_name, all_orders, order_type)

    return all_orders
