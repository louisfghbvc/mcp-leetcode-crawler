#!/bin/bash

# Install dependencies
pip install -r requirements.txt

# Create output directory
mkdir -p output

# Run the crawler
python crawler.py

echo "Crawler execution completed. Check the output directory for results."

# Check if credentials.json exists
if [ -f "credentials.json" ]; then
    echo "Found Google API credentials. Exporting to Google Sheets..."
    
    # Export to Google Sheets
    python google_sheets_exporter.py --monthly --name "LeetCode Google Interview Questions"
    
    echo "Data exported to Google Sheets."
else
    echo ""
    echo "To export to Google Sheets, you need to:"
    echo "1. Go to Google Cloud Console (https://console.cloud.google.com/)"
    echo "2. Create a new project"
    echo "3. Enable the Google Sheets API"
    echo "4. Create OAuth 2.0 credentials (Desktop application)"
    echo "5. Download the credentials as 'credentials.json' to this directory"
    echo "6. Run: python google_sheets_exporter.py --monthly"
fi
