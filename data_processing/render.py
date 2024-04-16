import pandas as pd
import os

url = os.path.join('render', 'output.html')


def render_to_html(summary):
    # Make pretty
    summary.index.name = None
    pd.options.display.float_format = '{:20,.2f}'.format
    formatters = {
        'Margin': '{:,.2%}'.format,
        #'typeID': '{:05}'.format,
        'type_id': '<a href="https://esi.evetech.net/latest/ui/openwindow/marketdetails/?type_id={:05}">{0:05}</a>'.format, # Doesn't seem to do anything. TODO: make clickable link
    }

    summary = summary[[
        'typeID', 'Total Profit', 'Source price',
        'Destination price', 'Profit', 'Margin',
        'Daily Volume', 'Haul Size', 'Units available', 'Average Price', 'ISK p m3'
    ]]

    # Output to HTML table
    with open(url, 'w+') as fp:
        fp.write('<link rel="stylesheet" href="style.css">')
        fp.write(summary.to_html(
            formatters=formatters,
            bold_rows=False,
            escape=False  # Disable HTML escaping to allow the anchor tags
        ))

    return url
