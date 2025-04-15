#!/usr/bin/env python3
"""
Google Sheets Exporter for LeetCode Crawler
-------------------------------------------
This script exports crawled LeetCode interview questions to Google Sheets.
"""

import os
import pandas as pd
import logging
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("sheets_exporter.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

class GoogleSheetsExporter:
    def __init__(self, token_path='token.json', credentials_path='credentials.json'):
        self.token_path = token_path
        self.credentials_path = credentials_path
        self.creds = None
        self.service = None
        
    def authenticate(self):
        """Authenticate with Google Sheets API."""
        # The file token.json stores the user's access and refresh tokens
        if os.path.exists(self.token_path):
            self.creds = Credentials.from_authorized_user_info(
                json.loads(open(self.token_path).read()), SCOPES)
        
        # If there are no (valid) credentials available, let the user log in.
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES)
                self.creds = flow.run_local_server(port=0)
            
            # Save the credentials for the next run
            with open(self.token_path, 'w') as token:
                token.write(self.creds.to_json())
        
        self.service = build('sheets', 'v4', credentials=self.creds)
        logger.info("Successfully authenticated with Google Sheets API")
    
    def create_spreadsheet(self, title="LeetCode Interview Questions"):
        """Create a new Google Sheet."""
        spreadsheet = {
            'properties': {
                'title': title
            }
        }
        
        spreadsheet = self.service.spreadsheets().create(body=spreadsheet,
                                                        fields='spreadsheetId').execute()
        spreadsheet_id = spreadsheet.get('spreadsheetId')
        logger.info(f"Created spreadsheet with ID: {spreadsheet_id}")
        
        return spreadsheet_id
    
    def add_sheet(self, spreadsheet_id, title):
        """Add a new sheet to an existing spreadsheet."""
        batch_update_request = {
            "requests": [
                {
                    "addSheet": {
                        "properties": {
                            "title": title
                        }
                    }
                }
            ]
        }
        
        try:
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body=batch_update_request).execute()
            logger.info(f"Added sheet '{title}' to spreadsheet {spreadsheet_id}")
            return True
        except Exception as e:
            logger.error(f"Error adding sheet '{title}': {e}")
            return False
    
    def write_dataframe_to_sheet(self, spreadsheet_id, sheet_name, df):
        """Write a pandas DataFrame to a specific sheet."""
        # Convert DataFrame to values list
        values = [df.columns.tolist()]  # Header row
        values.extend(df.values.tolist())  # Data rows
        
        body = {
            'values': values
        }
        
        try:
            self.service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_name}!A1",
                valueInputOption='RAW',
                body=body
            ).execute()
            logger.info(f"Wrote {len(df)} rows to sheet '{sheet_name}'")
            return True
        except Exception as e:
            logger.error(f"Error writing to sheet '{sheet_name}': {e}")
            return False
    
    def format_header_row(self, spreadsheet_id, sheet_name):
        """Format the header row to make it bold and frozen."""
        requests = [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": self.get_sheet_id(spreadsheet_id, sheet_name),
                        "startRowIndex": 0,
                        "endRowIndex": 1
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {
                                "red": 0.9,
                                "green": 0.9,
                                "blue": 0.9
                            },
                            "textFormat": {
                                "bold": True
                            }
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat)"
                }
            },
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": self.get_sheet_id(spreadsheet_id, sheet_name),
                        "gridProperties": {
                            "frozenRowCount": 1
                        }
                    },
                    "fields": "gridProperties.frozenRowCount"
                }
            }
        ]
        
        body = {
            'requests': requests
        }
        
        try:
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body=body).execute()
            logger.info(f"Formatted header row for sheet '{sheet_name}'")
            return True
        except Exception as e:
            logger.error(f"Error formatting header row for sheet '{sheet_name}': {e}")
            return False
    
    def get_sheet_id(self, spreadsheet_id, sheet_name):
        """Get the sheet ID from its name."""
        spreadsheet = self.service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = spreadsheet.get('sheets', [])
        for sheet in sheets:
            if sheet.get("properties", {}).get("title") == sheet_name:
                return sheet.get("properties", {}).get("sheetId")
        return None
    
    def export_to_sheets(self, csv_path, spreadsheet_name=None):
        """Export data from a CSV file to Google Sheets."""
        # Read the CSV file
        df = pd.read_csv(csv_path)
        
        # Authenticate with Google Sheets
        self.authenticate()
        
        # Create a new spreadsheet or use an existing one
        if spreadsheet_name:
            spreadsheet_id = self.create_spreadsheet(spreadsheet_name)
        else:
            # Extract a name from the CSV filename
            base_name = os.path.basename(csv_path)
            spreadsheet_name = os.path.splitext(base_name)[0]
            spreadsheet_id = self.create_spreadsheet(spreadsheet_name)
        
        # Add a sheet and write data to it
        sheet_name = "Interview Questions"
        self.add_sheet(spreadsheet_id, sheet_name)
        self.write_dataframe_to_sheet(spreadsheet_id, sheet_name, df)
        self.format_header_row(spreadsheet_id, sheet_name)
        
        logger.info(f"Exported data to spreadsheet: https://docs.google.com/spreadsheets/d/{spreadsheet_id}")
        return spreadsheet_id
    
    def export_monthly_data(self, directory="output", spreadsheet_name="LeetCode Interview Questions by Month"):
        """Export all monthly CSV files to a single Google Sheet with multiple tabs."""
        # Authenticate with Google Sheets
        self.authenticate()
        
        # Create a new spreadsheet
        spreadsheet_id = self.create_spreadsheet(spreadsheet_name)
        
        # Get all CSV files in the directory
        csv_files = [f for f in os.listdir(directory) if f.endswith('.csv')]
        
        for csv_file in csv_files:
            # Extract month from filename (assuming format: leetcode_google_interviews_YYYY-MM.csv)
            month_str = csv_file.replace("leetcode_google_interviews_", "").replace(".csv", "")
            sheet_name = month_str  # Use YYYY-MM as sheet name
            
            # Read the CSV file
            csv_path = os.path.join(directory, csv_file)
            df = pd.read_csv(csv_path)
            
            # Add a sheet for this month
            self.add_sheet(spreadsheet_id, sheet_name)
            
            # Write data to the sheet
            self.write_dataframe_to_sheet(spreadsheet_id, sheet_name, df)
            
            # Format the header row
            self.format_header_row(spreadsheet_id, sheet_name)
        
        logger.info(f"Exported all monthly data to spreadsheet: https://docs.google.com/spreadsheets/d/{spreadsheet_id}")
        return spreadsheet_id

if __name__ == "__main__":
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="Export LeetCode crawler data to Google Sheets")
    parser.add_argument("--csv", help="Path to the CSV file to export")
    parser.add_argument("--monthly", action="store_true", help="Export all monthly CSV files in the output directory")
    parser.add_argument("--name", help="Name for the Google Sheet")
    
    args = parser.parse_args()
    
    exporter = GoogleSheetsExporter()
    
    if args.monthly:
        exporter.export_monthly_data(spreadsheet_name=args.name or "LeetCode Interview Questions by Month")
    elif args.csv:
        exporter.export_to_sheets(args.csv, args.name)
    else:
        print("Error: Please specify either --csv or --monthly option.")
        parser.print_help()
