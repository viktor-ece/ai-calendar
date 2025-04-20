import os.path
import datetime 
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build 
from googleapiclient.errors import HttpError 
from typing import List, Dict, Any
import pytz
from datetime import datetime, timedelta, time

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_PATH = "token.json" 
CREDENTIALS_PATH = "credentials.json" 

def format_event_time(dt: datetime, timezone_str: str) -> Dict[str, Any]:
    """
    Format a datetime for human-readable display in a specific timezone.
    Returns a dictionary with various formatted time components:
    - Full datetime object
    - Day of week
    - Date string
    - Time string
    - Combined formatted string
    """
    target_tz = pytz.timezone(timezone_str)
    local_dt = dt.astimezone(target_tz)
    day_of_week = local_dt.strftime('%A')
    date_str = local_dt.strftime('%B %d, %Y')
    time_str = local_dt.strftime('%I:%M %p').lstrip('0')
    return {
        'datetime': local_dt,
        'day_of_week': day_of_week,
        'date': date_str,
        'time': time_str,
        'formatted': f"{day_of_week}, {date_str} at {time_str}"
    }   

def get_calendar_credentials():
    """Gets valid user credentials from storage or initiates login flow."""
    creds = None
    # Check if token file exists
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except FileNotFoundError:
            print(f"Error: Token file '{TOKEN_PATH}' not found. Please authenticate again.")
            return None
        except ValueError as e:
            print(f"Error loading token file: {e}. Deleting potentially corrupt token.")
            os.remove(TOKEN_PATH)  
            return None

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                print("Credentials expired, refreshing...")
                creds.refresh(Request())
            except Exception as e:
                print(f"Error refreshing token: {e}. Re-authenticating.")
                creds = None # Force re-authentication
        # Only run the flow if creds are still None (initial run or refresh failed)
        if not creds:
            try:
                print("No valid credentials found, initiating authentication flow...")
                if not os.path.exists(CREDENTIALS_PATH):
                    print(f"Error: {CREDENTIALS_PATH} not found.")
                    print("Please download your OAuth client credentials.")
                    return None

                flow = InstalledAppFlow.from_client_secrets_file(
                    CREDENTIALS_PATH, SCOPES
                )

                # This version uses the local server but disables auto-browser opening.
                # It will print a URL. You MUST manually copy/paste this URL into
                # your browser, log in, and grant consent.
                # The local server running in the background will automatically
                # receive the authorization code via the redirect.
                print("Starting local server (browser launch disabled)...")
                creds = flow.run_local_server(port=0, open_browser=False)
                print("Authentication flow completed, credentials obtained.")

                # --- Commented out code for potentially fully automatic flow on Linux ---
                # On a Linux system with a GUI and correctly configured browser access (xdg-utils),
                # the following line *might* work fully automatically (open browser + get code):
                # print("Attempting automatic browser authentication...")
                # creds = flow.run_local_server(port=0)
                # print("Automatic authentication flow completed.")
                # --- End of commented out code ---

            except FileNotFoundError:
                print(f"Error: Credentials file '{CREDENTIALS_PATH}' not found. Please download your OAuth client credentials.")
                return None
            except Exception as e:
                print(f"Error during authentication flow: {e}")
                return None  # Failed to authenticate

        # Save the credentials for the next run (only if creds were newly obtained)
        if creds:
            try:
                with open(TOKEN_PATH, "w") as token:
                    token.write(creds.to_json())
                print(f"Credentials saved to {TOKEN_PATH}")
            except Exception as e:
                print(f"Error saving token: {e}")
            # Proceed even if saving failed, creds are valid for this session

    if creds and creds.valid:
         print("Credentials loaded successfully.")
         return creds
    else:
         print("Failed to obtain valid credentials.")
         return None

def create_event_from_llm_suggestion(event_data: dict, title: str, timezone: str = 'UTC') -> dict:
    """
    Creates a Google Calendar event from LLM suggestion data in the specified timezone.
    
    Args:
        event_data (dict): Dictionary containing event details from parse_llm_response
            Expected keys:
            - start_time: datetime object for start time
            - duration: Duration in hours
            - explanation: Event description/explanation
        title (str): Title for the event
        timezone (str): Target timezone string (e.g., 'Europe/Athens', 'UTC', 'America/New_York')
    
    Returns:
        dict: Created event details from Google Calendar API
    """
    creds = get_calendar_credentials()
    if not creds:
        raise Exception("Failed to get valid credentials")
    
    try:
        service = build('calendar', 'v3', credentials=creds)
        
        # Ensure start_time is in the target timezone
        target_tz = pytz.timezone(timezone)
        if event_data['start_time'].tzinfo is None:
            start_time = target_tz.localize(event_data['start_time'])
        else:
            start_time = event_data['start_time'].astimezone(target_tz)
        
        # Calculate end time in the same timezone
        end_time = start_time + timedelta(hours=event_data['duration'])
        
        event = {
            'summary': title,
            'description': event_data['explanation'],
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': timezone,
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': timezone,
            },
        }
        
        event = service.events().insert(calendarId='primary', body=event).execute()
        return event
        
    except HttpError as error:
        print(f"An error occurred while creating the event: {error}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

def get_events_from_google_calendar(start_date_str: str | None = None, days_ahead: int = 7, timezone: str = 'UTC', calendar_ids: List[str] | None = None) -> List[Dict[str, Any]]:
    """
    Fetch events from Google Calendar API and convert them to the target timezone.
    
    Args:
        start_date_str: Start date in YYYY-MM-DD format (optional)
        days_ahead: Number of days to look ahead
        timezone: Target timezone string (e.g., 'Europe/Athens', 'UTC', 'America/New_York')
        calendar_ids: List of calendar IDs to fetch events from. If None, uses primary calendar.
    
    Returns:
        List of events in the target timezone
    """
    creds = get_calendar_credentials()
    if not creds:
        raise Exception("Failed to get valid credentials")
    
    try:
        service = build('calendar', 'v3', credentials=creds)
        
        # Set the date window for event filtering
        if start_date_str:
            try:
                window_start = datetime.strptime(start_date_str, '%Y-%m-%d')
            except ValueError:
                print(f"Invalid date format: {start_date_str}. Using current date instead.")
                window_start = datetime.now()
        else:
            window_start = datetime.now()
        
        # Localize the window start to the target timezone
        target_tz = pytz.timezone(timezone)
        window_start = target_tz.localize(window_start)
        window_end = window_start + timedelta(days=days_ahead)
        
        # Convert to RFC3339 format for Google Calendar API
        time_min = window_start.astimezone(pytz.utc).isoformat()
        time_max = window_end.astimezone(pytz.utc).isoformat()
        
        # If no calendar IDs provided, use primary calendar
        if calendar_ids is None:
            calendar_ids = ['primary']
        
        all_events = []
        
        # Fetch events from each calendar
        for calendar_id in calendar_ids:
            try:
                # Get calendar name
                calendar = service.calendars().get(calendarId=calendar_id).execute()
                calendar_name = calendar.get('summary', 'Unknown Calendar')
                
                # Fetch events from this calendar
                events_result = service.events().list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                
                events = events_result.get('items', [])
                
                for event in events:
                    try:
                        # Get start and end times
                        start = event['start'].get('dateTime', event['start'].get('date'))
                        end = event['end'].get('dateTime', event['end'].get('date'))
                        
                        # Convert to datetime objects
                        if 'dateTime' in event['start']:
                            start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                            end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
                        else:
                            start_dt = datetime.combine(datetime.fromisoformat(start).date(), time(0, 0))
                            end_dt = datetime.combine(datetime.fromisoformat(end).date(), time(0, 0))
                        
                        # Convert to target timezone
                        if start_dt.tzinfo is None:
                            start_dt = target_tz.localize(start_dt)
                        else:
                            start_dt = start_dt.astimezone(target_tz)
                            
                        if end_dt.tzinfo is None:
                            end_dt = target_tz.localize(end_dt)
                        else:
                            end_dt = end_dt.astimezone(target_tz)
                        
                        # Format times for display
                        start_format = format_event_time(start_dt, timezone)
                        end_format = format_event_time(end_dt, timezone)
                        duration_minutes = int((end_dt - start_dt).total_seconds() / 60)
                        
                        # Check if this is a recurring event
                        is_recurring = 'recurringEventId' in event
                        
                        # Add event to list
                        all_events.append({
                            'summary': event.get('summary', 'Untitled Event'),
                            'start_utc': start_dt.astimezone(pytz.utc),
                            'end_utc': end_dt.astimezone(pytz.utc),
                            'start_local': start_format['datetime'],
                            'end_local': end_format['datetime'],
                            'formatted_start': start_format['formatted'],
                            'formatted_end': end_format['formatted'],
                            'formatted_time': f"{start_format['day_of_week']}, {start_format['date']} from {start_format['time']} to {end_format['time']} ({timezone} time)",
                            'duration_minutes': duration_minutes,
                            'is_recurring': is_recurring,
                            'calendar_name': calendar_name
                        })
                    except Exception as e:
                        print(f"Error processing event {event.get('summary', 'Unknown')} from calendar {calendar_name}: {e}")
                        continue
            except Exception as e:
                print(f"Error fetching events from calendar {calendar_id}: {e}")
                continue
        
        # Sort all events by start time
        all_events.sort(key=lambda event: event['start_utc'])
        return all_events
        
    except HttpError as error:
        print(f"An error occurred while fetching events: {error}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return []