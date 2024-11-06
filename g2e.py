import sys
import time
import gpxpy
import pandas as pd
import geopy.distance
import numpy as np
import requests
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

# you can get an API key at https://www.gpxz.io/
# if you want to use the altitude included in the GPX file,
# just set USE_GPXZ to False

# --- Configuration Variables ---
PLOT_DATA = True
HIKER_MASS = 80
USE_GPXZ = True
GPXZ_API_KEY = "insert your API key here"  # Replace with your API Key
GPXZ_BATCH_SIZE = 50
REQUESTS_PER_SECOND = 1  # Limit for the free tier
REQUESTS_PER_DAY = 100 # Limit per day for the free tier
current_day_requests = 15 # Requests today

# Higher resolution elevation data with GPXZ
def enhance_elevation(lats, lons, api_key, batch_size):
    global current_day_requests
    elevations = []
    # splitting the data into chunks that can be sent to the API
    n_chunks = int(len(lats) // batch_size) + 1
    lat_chunks = np.array_split(lats, n_chunks)
    lon_chunks = np.array_split(lons, n_chunks)
    
    # Here we send each chunk to gpxz, respecting the rate limit
    for lat_chunk, lon_chunk in zip(lat_chunks, lon_chunks):
        if current_day_requests >= REQUESTS_PER_DAY:
            print("Daily GPXZ request limit reached. Using original elevation data.")
            return None 
        latlons = '|'.join(f'{lat},{lon}' for lat, lon in zip(lat_chunk, lon_chunk))
        data = {'latlons': latlons}
        
        while True: # If we get a too many requests error, wait and then retry to get the chunk
            if current_day_requests < REQUESTS_PER_DAY: # check if we went over our daily limit
                current_day_requests += 1
                response = requests.post(
                    'https://api.gpxz.io/v1/elevation/points',
                    headers={'x-api-key': api_key},
                    data=data,
                    )
                try:
                    response.raise_for_status()
                    elevations += [r['elevation'] for r in response.json()['results']]
                    print(".", end='', flush=True)
                    time.sleep(1/REQUESTS_PER_SECOND)  # Respect rate limit
                    break # Exit retry loop if successful
                except requests.exceptions.HTTPError as e:
                    if response.status_code == 429:  # Too Many Requests
                        retry_after = int(response.headers.get('Retry-After', 2)) # Get retry time from header
                        print("!", end='', flush=True)
                        #print(f"Rate limited by GPXZ. Retrying after {retry_after} seconds...") #uncomment this if you want a more descriptive error than "!"
                        time.sleep(retry_after) # Wait specified duration and get back in the loop
                    else:
                        print("")
                        print(f"Error fetching elevation data: {e}")
                        return None
            else: # we did get over our daily limit :(
                print("")
                print("Daily GPXZ request limit reached. Using original elevation data.")
                return None
    print("")
    return elevations

def calculate_calories(gpx_path, mass, api_key, batch_size):
    # Loading the gpx file
    try:
        print("opening file...")
        with open(gpx_path) as file:
            gpx = gpxpy.parse(file)
    except FileNotFoundError:
        print(f"Error: GPX file not found at {gpx_path}")
        return None, None, None  # Return None in case of error
    
    # getting the points from the file
    print("extracting the points...")
    points = []
    for segment in gpx.tracks[0].segments:
        print(":", end='', flush=True)
        for p in segment.points:
            print(".", end='', flush=True)
            points.append({
                'time': p.time,
                'latitude': p.latitude,
                'longitude': p.longitude,
                'elevation': p.elevation,
            }) 
    df = pd.DataFrame.from_records(points)
    print("")
    
    coords = [(p.latitude, p.longitude) for p in df.itertuples()]
    df['distance'] = [0] + [geopy.distance.distance(from_, to).m for from_, to in zip(coords[:-1], coords[1:])]
    df['duration'] = df.time.diff().dt.total_seconds().fillna(0)
    
    if GPXZ_API_KEY != "insert your API key here" and USE_GPXZ:
        print("Getting higher resolution data with gpxz...")
        df['elevation_gpxz'] = enhance_elevation(df.latitude, df.longitude, api_key, batch_size)
    else:
        df['elevation_gpxz'] = None
    
    # Fallback to original data
    if df['elevation_gpxz'].isnull().any():
        if USE_GPXZ and GPXZ_API_KEY == "insert your API key here":
            print("You don't have an API key! Using the original data")
        elif USE_GPXZ and GPXZ_API_KEY != "insert your API key here":
            print("Using original elevation data due to errors fetching from GPXZ or missing data.")
        else:
            print("skipping gpxz")
        df['elevation_gpxz'] = df['elevation']
    
    #getting the rise from one point to the next
    df['rise'] = df['elevation_gpxz'].diff().fillna(0)

    # Calorie Calculation
    s = (df.distance / df.duration).fillna(0)
    g = (df.rise / df.distance).fillna(0) * 100

    EE = 1.44
    EE += 1.94 * s ** 0.43
    EE += 0.24 * s ** 4
    EE += 0.34 * s * g * (1 - 1.05 ** (1 - 1.1 ** (g + 32)))

    joules_in_food_calorie = 4184
    J = EE * mass * df.duration #Joules used
    C = J / joules_in_food_calorie #Converting the joules to calories

    total_calories = C.sum()
    return total_calories, df, J, C
    
# calling the functions
GPX_FILE = sys.argv[1]
total_calories, df, J, C = calculate_calories(GPX_FILE, HIKER_MASS, GPXZ_API_KEY, GPXZ_BATCH_SIZE)
if total_calories is not None:
    print("")
    print(f"Total calories used: {round(total_calories, 2)}")
    print(f"Total Joules used: {round(sum(J), 2)}")
    print(f"Wh used: {round(sum(J)/3600, 2)}")

# Drawing the nice plot
if PLOT_DATA:
    # Calculate cumulative distance for x-axis
    df['cumulative_distance'] = df['distance'].cumsum() / 1000  # in km
    
    # Plotting power consumption rate and Elevation Profile
    fig, ax1 = plt.subplots(figsize=(10, 5))  # Adjust figure size as needed
     
    # Power used by your legs rate as a moving average
    smoothing_value = 1  # Adjust window size for smoothing
    df['power'] = (df['duration'] * 0).fillna(0)
    df['power'] = J.rolling(window=smoothing_value, center=True).mean()/df['duration']
    
    ax1.plot(df['cumulative_distance'], df['power'], color='black', label='Power (Watts)')
    ax1.set_xlabel('Distance (km)')
    ax1.set_ylabel('Joules/s (Watts)', color='black')
    ax1.tick_params(axis='y', labelcolor='black')
    
    ax2 = ax1.twinx()  # Create a second y-axis sharing the same x-axis
    ax2.fill_between(df['cumulative_distance'], df['elevation_gpxz'], color='lightgray', alpha=0.5, label="elevation profile") # Added color
    
    # Show the plot and the labels
    plt.title('Power consumption and Elevation Profile') # Added a title
    fig.legend(loc="upper right", bbox_to_anchor=(1,1), bbox_transform=ax1.transAxes) # Added bbox_to_anchor
    plt.show()
