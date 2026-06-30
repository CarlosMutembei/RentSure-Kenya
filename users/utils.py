import requests

def geocode_address(query):
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        'q': query,
        'format': 'json',
        'limit': 1,
        'addressdetails': 1,
    }
    try:
        resp = requests.get(url, params=params, headers={'User-Agent': 'RentsureKenya'}, timeout=5)
        data = resp.json()
        if data:
            addr = data[0]
            lat = float(addr['lat'])
            lon = float(addr['lon'])
            address = addr.get('address', {})
            town = address.get('town') or address.get('city') or address.get('village') or address.get('suburb') or ''
            county = address.get('county') or address.get('state_district') or ''
            return {
                'lat': lat,
                'lng': lon,
                'town': town,
                'county': county,
            }
    except Exception as e:
        print(f"Geocoding error: {e}")
    return None