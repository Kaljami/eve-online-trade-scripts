import os
import pickle


# Pre-calculated mapping of typeID -> item name. This comes from typeID.yaml, part of the Static Data Export.
def get_item_names():
    with open(os.path.join('static', 'sde_names.pkl'), 'rb') as fp:
        return pickle.load(fp)


def get_item_sizes():
    with open(os.path.join('static', 'sde_sizes.pkl'), 'rb') as fp:
        return pickle.load(fp)
