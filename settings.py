from recordclass import recordclass
import yaml

path_to_settings = 'settings.yaml'

with open(path_to_settings) as fp:
    y = yaml.safe_load(fp)
    y['cache_all'] = y['cache_all'].lower() == 'true'
    y['hide_existing'] = y['hide_existing'].lower() == 'true'
    # Define fields and their types
    field_types = {
        'cache_all': bool,
        'hide_existing': bool,
        'source_hub': str,
        'source_order_type': str,
        'dest_hub': str,
        'dest_order_type': str,
        'days_history': int,
        'bogus_threshold': int,
    }

    # Create a recordclass dynamically based on field_types
    Settings = recordclass('Settings', field_types)
    settings = Settings(**y)
    print("loaded settings:")
    print(settings)


def save_to_file(settings):
    with open(path_to_settings, 'w') as fp:
        fp.write(yaml.dump(settings))
