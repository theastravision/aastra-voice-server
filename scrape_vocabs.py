import os
import csv
import time
import requests

def scrape_hinglish_dataset(output_csv='data/vocab/hinglish_conversations.csv'):
    base_url = "https://datasets-server.huggingface.co/rows"
    params = {
        "dataset": "Abhishekcr448/Hinglish-Everyday-Conversations-1M",
        "config": "default",
        "split": "train",
        "offset": 0,
        "length": 100
    }
    
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    
    # Determine the starting offset and file mode based on existing data
    file_exists = os.path.exists(output_csv)
    offset = 0
    total_rows_scraped = 0
    
    if file_exists:
        try:
            with open(output_csv, mode='r', encoding='utf-8') as csv_file:
                # Count existing lines (minus header) to estimate the last offset
                existing_lines = sum(1 for row in csv.reader(csv_file))
                if existing_lines > 1:
                    total_rows_scraped = existing_lines - 1
                    # Round down to the nearest hundred to prevent missing rows if a batch was incomplete
                    offset = (total_rows_scraped // 100) * 100
                    print(f"Resuming script. Found existing file with {total_rows_scraped} rows. Starting back from offset: {offset}...")
        except Exception as e:
            print(f"Could not read existing file cleanly, starting from 0. Error: {e}")
            file_exists = False
            
    # Open file: Use append 'a' if file exists and we are resuming, otherwise write 'w'
    file_mode = 'a' if (file_exists and offset > 0) else 'w'
    
    with open(output_csv, mode=file_mode, encoding='utf-8', newline='') as csv_file:
        writer = csv.writer(csv_file)
        
        # Write headers only if creating a new file
        if file_mode == 'w':
            writer.writerow(['input', 'output'])
        else:
            # If resuming, truncate the file to the exact offset point to prevent row duplication
            csv_file.seek(0, 2) # Move to end of file
            
        backoff_time = 5  # Start with a 5-second wait if rate-limited
        
        while True:
            print(f"Fetching rows starting from offset: {offset}...")
            params['offset'] = offset
            
            try:
                response = requests.get(base_url, params=params)
                
                # Handle Rate Limiting (HTTP 429) cleanly with exponential backoff
                if response.status_code == 429:
                    print(f"Rate limited (429). Waiting {backoff_time} seconds before retrying...")
                    time.sleep(backoff_time)
                    backoff_time = min(backoff_time * 2, 60)  # Double the wait time, cap it at 60 seconds
                    continue # Retry the same offset block
                
                # Stop if we hit other critical errors (e.g., 404, 500)
                if response.status_code != 200:
                    print(f"Failed to fetch data. Status code: {response.status_code}")
                    break
                    
                # Reset backoff time on a successful request
                backoff_time = 5
                
                data = response.json()
                rows = data.get('rows', [])
                
                if not rows:
                    print("No more rows found. Scraping completed.")
                    break
                
                # Extract input and output
                for row_data in rows:
                    row_content = row_data.get('row', {})
                    input_text = row_content.get('input', '')
                    output_text = row_content.get('output', '')
                    
                    writer.writerow([input_text, output_text])
                
                rows_fetched = len(rows)
                total_rows_scraped += rows_fetched
                print(f"Successfully scraped {rows_fetched} rows (Total tracked: {total_rows_scraped})")
                
                if rows_fetched < 100:
                    print("Reached the final batch of the dataset.")
                    break
                    
                offset += 100
                
                # Base cooling delay between successful requests
                time.sleep(1.0) 
                
            except Exception as e:
                print(f"An error occurred: {e}")
                print("Waiting 10 seconds before retrying connection...")
                time.sleep(10)
                continue

    print(f"\nExecution finished. Progress preserved in '{output_csv}'.")

if __name__ == '__main__':
    scrape_hinglish_dataset()