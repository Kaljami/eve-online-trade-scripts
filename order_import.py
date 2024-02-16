import glob
import os

# not used since we can pull the player orders from ESI
def get_player_orders_file():
    path = glob.glob(os.path.expanduser(os.path.join('~', 'Documents', 'EVE', 'logs', 'Marketlogs', '*')))

    latest_log = max(path, key=os.path.getctime)
    print("found market log" + latest_log)
    return latest_log
