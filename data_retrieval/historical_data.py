import asyncio
import os
import pickle

import aiohttp


async def get_history(session, region_id, typeID):
    """Async get historical volume data for a given region and typeID."""

    history_url = f'https://esi.evetech.net/latest/markets/{region_id}/history/'

    params = {
        'type_id': typeID
    }

    headers = {
        'accept': 'application/json'
    }

    while True:
        try:
            res = await session.get(history_url, params=params, headers=headers)
            return (typeID, await res.json())
        except aiohttp.ClientResponseError:
            pass


async def gather_all_history(region_id, typeIDs):
    """Async get volume of all items in a list for a given region."""

    async with aiohttp.ClientSession() as session:
        tasks = [
            get_history(session, region_id, typeID)
            for typeID in
            typeIDs
        ]

        return await asyncio.gather(*tasks)


def get_all_history_concurrent(region_id, typeIDs):
    """Master function to control async loop and process results."""

    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(gather_all_history(region_id, typeIDs))

    return {typeID: data for typeID, data in result}


def get_orders_from_cache(system_name):
    """Return the latest cached copy of market orders, useful for debugging."""

    with open(os.path.join('cache', f'{system_name}_historic.pkl'), 'rb') as fp:
        return pickle.load(fp)


def save_orders_to_cache(system_name, data):
    """Save the given set of results to file using Pickle."""

    with open(os.path.join('cache', f'{system_name}_historic.pkl'), 'wb') as fp:
        pickle.dump(data, fp)


def get_all_history(system_name, typeIDs, cached):
    """Given one of 'Jita'/'Amarr', return all of the historical order data in the region."""

    if cached:
        print (f"Getting {system_name} market history from cached data")
        return get_orders_from_cache(system_name) 

    names_to_id = {'Amarr': 10000043, 'Jita': 10000002, 'Dodixie': 10000032, 'Rens': 10000030, 'Hek': 10000042, '1DQ-1A': 10000060}
    region_id = names_to_id[system_name]

    result = get_all_history_concurrent(region_id, typeIDs)

    save_orders_to_cache(system_name, result)

    return result
