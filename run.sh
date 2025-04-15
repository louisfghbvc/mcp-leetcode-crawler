#!/bin/bash

# Install dependencies
pip install -r requirements.txt

# Create output directory
mkdir -p output

# Run the crawler
python crawler.py

echo "Crawler execution completed. Check the output directory for results."
