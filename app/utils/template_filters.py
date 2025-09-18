# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/utils/template_filters.py

import re

def strip_tcid_prefix(tcid):
    """
    A Jinja2 filter that removes leading non-numeric characters from a TCID string.
    e.g., 'C12345' -> '12345', 'TC12345' -> '12345'
    """
    if not tcid or not isinstance(tcid, str):
        return tcid
    match = re.search(r'\d', tcid)
    return tcid[match.start():] if match else tcid

def sort_details(details):
    """
    Sorts a list of TCID details (dictionaries) for the planning sub-table.
    - Sorts by engine, then region.
    - 'NoEngine' and 'NoRegion' are sorted last.
    """
    def sort_key(item):
        engine = item.get('engine')
        region = item.get('region')
        return (
            engine is None or engine == 'NoEngine',
            engine,
            region is None or region == 'NoRegion',
            region
        )
    return sorted(details, key=sort_key)