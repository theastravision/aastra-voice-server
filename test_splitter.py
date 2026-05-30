import sys
import os

# Add the current directory to sys.path so we can import streaming.stream_filter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from streaming.stream_filter import StreamFilterAndSplitter

def run_test():
    # Test 1: Standard sentence with a <think> tag
    print("--- Test 1: Simulation (Standard with <think>) ---")
    splitter = StreamFilterAndSplitter(first_chunk_min=40, next_chunk_min=60)
    text1 = "Hello there! <think>I should calculate 1.5 million.</think> Your refund of 1.5 million is approved. Dr. Smith will see you now."
    tokens = [text1[i:i+3] for i in range(0, len(text1), 3)]
    for token in tokens:
        for chunk in splitter.push(token):
            print(f"CHUNK: '{chunk}'")
    remainder = splitter.flush()
    if remainder:
        print(f"REMAINDER: '{remainder}'")
        
    # Test 2: Tag Split Across Tokens
    print("\n--- Test 2: Tag Fragment Splitting ---")
    splitter = StreamFilterAndSplitter(first_chunk_min=40, next_chunk_min=60)
    tokens = [
        "Hi, let me check ",
        "<th",
        "ink> processing ",
        "</t",
        "hink>",
        "Your account is fine. We will contact you soon."
    ]
    for token in tokens:
        for chunk in splitter.push(token):
            print(f"CHUNK: '{chunk}'")
    remainder = splitter.flush()
    if remainder:
        print(f"REMAINDER: '{remainder}'")

    # Test 3: Markdown and Emoji Stripping
    print("\n--- Test 3: Markdown Stripping ---")
    splitter = StreamFilterAndSplitter(first_chunk_min=20, next_chunk_min=40)
    text3 = "This is *important* text! `Code snippet`. ~strikethrough~. Let's see what happens next. Have a nice day!"
    tokens = [text3[i:i+5] for i in range(0, len(text3), 5)]
    for token in tokens:
        for chunk in splitter.push(token):
            print(f"CHUNK: '{chunk}'")
    remainder = splitter.flush()
    if remainder:
        print(f"REMAINDER: '{remainder}'")
        
    # Test 4: Extremely long text without punctuation (Fallback mechanism)
    print("\n--- Test 4: Extreme Long Text Fallback ---")
    splitter = StreamFilterAndSplitter(first_chunk_min=40, next_chunk_min=100)
    text4 = "This is a very long sequence of words that just keeps going on and on and on and on and on without any punctuation whatsoever to stop it so the system will eventually have to split it based on the fallback space mechanism once it exceeds the two hundred and fifty character threshold let us see if it works as intended when we stream it."
    tokens = [text4[i:i+4] for i in range(0, len(text4), 4)]
    for token in tokens:
        for chunk in splitter.push(token):
            print(f"CHUNK: '{chunk}'")
    remainder = splitter.flush()
    if remainder:
        print(f"REMAINDER: '{remainder}'")

if __name__ == "__main__":
    run_test()
