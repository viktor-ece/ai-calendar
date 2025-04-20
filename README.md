# AI Calendar Assistant

An intelligent calendar management system that combines ICS calendar parsing, AI-powered scheduling suggestions, and Google Calendar integration.

## Features

- **Multi-Calendar Support**: Fetch and combine events from multiple Google Calendars
- **Smart Scheduling**: AI-powered suggestions for optimal event timing
- **Google Calendar Integration**: Seamlessly create events in Google Calendar
- **Recurring Event Handling**: Full support for recurring events and exceptions
- **Timezone-Aware**: Proper handling of timezones across all operations
- **Interactive Feedback**: Refine scheduling suggestions through natural language feedback

## Components

### 1. Google Calendar API (`google_calendar_api.py`)
- Manages Google Calendar authentication
- Creates and manages calendar events
- Handles OAuth2 flow

### 2. LLM Scheduler (`llm_scheduler.py`)
- Formats events for AI processing
- Generates intelligent scheduling suggestions
- Handles user feedback and constraints
- Uses Google's Gemini AI model

### 3. Calendar Parser (`calendar_parser.py`) (currently not used in the main application)
- Parses ICS calendar files 
- Handles recurring events and exceptions
- Supports multiple calendars
- Timezone-aware event processing

### 4. Main Application (`main.py`)
- Orchestrates all components
- Provides interactive command-line interface
- Manages user interaction and feedback

## Prerequisites

- Python 3.8 or higher
- Google Cloud Platform account
- Google Calendar API enabled
- Google Gemini API access

## Installation

1. Clone the repository:
```bash
git clone https://github.com/victor-ece/ai-calendar.git
cd ai-calendar
```

2. Execute the setup script (recommended for first-time users):
```bash
chmod +x setup.sh
./setup.sh
```

3. Set up the environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

4. Set up Google Calendar API:
   - Go to Google Cloud Console
   - Create a new project
   - Enable Google Calendar API
   - Create OAuth 2.0 credentials
   - Download credentials and save as `credentials.json`

5. Set up Google Gemini API:
   - Get your API key from Google AI Studio
   - Create a `.env` file with:
   ```
   GOOGLE_API_KEY=your_api_key_here
   ```

## Usage

1. Set up your Google Calendar integration:
   - Ensure you have valid `credentials.json` in the project directory
   - Run the application to authenticate with Google Calendar
   - Select the calendars you want to manage by specifying their IDs in the `main.py` file.

2. Run the application with an optional command-line argument to use hardcoded values.

### Usage

To use hardcoded values:
```bash
python main.py -u
```

To prompt for timezone selection:
```bash
python main.py -t
```

To prompt for input:
```bash
python main.py
```

If the `-u` flag is not provided, the application will prompt for the start date and the number of days to fetch events. The start date must be in the format `YYYY-MM-DD`, and the number of days must be a positive integer.

If the `-t` flag is provided, the application will prompt you to choose between using your system timezone or entering a custom timezone. If not provided, it will use your system timezone by default.

### Note
To read events from multiple calendars, you must specify the calendar IDs in the `main.py` file under the `selected_calendars` variable.

## Configuration

### Calendar Settings
- `start_date`: Initial date for calendar parsing
- `days_ahead`: Number of days to look ahead
- `timezone`: Default timezone for events
- `selected_calendars`: List of Google Calendar IDs to manage

### AI Settings
- Model: Gemini 2.0 Flash Thinking
- Context window: Current schedule + feedback history
- Response format: Structured event details

## File Structure

```
ai-calendar/
├── calendar_parser.py    # ICS calendar parsing
├── llm_scheduler.py      # AI scheduling logic
├── google_calendar_api.py # Google Calendar integration
├── main.py              # Main application
├── requirements.txt     # Python dependencies
├── setup.sh            # Quick setup script
├── .env                # Environment variables
├── credentials.json    # Google OAuth credentials
├── token.json         # OAuth token storage
├── main.ics           # Main calendar file
```

## Security

- OAuth tokens are stored locally
- API keys are managed through environment variables
- Calendar data is processed locally
- No data is stored permanently

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support, please open an issue in the GitHub repository. 