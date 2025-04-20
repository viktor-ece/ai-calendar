from datetime import datetime, timedelta, date, time
import pytz
from icalendar import Calendar
from typing import List, Dict, Any, Tuple
from dateutil import rrule
from dateutil.rrule import rrulestr
from dateutil.parser import parse

def parse_ics_datetime(dtstr: str, timezone_str: str = 'UTC') -> datetime:
    """
    Convert an ICS datetime string to a Python datetime object.
    Handles three formats:
    1. UTC time (ends with Z)
    2. Local time with hours/minutes/seconds
    3. Date-only format
    """
    try:
        # Handle UTC time (ends with Z)
        if dtstr.endswith('Z'):
            dt = datetime.strptime(dtstr, '%Y%m%dT%H%M%SZ')
            return pytz.utc.localize(dt)
        
        # Handle local time with hours/minutes/seconds
        dt = datetime.strptime(dtstr, '%Y%m%dT%H%M%S')
        # Localize to the specified timezone
        return pytz.timezone(timezone_str).localize(dt)
    except ValueError:
        # Handle date-only format (no time component)
        dt = datetime.strptime(dtstr, '%Y%m%d')
        return pytz.timezone(timezone_str).localize(dt)

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

def parse_calendar(ics_filepath: str, start_date_str: str | None = None, days_ahead: int = 7, 
                  timezone: str = 'UTC', debug: bool = False) -> List[Dict[str, Any]]:
    """
    Main function to parse an ICS calendar file and extract events.
    Uses a two-pass approach to handle recurring events with modifications:
    1. First pass: Build recurring series
    2. Second pass: Apply modifications (EXDATE and RECURRENCE-ID)
    """
    if debug:
        print(f"Parsing calendar: {ics_filepath}")
        print(f"Target timezone: {timezone}")
    
    # Read and parse the ICS file
    try:
        with open(ics_filepath, 'rb') as f:
            cal = Calendar.from_ical(f.read())
    except FileNotFoundError:
        print(f"Error: The file '{ics_filepath}' was not found.")
        return []
    except IsADirectoryError:
        print(f"Error: Expected a file but found a directory: '{ics_filepath}'.")
        return []
    except Exception as e:
        print(f"Error reading file '{ics_filepath}': {e}")
        return []

    # Get the calendar's default timezone
    cal_timezone = cal.get('X-WR-TIMEZONE', timezone)
    if debug:
        print(f"Calendar timezone: {cal_timezone}")

    # Set the date window for event filtering
    if start_date_str:
        try:
            parsed_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            window_start = datetime.combine(parsed_date, time(0, 0))
            window_start = pytz.timezone(cal_timezone).localize(window_start)
        except ValueError:
            window_start = datetime.now(pytz.timezone(cal_timezone))
    else:
        window_start = datetime.now(pytz.timezone(cal_timezone))

    window_end = window_start + timedelta(days=days_ahead)
    if debug:
        print(f"Window: {window_start} to {window_end}")

    # First pass: Build recurring series and collect modifications
    recurring_events = {}  # uid -> (original_event, modifications)
    modifications = {}     # uid -> {recurrence_id: modified_event}
    single_events = []     # Non-recurring events

    for component in cal.walk():
        if component.name != 'VEVENT':
            continue

        try:
            # Get basic event information
            summary = str(component.get('SUMMARY', 'Untitled Event'))
            uid = str(component.get('UID', ''))
            
            # Process start time
            dtstart = component.get('DTSTART')
            if dtstart is None:
                continue
            
            start_dt = dtstart.dt
            if isinstance(start_dt, date) and not isinstance(start_dt, datetime):
                start_dt = datetime.combine(start_dt, time(0, 0))
            
            # Localize start time to calendar timezone
            if start_dt.tzinfo is None:
                start_dt = pytz.timezone(cal_timezone).localize(start_dt)
            
            # Process end time
            dtend = component.get('DTEND')
            if dtend is None:
                duration = component.get('DURATION')
                if duration is not None:
                    end_dt = start_dt + duration.dt
                else:
                    end_dt = start_dt + timedelta(hours=1)
            else:
                end_dt = dtend.dt
                if isinstance(end_dt, date) and not isinstance(end_dt, datetime):
                    end_dt = datetime.combine(end_dt, time(0, 0))
                
                if end_dt.tzinfo is None:
                    end_dt = pytz.timezone(cal_timezone).localize(end_dt)

            # Check if this is a recurring event
            rrule_prop = component.get('RRULE')
            if rrule_prop:
                # Check if this is a modification of a recurring event
                recurrence_id = component.get('RECURRENCE-ID')
                if recurrence_id:
                    if uid not in modifications:
                        modifications[uid] = {}
                    modifications[uid][recurrence_id.dt] = component
                else:
                    # This is the original recurring event
                    recurring_events[uid] = (component, [])
            else:
                # Non-recurring event
                if (window_start <= start_dt < window_end or 
                    window_start <= end_dt < window_end or
                    (start_dt <= window_start and end_dt >= window_end)):
                    single_events.append(component)

        except Exception as e:
            if debug:
                print(f"Error processing event: {e}")
            continue

    # Second pass: Process recurring events and apply modifications
    events = []
    
    for uid, (component, _) in recurring_events.items():
        try:
            # Get basic event information
            summary = str(component.get('SUMMARY', 'Untitled Event'))
            
            # Process start and end times
            dtstart = component.get('DTSTART')
            dtend = component.get('DTEND')
            start_dt = dtstart.dt
            end_dt = dtend.dt if dtend else start_dt + timedelta(hours=1)
            
            # Localize times if needed
            if start_dt.tzinfo is None:
                start_dt = pytz.timezone(cal_timezone).localize(start_dt)
            if end_dt.tzinfo is None:
                end_dt = pytz.timezone(cal_timezone).localize(end_dt)
            
            # Get exception dates
            exdates = []
            for exdate in component.get('EXDATE', []):
                if isinstance(exdate.dt, list):
                    for dt in exdate.dt:
                        if dt.tzinfo is None:
                            dt = pytz.timezone(cal_timezone).localize(dt)
                        exdates.append(dt.astimezone(pytz.utc))
                else:
                    dt = exdate.dt
                    if dt.tzinfo is None:
                        dt = pytz.timezone(cal_timezone).localize(dt)
                    exdates.append(dt.astimezone(pytz.utc))
            
            # Parse recurrence rule
            rule_string = component.get('RRULE').to_ical().decode('utf-8')
            start_utc = start_dt.astimezone(pytz.utc)
            rule = rrulestr(rule_string, dtstart=start_utc)
            
            # Get all occurrences within the window
            window_start_utc = window_start.astimezone(pytz.utc)
            window_end_utc = window_end.astimezone(pytz.utc)
            occurrences = list(rule.between(window_start_utc, window_end_utc, inc=True))
            
            # Process each occurrence
            for occurrence in occurrences:
                # Skip if this occurrence is in the exception dates
                if any(abs((occurrence - exdate).total_seconds()) < 60 for exdate in exdates):
                    continue
                
                # Check if this occurrence has been modified
                modified_component = modifications.get(uid, {}).get(occurrence.astimezone(pytz.timezone(cal_timezone)))
                if modified_component:
                    # Use the modified event's details
                    mod_dtstart = modified_component.get('DTSTART')
                    mod_dtend = modified_component.get('DTEND')
                    mod_start_dt = mod_dtstart.dt
                    mod_end_dt = mod_dtend.dt if mod_dtend else mod_start_dt + timedelta(hours=1)
                    
                    if mod_start_dt.tzinfo is None:
                        mod_start_dt = pytz.timezone(cal_timezone).localize(mod_start_dt)
                    if mod_end_dt.tzinfo is None:
                        mod_end_dt = pytz.timezone(cal_timezone).localize(mod_end_dt)
                    
                    # Use modified times
                    occurrence = mod_start_dt
                    occurrence_end = mod_end_dt
                    duration = mod_end_dt - mod_start_dt
                else:
                    # Use original event's duration
                    duration = end_dt - start_dt
                    # Calculate the time difference between original start and this occurrence
                    time_diff = occurrence - start_dt.astimezone(pytz.utc)
                    # Add the duration to the occurrence time, preserving the original duration
                    occurrence_end = occurrence + duration
                
                # Convert to target timezone
                occurrence = occurrence.astimezone(pytz.timezone(timezone))
                occurrence_end = occurrence_end.astimezone(pytz.timezone(timezone))
                
                # Format times for display
                start_format = format_event_time(occurrence, timezone)
                end_format = format_event_time(occurrence_end, timezone)
                duration_minutes = int(duration.total_seconds() / 60)
                
                # Add event to list
                events.append({
                    'summary': summary,
                    'start_utc': occurrence.astimezone(pytz.utc),
                    'end_utc': occurrence_end.astimezone(pytz.utc),
                    'start_local': start_format['datetime'],
                    'end_local': end_format['datetime'],
                    'formatted_start': start_format['formatted'],
                    'formatted_end': end_format['formatted'],
                    'formatted_time': f"{start_format['day_of_week']}, {start_format['date']} from {start_format['time']} to {end_format['time']} ({timezone} time)",
                    'duration_minutes': duration_minutes,
                    'is_recurring': True,
                    'is_modified': modified_component is not None
                })
                
        except Exception as e:
            if debug:
                print(f"Error processing recurring event: {e}")
            continue

    # Add non-recurring events
    for component in single_events:
        try:
            summary = str(component.get('SUMMARY', 'Untitled Event'))
            dtstart = component.get('DTSTART')
            dtend = component.get('DTEND')
            
            start_dt = dtstart.dt
            end_dt = dtend.dt if dtend else start_dt + timedelta(hours=1)
            
            if start_dt.tzinfo is None:
                start_dt = pytz.timezone(cal_timezone).localize(start_dt)
            if end_dt.tzinfo is None:
                end_dt = pytz.timezone(cal_timezone).localize(end_dt)
            
            # Format times for display
            start_format = format_event_time(start_dt, timezone)
            end_format = format_event_time(end_dt, timezone)
            duration_minutes = int((end_dt - start_dt).total_seconds() / 60)
            
            # Add event to list
            events.append({
                'summary': summary,
                'start_utc': start_dt.astimezone(pytz.utc),
                'end_utc': end_dt.astimezone(pytz.utc),
                'start_local': start_format['datetime'],
                'end_local': end_format['datetime'],
                'formatted_start': start_format['formatted'],
                'formatted_end': end_format['formatted'],
                'formatted_time': f"{start_format['day_of_week']}, {start_format['date']} from {start_format['time']} to {end_format['time']} ({timezone} time)",
                'duration_minutes': duration_minutes,
                'is_single': True
            })
            
        except Exception as e:
            if debug:
                print(f"Error processing single event: {e}")
            continue

    return events

def parse_multiple_calendars(calendar_files: List[Tuple[str, str]], start_date_str: str | None = None, 
                            days_ahead: int = 7, timezone: str = 'UTC') -> List[Dict[str, Any]]:
    """
    Parse multiple calendar files and combine their events.
    Parameters:
    - calendar_files: List of (file_path, calendar_name) tuples
    - start_date_str: Start date in YYYY-MM-DD format (optional)
    - days_ahead: Number of days to look ahead
    - timezone: Target timezone
    
    Returns a combined list of events from all calendars, sorted by start time
    """
    all_events = []
    
    # Process each calendar file
    for file_path, calendar_name in calendar_files:
        events = parse_calendar(file_path, start_date_str, days_ahead, timezone)
        # Add calendar name to each event
        for event in events:
            event['calendar_name'] = calendar_name
        all_events.extend(events)
    
    # Sort all events by start time
    all_events.sort(key=lambda event: event['start_utc'])
    return all_events

def print_events(events: List[Dict[str, Any]], show_details: bool = False) -> None:
    """
    Print events in a formatted way.
    Parameters:
    - events: List of events to print
    - show_details: Whether to show detailed event information
    """
    if not events:
        print("No events found in the specified time period.")
        return
    
    print(f"Found {len(events)} events:")
    print("-" * 80)
    
    # Print each event
    for i, event in enumerate(events, 1):
        print(f"{i}. [{event['calendar_name']}] {event['summary']}")
        print(f"   {event['formatted_time']}")
        
        # Print detailed information if requested
        if show_details:
            duration_hours = event['duration_minutes'] / 60
            duration_str = f"{duration_hours:.1f} hours" if duration_hours >= 1 else f"{event['duration_minutes']} minutes"
            print(f"   Duration: {duration_str}")
            print(f"   Start: {event['start_local'].isoformat()}")
            print(f"   End: {event['end_local'].isoformat()}")
        print()