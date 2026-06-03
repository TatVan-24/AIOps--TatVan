import pandas as pd
import queue
import threading
import time
import os

file_path = 'https://raw.githubusercontent.com/numenta/NAB/master/data/realKnownCause/machine_temperature_system_failure.csv'
output_file = "features.parquet"
window_size = 12

stream_queue = queue.Queue()

def producer():
    try: 
        df = pd.read_csv(file_path)
        for idx, row in df.iterrows():
            stream_queue.put(row.to_dict())

        stream_queue.put(None)
        print(f'Producer - Finished whole data into the queue')
    except FileNotFoundError:
        print(f'Producer - ERROR, no CSV file found!')
        stream_queue.put(None)

def consumer():
    buffer = []
    while True:
        data = stream_queue.get()

        if data is None:
            break

        buffer.append(data)

    if not buffer:
        print(f'Consumer - Being not data enough to process!')
        return
    
    print(f'Consumer - Received {len(buffer)} records, Beginning feature detection')

    df_stream = pd.DataFrame(buffer)
    df_stream['timestamp'] = pd.to_datetime(df_stream['timestamp'])
    df_stream = df_stream.sort_values('timestamp').reset_index(drop=True)

    df_stream['rolling_mean_1h'] = df_stream['value'].rolling(window=window_size).mean()
    
    df_stream['rolling_std_1h'] = df_stream['value'].rolling(window=window_size).std()
    
    df_stream['rate_of_change'] = df_stream['value'].pct_change()
    
    df_stream.to_parquet(output_file, index=False)
    print(f'Consumer - Successfully storing file into : {output_file}')


prod_thread = threading.Thread(target=producer)
cons_thread = threading.Thread(target=consumer)

cons_thread.start()
prod_thread.start()

prod_thread.join()
cons_thread.join()

print('Complete')

