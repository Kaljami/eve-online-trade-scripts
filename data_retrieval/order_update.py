import pandas as pd
from pynput import keyboard
import pyperclip
import requests

import data_retrieval.order_import as order_import
from data_retrieval.price_differences import get_prices_from_station

# TODO: Load character location from session and use that as region to check orders

# Calculates what you should set as your price to be the lowest bidder
def reduce_price(input_number):
    # Convert the input number to a string to be cut up
    input_str = str(input_number)
    # Split the input into integer and decimal parts
    integer_part, decimal_part = input_str.split('.')
    # Combine the integer part and decimal part
    combined_number = integer_part + decimal_part
    # Save first 4 digits into a variable
    first_four_digits = integer_part[:4]
    # Save all the remaining digits, including period and decimals into another variable
    remaining_digits = combined_number[5:]
    if input_number >1000:
        # Reduce 1 from the count that is the first 4 digits
        first_four_digits = str(int(first_four_digits) - 1)
        #print(first_four_digits, "after")
        # Combine the new 4 digits and any trailing numbers back up
        result_number = first_four_digits + remaining_digits
        return result_number
    if 100 < input_number <= 1000:
        result_number = first_four_digits + '.' + decimal_part
        result_number = str(float(result_number) - 0.1)
        return result_number
    else:
        result_number = first_four_digits + '.' + decimal_part
        result_number = str(float(result_number) - 0.01)
        return result_number
    
def increase_price(input_number):
    # Convert the input number to a string to be cut up
    input_str = str(input_number)
    # Split the input into integer and decimal parts
    integer_part, decimal_part = input_str.split('.')
    # Combine the integer part and decimal part
    combined_number = integer_part + decimal_part
    # Save first 4 digits into a variable
    first_four_digits = integer_part[:4]
    # Save all the remaining digits, including period and decimals into another variable
    remaining_digits = combined_number[5:]
    if input_number >1000:
        # Reduce 1 from the count that is the first 4 digits
        first_four_digits = str(int(first_four_digits) + 1)
        #print(first_four_digits, "after")
        # Combine the new 4 digits and any trailing numbers back up
        result_number = first_four_digits + remaining_digits
        return result_number
    if 100 < input_number <= 1000:
        result_number = first_four_digits + '.' + decimal_part
        result_number = str(float(result_number) + 0.1)
        return result_number
    else:
        result_number = first_four_digits + '.' + decimal_part
        result_number = str(float(result_number) + 0.01)
        return result_number




# Primary function here. Goes through market orders and compares the prices to esi data (cached data if available.)
def update_all(settings, session, character_id):
    character_orders_url = f'https://esi.evetech.net/latest/characters/{character_id}/orders/'
    character_orders_response = session.get(character_orders_url)
    character_orders_data = character_orders_response.json()
    #print ("current player sell orders from ESI:",sell_orders_data) 

    # Convert the orders data to a DataFrame
    sell_orders = pd.DataFrame(character_orders_data)
    buy_orders = pd.DataFrame(character_orders_data)
    sell_orders.set_index('type_id', inplace=True)
    buy_orders.set_index('type_id', inplace=True)
    sell_orders['is_buy_order'] = sell_orders['is_buy_order'].fillna(False)
    
    print("Market order list found")

    # Download actual up-to-date prices from ESI
    min_prices = get_prices_from_station(settings.dest_hub, "sell", settings.cache_all)
    max_prices = get_prices_from_station(settings.dest_hub, "buy", settings.cache_all)

    sell_orders_f = sell_orders[sell_orders['is_buy_order'] == False]
    buy_orders_f = buy_orders[buy_orders['is_buy_order'] == True]


    sell_orders_f['min_price'] = min_prices.apply(lambda x: reduce_price(x))
    buy_orders_f['max_price'] = max_prices.apply(lambda x: increase_price(x))

    print("current player orders with minprice:")
    print(str(sell_orders_f))
    print(str(buy_orders_f))
    
    print("Starting prepare")
    # Go through your orders and check if there is another priced lower than yours. 
    def prepare():
        global n_orders_outofdate
        n_orders_outofdate = 0
        tolerance = 1e-5  # Tolerance for avoidin float math problems
        prepared_data = []  # Store the typeID + updated_price tuples in a list. No need to store old price
        for typeID, order_price, updated_price in zip(sell_orders_f.index, sell_orders_f['price'], sell_orders_f['min_price']):
            min_price = min_prices.loc[typeID]
            print("Sells:","Type ID:", typeID, "Lowest Seller:", min_price, "Your Sell Order:", order_price, "Your updated price:", updated_price)
            # Use a tolerance-based equality check because maybe weird float math with bigger numbers? 
            if abs(min_price - order_price) > tolerance:
                n_orders_outofdate += 1
                prepared_data.append((typeID, updated_price))
        for typeID, order_price, updated_price in zip(buy_orders_f.index, buy_orders_f['price'], buy_orders_f['max_price']):
            max_price = max_prices.loc[typeID]
            print("Buys:","Type ID:", typeID, "Highest Buyer:", max_price, "Your Buy Order:", order_price, "Your updated price:", updated_price)
            if abs(max_price - order_price) > tolerance:
                n_orders_outofdate += 1
                prepared_data.append((typeID, updated_price))
        return prepared_data
        

    prepared_data = prepare()
    print("Prepare done.",n_orders_outofdate,"orders need to be updated.")
    print("Press V to open the next item on market. Press ESC to cancel")

    def handle_paste():
        global n_orders_outofdate
        print("orders to be updated:",n_orders_outofdate)
        n_orders_outofdate = n_orders_outofdate-1
        try:
            typeID, updated_price = prepared_data.pop(0)
        except IndexError:
            print("All items updated. Returning OK signal.")
            global listen_for_keyboard
            listen_for_keyboard = False
            return False

        print(f"Updating itemID {typeID}. New price is {updated_price}")

        pyperclip.copy(str(updated_price))

        params = {'type_id': typeID}
        res = session.post('https://esi.evetech.net/latest/ui/openwindow/marketdetails/', params=params)

        #print("ESI Status code",res.status_code)
        
    def on_activate(key):
        try:
            if key.char == 'v':
                handle_paste()
            else:
                return True # If some other key than V pressed, ignore. 
            if n_orders_outofdate == 0:
                print("All items updated. Returning to the main menu.")
                return False # If there are no more oreders to be updated, stop listening for keys and return to main menu.
            else:
                return True
        except AttributeError:
            return True

    def on_release(key):
        if key == keyboard.Key.esc:
            # Stop listener
            return False
    
    with keyboard.Listener(
            on_press=on_activate,
            on_release=on_release) as listener:
        listener.join()

if __name__ == '__main__':
    from settings import settings
    update_all(settings)
