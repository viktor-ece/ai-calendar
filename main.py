import argparse
import tzlocal
import os
from datetime import datetime, timedelta
import pytz
from typing import List, Tuple
from llm_scheduler import format_events_for_llm, get_llm_suggestion, parse_llm_response
from google_calendar_api import create_event_from_llm_suggestion, get_events_from_google_calendar

def main():
    # Set up argument parsing
    parser = argparse.ArgumentParser(description="Fetch events from Google Calendar.")
    parser.add_argument('-u', '--use_hardcoded', action='store_true', help='Use hardcoded start date and duration')
    parser.add_argument('-t', '--ask_timezone', action='store_true', help='Prompt for timezone selection')
    
    args = parser.parse_args()

    # Default hardcoded values
    hardcoded_start_date = "2025-04-17"
    hardcoded_days_ahead = 7

    # Use hardcoded values if specified, otherwise prompt for input
    if args.use_hardcoded:
        start_date = hardcoded_start_date
        days_ahead = hardcoded_days_ahead
    else:
        start_date = input("Enter the start date (YYYY-MM-DD): ")
        while True:
            try:
                # Validate date format
                datetime.strptime(start_date, '%Y-%m-%d')
                break
            except ValueError:
                start_date = input("Invalid date format. Please enter the start date (YYYY-MM-DD): ")

        while True:
            try:
                days_ahead = int(input("Enter the number of days to fetch events: "))
                if days_ahead <= 0:
                    raise ValueError("Number of days must be a positive integer.")
                break
            except ValueError as e:
                print(e)
                days_ahead = input("Please enter a valid number of days to fetch events: ")

    # Get timezone preference
    if args.ask_timezone:
        print("\nTimezone Selection:")
        print("1. Use system timezone")
        print("2. Enter custom timezone")
        while True:
            choice = input("Enter your choice (1/2): ").strip()
            if choice == "1":
                timezone = str(tzlocal.get_localzone())
                break
            elif choice == "2":
                timezone = input("Enter timezone (e.g., 'Europe/Athens', 'America/New_York'): ").strip()
                try:
                    pytz.timezone(timezone)  # Validate timezone
                    break
                except pytz.exceptions.UnknownTimeZoneError:
                    print("Invalid timezone. Please try again.")
            else:
                print("Invalid choice. Please enter 1 or 2.")
    else:
        # Use system timezone by default
        timezone = str(tzlocal.get_localzone())

    # List of calendar IDs to fetch events from
    # 'primary' is your main calendar
    # Add other calendar IDs as needed
    calendar_ids = [
        'primary',  # Your main calendar
        # Add other calendar IDs here, for example:
        # 'user@example.com',  # Another user's calendar
        # 'group.calendar.google.com',  # A group calendar
    ]
    
    try:
        print("\n" + "="*80)
        print("CALENDAR PARSER".center(80))
        print("="*80)
        print(f"\nFetching events from {len(calendar_ids)} calendars")
        print(f"Date range: {start_date} to {(datetime.strptime(start_date, '%Y-%m-%d') + timedelta(days=days_ahead-1)).strftime('%Y-%m-%d')}")
        print(f"Timezone: {timezone}")
        
        all_events = get_events_from_google_calendar(start_date, days_ahead, timezone, calendar_ids)
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return
        
    print("\n" + "="*80)
    print("EVENT SCHEDULING".center(80))
    print("="*80)

    # Get user input for event details
    print("\nPlease provide event details:")
    print("-"*40)
    user_request = input("What event would you like to schedule? (e.g., 'Schedule a dog walk for 1 hour tomorrow'): ")
    event_title = input("What would you like to title this event? (e.g., 'Dog Walk'): ")

    # Format events for LLM
    schedule_context = format_events_for_llm(all_events, timezone)

    # Initialize feedback loop
    feedback_history = []
    while True:
        print("\n" + "="*80)
        print("AI SCHEDULING ASSISTANT".center(80))
        print("="*80)
        
        print("\nGenerating schedule suggestion...")
        raw_llm_response = get_llm_suggestion(schedule_context, user_request, timezone, feedback_history)

        if raw_llm_response is not None:
            # Parse the LLM response
            parsed_response = parse_llm_response(raw_llm_response)
            if parsed_response:
                print("\n" + "-"*40)
                print("SUGGESTED EVENT DETAILS".center(40))
                print("-"*40)
                print(f"Start Time: {parsed_response.get('start_time')}")
                print(f"Duration: {parsed_response.get('duration')} hours")
                print(f"Explanation: {parsed_response.get('explanation')}")
                
                if feedback_history:
                    print("\n" + "-"*40)
                    print("FEEDBACK HISTORY".center(40))
                    print("-"*40)
                    for i, feedback in enumerate(feedback_history, 1):
                        print(f"{i}. {feedback}")
                
                # Display the schedule for the suggested day
                print("\n" + "-"*40)
                print(f"SCHEDULE FOR {parsed_response['start_time'].strftime('%Y-%m-%d')}".center(40))
                print("-"*40)
                
                # Get all events for the suggested day from the parsed ICS file
                target_date = parsed_response['start_time'].date()
                day_events = [event for event in all_events if event['start_local'].date() == target_date]
                
                # Create the new event object with timezone-aware datetimes
                timezone_obj = pytz.timezone(timezone)
                new_event_start = timezone_obj.localize(parsed_response['start_time'])
                new_event = {
                    'start_local': new_event_start,
                    'end_local': new_event_start + timedelta(hours=parsed_response['duration']),
                    'summary': event_title,
                    'is_new': True,
                    'timezone': timezone
                }
                
                # Add the new event to the list and sort by start time
                day_events.append(new_event)
                day_events.sort(key=lambda x: x['start_local'])
                
                if day_events:
                    for event in day_events:
                        time_range = f"{event['start_local'].strftime('%H:%M')} - {event['end_local'].strftime('%H:%M')}"
                        if event.get('is_new'):
                            print(f"{time_range}: {event['summary']} (NEW)")
                        else:
                            print(f"{time_range}: {event['summary']}")
                else:
                    print("No events scheduled for this day.")
                
                print("\n" + "-"*40)
                print("OPTIONS".center(40))
                print("-"*40)
                print("1. Accept this suggestion")
                print("2. Request a different time")
                print("3. Request a different duration")
                print("4. Provide specific constraints")
                print("5. Cancel event creation")
                
                choice = input("\nEnter your choice (1-5): ").strip()
                
                if choice == "1":
                    print("\n" + "="*80)
                    print("CREATING EVENT".center(80))
                    print("="*80)
                    # Create the event in Google Calendar
                    created_event = create_event_from_llm_suggestion(parsed_response, event_title, timezone)
                    if created_event:
                        print("\nEvent created successfully!")
                        print(f"Event Link: {created_event.get('htmlLink')}")
                    else:
                        print("\nFailed to create event.")
                    break
                elif choice == "2":
                    print("\n" + "-"*40)
                    print("TIME PREFERENCE".center(40))
                    print("-"*40)
                    feedback = input("What time would you prefer? (e.g., 'morning', 'afternoon', 'evening', or specific time): ")
                    feedback_history.append(f"Requested different time: {feedback}")
                elif choice == "3":
                    print("\n" + "-"*40)
                    print("DURATION PREFERENCE".center(40))
                    print("-"*40)
                    feedback = input("What duration would you prefer? (e.g., '1 hour', '2 hours', '30 minutes'): ")
                    feedback_history.append(f"Requested different duration: {feedback}")
                elif choice == "4":
                    print("\n" + "-"*40)
                    print("ADDITIONAL CONSTRAINTS".center(40))
                    print("-"*40)
                    feedback = input("What specific constraints do you have? (e.g., 'must be after 5pm', 'not on weekends'): ")
                    feedback_history.append(f"Added constraints: {feedback}")
                elif choice == "5":
                    print("\n" + "="*80)
                    print("EVENT CREATION CANCELLED".center(80))
                    print("="*80)
                    break
                else:
                    print("\nInvalid choice. Please try again.")
            else:
                print("\n" + "="*80)
                print("ERROR".center(80))
                print("="*80)
                print("Failed to parse LLM response.")
                break
        else:
            print("\n" + "="*80)
            print("ERROR".center(80))
            print("="*80)
            print("Failed to get LLM response.")
            break

    print("\n" + "="*80)
    print("PROCESS COMPLETED".center(80))
    print("="*80)

if __name__ == "__main__":
    main() 