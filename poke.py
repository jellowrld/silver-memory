import requests

def get_pokemon_name_to_id():
    print("Loading Pokémon list from PokéAPI...")
    url = "https://pokeapi.co/api/v2/pokemon?limit=10000"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        name_to_id = {}
        for entry in data['results']:
            name = entry['name']
            poke_details = requests.get(entry['url']).json()
            poke_id = poke_details['id']
            name_to_id[name] = poke_id
        print("Pokémon list loaded successfully.")
        return name_to_id
    except Exception as e:
        print(f"Error loading Pokémon list: {e}")
        return {}

def fetch_spawn_data_by_name(name, lat, lon, radius_km=3.0):
    pokemon_id = POKEMON_NAME_TO_ID.get(name.lower())
    if not pokemon_id:
        print(f"Unknown Pokémon: {name}")
        return

    url = "https://pokemap.net/api/v1/pokemon"
    params = {
        'lat': lat,
        'lng': lon,
        'radius': radius_km * 1000
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        pokemons = data.get("pokemons", [])

        matches = [p for p in pokemons if p['pokemon_id'] == pokemon_id]
        if not matches:
            print(f"No {name.title()} found within {radius_km} km.")
            return

        print(f"\n--- {name.title()} Spawns Near ({lat}, {lon}) ---")
        for p in matches:
            print(f"Location: ({p['latitude']}, {p['longitude']}), Disappears at: {p['disappear_time_formatted']}")
    except Exception as e:
        print(f"Failed to fetch spawn data: {e}")

# Example usage
if __name__ == "__main__":
    POKEMON_NAME_TO_ID = get_pokemon_name_to_id()
    if POKEMON_NAME_TO_ID:
        search_name = input("Enter Pokémon name: ").strip()
        fetch_spawn_data_by_name(search_name, lat=40.7580, lon=-73.9855)  # Times Square, NYC