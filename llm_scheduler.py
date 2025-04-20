import os
from datetime import datetime, timedelta
import pytz
import google.generativeai as genai
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

def format_events_for_llm(events: List[Dict[str, Any]], timezone: str = 'UTC') -> str:
    """
    Format events in a concise, LLM-friendly format.
    Returns a structured string with clear event information in local time.
    """
    if not events:
        return "No events found in the specified time period."
    
    # Get current time in local timezone
    current_time = datetime.now(pytz.timezone(timezone))
    current_time_str = current_time.strftime('%Y-%m-%d %H:%M')
    
    # Get date range from first and last events in local time
    start_date = events[0]['start_local'].strftime('%Y-%m-%d')
    end_date = events[-1]['start_local'].strftime('%Y-%m-%d')
    
    output = [
        f"Current Time ({timezone}): {current_time_str}",
        f"Schedule Context ({timezone}): {start_date} to {end_date}",
        f"\nEvents:"
    ]
    
    for event in events:
        # Format the time range in local time
        start_time = event['start_local'].strftime('%Y-%m-%d %H:%M')
        end_time = event['end_local'].strftime('%H:%M')
        
        # Build event description
        desc = event['summary']
        if event.get('is_recurring'):
            desc += " (Recurring)"
        if event['calendar_name'] != 'Main':
            desc += f" (from {event['calendar_name']} Calendar)"
        
        output.append(f"{start_time} - {end_time}: {desc}")
    
    return "\n".join(output)

def get_llm_suggestion(schedule_context: str, user_request: str, timezone: str = 'UTC', feedback_history: List[str] | None = None) -> str | None:
    """
    Sends schedule context and user request to the Gemini API
    and returns the raw text response. Returns None on error.
    """
    try:
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            print("Error: GOOGLE_API_KEY not found in environment variables.")
            return None
    except Exception as e:
        print(f"Error reading environment variable: {e}")
        return None

    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        print(f"Error configuring Google AI client: {e}")
        return None

    try:
        model_name = 'gemini-2.0-flash-thinking-exp-01-21'
        model = genai.GenerativeModel(model_name)
        print(f"Gemini model '{model_name}' initialized.")
    except Exception as e:
        print(f"Error initializing generative model: {e}")
        return None

    # Format feedback history for the prompt
    feedback_text = "No feedback provided"
    if feedback_history and len(feedback_history) > 0:
        feedback_text = "Feedback History:\n"
        for i, feedback in enumerate(feedback_history, 1):
            feedback_text += f"{i}. {feedback}\n"

    prompt = f"""You are a calendar scheduling assistant. Your task is to suggest the best time for a new event based on the user's request and existing schedule.

RULES:
1. Only suggest ONE time slot
2. The time must be in {timezone} timezone
3. Try to avoid conflicts with existing events, but if no perfect slot exists:
   - Suggest the least disruptive time (e.g., shorter duration, different day)
   - Explain why this is the best available option
   - Mention any conflicts that can't be avoided
4. Consider past scheduling patterns (up to 1 month back)
5. Format your response EXACTLY as shown in the template below
6. Pay special attention to the nature of the event (e.g., "movie night" implies evening hours)
7. Consider typical human patterns (e.g., sleep, meals, work hours)
8. For events without specified duration, use reasonable defaults:
   - Movie night: 2-3 hours
   - Meetings: 1 hour
   - Social events: 2-3 hours
   - Work sessions: 1-2 hours
9. When making scheduling decisions, consider:
   - Event type and typical timing (e.g., evening events, morning meetings)
   - Natural breaks in the schedule
   - Duration needed for the event
   - Human patterns (sleep, meals, work hours)
   - Recurring event patterns
   - Available time slots and potential conflicts
10. Formatting rules:
    - Use exactly two asterisks (**) for section headers (e.g., **Suggested schedule:**)
    - Use exactly one asterisk (*) followed by three spaces for bullet points
    - Do not add or remove any asterisks from the template
    - Keep all formatting exactly as shown in the template
11. Consider ALL previous feedback when making your suggestion:
    - Each feedback item represents a previous attempt to find a suitable time
    - Your new suggestion should address ALL previous feedback items
    - If previous feedback conflicts, prioritize the most recent feedback
    - Explain how your suggestion addresses the feedback history

SCHEDULE CONTEXT:
{schedule_context}

USER REQUEST:
{user_request}

{feedback_text}

RESPONSE TEMPLATE:
**Suggested schedule:**

*   Date and Time: YYYY-MM-DD HH:MM
*   Duration: [Specify duration in hours]
*   Explanation: [1-2 sentences explaining why this time works well. If there are conflicts:
- Explain why this is the best available option
- Mention any conflicts that can't be avoided
- Suggest potential alternatives if needed]

**Schedule for YYYY-MM-DD:**

Day: YYYY-MM-DD
HH:MM - HH:MM: Event 1
HH:MM - HH:MM: Event 2
[Include the suggested event in the schedule with exact start and end times]

[DO NOT include anything else in your response]"""

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"An unexpected error occurred while calling GenAI API: {e}")
        return None

def parse_llm_response(response: str) -> Dict[str, Any]:
    """
    Parse the LLM response to extract event details from the current format.
    Returns a dictionary with the following keys:
    - summary: Event title/summary (extracted from the schedule section)
    - start_time: Start time as datetime object
    - duration: Duration in hours
    - explanation: Explanation text
    - schedule_day: Dictionary with date and list of events
    """
    if not response:
        return None

    result = {}
    current_section = None
    schedule_events = []
    date_str = None

    for line in response.split('\n'):
        line = line.strip()
        if not line:
            continue

        # Detect section headers
        if line.startswith('**Suggested schedule:**'):
            current_section = 'suggested'
            continue
        elif line.startswith('**Schedule for'):
            current_section = 'schedule'
            # Extract date from header
            try:
                date_str = line.split('for ')[1].strip('**:')
                result['schedule_day'] = {
                    'date': datetime.strptime(date_str, '%Y-%m-%d').date(),
                    'events': []
                }
            except (IndexError, ValueError) as e:
                print(f"Warning: Could not parse schedule date from: {line}. Error: {e}")
            continue

        if current_section == 'suggested':
            if line.startswith('*   Date and Time:'):
                try:
                    dt_str = line.split('Time:')[1].strip()
                    result['start_time'] = datetime.strptime(dt_str, '%Y-%m-%d %H:%M')
                except (IndexError, ValueError):
                    print(f"Warning: Could not parse start time: {dt_str}")
            elif line.startswith('*   Duration:'):
                try:
                    duration_str = line.split('Duration:')[1].strip()
                    # Remove 'hour' or 'hours' if present and convert to float
                    duration_str = duration_str.replace('hours', '').replace('hour', '').strip()
                    result['duration'] = float(duration_str)
                except (IndexError, ValueError):
                    print(f"Warning: Could not parse duration: {duration_str}")
            elif line.startswith('*   Explanation:'):
                result['explanation'] = line.split('Explanation:')[1].strip()
        elif current_section == 'schedule':
            if line.startswith('Day:'):
                continue
            elif ':' in line:  
                try:
                    time_part, event_desc = line.split(':', 1)
                    time_parts = time_part.split(' - ')
                    if len(time_parts) == 2:
                        start_time, end_time = time_parts
                        schedule_events.append({
                            'time_range': f"{start_time.strip()} - {end_time.strip()}",
                            'description': event_desc.strip()
                        })
                        # If this is the suggested event, extract its summary
                        if 'suggested' in event_desc.lower() or 'new' in event_desc.lower():
                            result['summary'] = event_desc.strip()
                except Exception as e:
                    print(f"Warning: Could not parse event line: {line}")
                    print(f"Error: {e}")

    if 'schedule_day' in result:
        result['schedule_day']['events'] = schedule_events

    return result 