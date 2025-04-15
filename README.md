# LeetCode Crawler

A comprehensive tool to crawl LeetCode discussion forums for interview questions, particularly focusing on those from Google interviews. This tool extracts valuable information from the discussions, organizes it by month, and allows exporting to various formats including CSV and Google Sheets.

## Features

- Crawl interview questions from LeetCode discussions
- Filter by company tags (default: Google)
- Extract detailed information including problem links
- Group results by month
- Save to CSV files for easy analysis
- Export to Google Sheets with formatted worksheets
- Command-line interface for flexible usage

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/mcp-leetcode-crawler.git
   cd mcp-leetcode-crawler
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

## Usage

### Basic Usage

Run the crawler with default settings:

```
python crawler.py
```

This will:
1. Crawl LeetCode discussion forums for Google interview questions
2. Save all posts to a single CSV file (`leetcode_interview_questions.csv`)
3. Group posts by month and save them to separate CSV files in the `output` directory

### Command-line Interface

For more control, use the CLI:

```
python cli.py --company google --pages 20 --output results.csv --output-dir monthly_data
```

Available options:
- `--company`: Company tag to filter questions (default: google)
- `--pages`: Number of pages to crawl (default: 10)
- `--output`: Output CSV file path (default: leetcode_interview_questions.csv)
- `--output-dir`: Directory for monthly output files (default: output)
- `--verbose`: Enable verbose logging
- `--category`: Category to crawl (default: interview-question)

### Export to Google Sheets

To export your data to Google Sheets:

1. Set up Google Sheets API credentials:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project
   - Enable the Google Sheets API
   - Create OAuth 2.0 credentials (Desktop application)
   - Download the credentials as `credentials.json` to your project directory

2. Run the exporter script:
   ```
   # Export a single CSV file
   python google_sheets_exporter.py --csv leetcode_interview_questions.csv --name "Google Interview Questions"
   
   # Export all monthly data
   python google_sheets_exporter.py --monthly --name "LeetCode Interview Questions by Month"
   ```

### Automated Run

Use the provided shell scripts:

```
# Basic run (CSV only)
./run.sh

# Run with Google Sheets export
./run_with_sheets.sh
```

## Project Structure

- `crawler.py` - Main crawler implementation
- `cli.py` - Command-line interface
- `google_sheets_exporter.py` - Utility to export data to Google Sheets
- `run.sh` - Shell script for basic execution
- `run_with_sheets.sh` - Shell script for execution with Google Sheets export
- `requirements.txt` - Python dependencies

## Customization

You can modify the scripts to:
- Change the company tags (e.g., from "google" to "facebook", "amazon", etc.)
- Adjust the number of pages to crawl
- Modify the output format
- Change how the data is grouped and organized

## Future Improvements

- [ ] Add support for multiple company tags simultaneously
- [ ] Implement automated scheduling for regular data updates
- [ ] Add a web interface for easier interaction
- [ ] Integrate with other data storage solutions (e.g., MongoDB)
- [ ] Add data visualization capabilities
- [ ] Implement full-text search for the collected data

## License

MIT
