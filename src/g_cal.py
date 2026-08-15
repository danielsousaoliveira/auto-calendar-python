from datetime import datetime, timedelta
import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from .dtos.event import EventDTO
from .dtos.task import TaskDTO
from .dtos.project_item import ProjectItemDTO
from .utils.utils import *
import random

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/tasks"]

def authenticate():
    creds = None
    authDir = "auth"

    if not os.path.exists(authDir):
        os.makedirs(authDir)

    tokenPath = os.path.join(authDir, "token.json")
    credentialsPath = os.path.join(authDir, "credentials.json")

    if os.path.exists(tokenPath):
      creds = Credentials.from_authorized_user_file(tokenPath, SCOPES)

   
    if not creds or not creds.valid:
      if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
      else:
        flow = InstalledAppFlow.from_client_secrets_file(
            credentialsPath, SCOPES
        )
        creds = flow.run_local_server(port=0)
      
      with open(tokenPath, "w") as token:
        token.write(creds.to_json())

    return creds

def get_calendar_service(creds: Credentials):
    return build("calendar", "v3", credentials=creds)

def get_tasks_service(creds: Credentials):
    return build("tasks", "v1", credentials=creds)



def list_all_google_events(service):

    now = datetime.now().isoformat() + "Z"
    print(f"Getting the upcoming 100 events")
    eventsResult = (
        service.events()
        .list(
            calendarId="primary", timeMin=now, maxResults=100, singleEvents=True
        )
        .execute()
    )
    events = eventsResult.get("items", [])

    if not events:
        print("No upcoming events found.")
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        print(f"{event['summary']} ({start})")

    return events

def list_all_google_tasks(service):

    results = service.tasks().list(tasklist='@default', maxResults=100).execute()
    items = results.get("items", [])

    if not items:
      print("No tasks found.")
      return

    print("Tasks:")
    for item in items:
      print(f"{item['title']} ({item['id']}) - ({item['due']})")

    return items

def insert_google_event(service, event):
    ev = service.events().insert(calendarId="primary", body=event).execute()
    return ev

def insert_google_task(service, task):
    ta = service.tasks().insert(tasklist='@default', body=task).execute()
    return ta

def create_tasks_to_insert_from_project_item(projectItem: ProjectItemDTO):
    tasks = []

    for t in projectItem.tasks:
        kind = "tasks#task"
        status = "needsAction"
        notes = f"Event: {projectItem.title}"

        tasks.append(TaskDTO(
            kind=kind,
            title=t,
            notes=notes,
            status=status,
            due=projectItem.endDate.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        ))

    return tasks

def create_event_to_insert_from_project_item(projectItem: ProjectItemDTO):
 
    attendees = [{'email': 'danielsousaoliveira77@gmail.com'}]
    colorId = str(random.randint(1,11))
    notes = f"Priority: {projectItem.priority} | Status: {projectItem.status} | Size {projectItem.size} | Estimate: {projectItem.estimate}"
    startDate = projectItem.startDate.strftime("%Y-%m-%dT%H:%M:%S")
    endDate = projectItem.endDate.strftime("%Y-%m-%dT%H:%M:%S")
    return EventDTO(
          summary=projectItem.title,
          start={'dateTime': startDate, 'timeZone': 'Europe/Lisbon'},
          end={'dateTime': endDate, 'timeZone': 'Europe/Lisbon'},
          attendees=attendees,
          colorId=colorId,
          description=notes
      )

def schedule_events_from_project_items(startDate, endDate, startHour, endHour, events, tasks):

    sizeOrder = {
    'XS': 4,
    'S': 3,
    'M': 2,
    'L': 1,
    'XL': 0
    }

    tasks = [task for task in tasks if task.status == 'Backlog']
    # Sort tasks by priority: P0 > P1 > P2
    tasks.sort(key=lambda task: (task.priority if task.priority is not None else 'P4', sizeOrder.get(task.size, float('inf'))))


    scheduledTasks = []
    scheduledEvents = []
    currentDate = datetime.strptime(startDate, "%Y-%m-%d")
    endDate = datetime.strptime(endDate, "%Y-%m-%d")

    while currentDate <= endDate:
        dayStart = parse_datetime(currentDate.strftime("%Y-%m-%d"), startHour)
        dayEnd = parse_datetime(currentDate.strftime("%Y-%m-%d"), endHour)


        for event in events:
           if 'dateTime' in event.get('start', {}) and 'dateTime' in event.get('end', {}) and datetime.fromisoformat(event['start']['dateTime']) <= dayEnd and datetime.fromisoformat(event['end']['dateTime']) >= dayStart:
            filteredEvent = ProjectItemDTO(
                        title=event['summary'],
                        startDate=datetime.fromisoformat(event['start']['dateTime']).replace(tzinfo=timezone.utc),
                        endDate=datetime.fromisoformat(event['end']['dateTime']).replace(tzinfo=timezone.utc),
                        priority=None,
                        size=None,
                        estimate=None,
                        status='Backlog',
                        description='',
                        tasks=[]
            )

            scheduledEvents.append(filteredEvent)

        largeTaskScheduled = False

        while len(tasks) > 0:
            
            task = tasks[0] 
            assign_estimate_if_missing(task)
            taskDuration = timedelta(hours=task.estimate)
            switchedTasks = False
            if task.size in ['L', 'XL']:
                if largeTaskScheduled:
                    for j in range(1, len(tasks)):
                        if tasks[j].size in ['XS', 'S', 'M']:                     
                            smaller_task = tasks.pop(j)
                            tasks.insert(0, smaller_task)
                            switchedTasks = True
                            break
                    if not switchedTasks:
                       largeTaskScheduled = False
                       currentDate += timedelta(days=1)
                       break
                       
                        
                else:
                    largeTaskScheduled = True
    
            taskStart, taskEnd = find_next_available_slot(dayStart, dayEnd, taskDuration, scheduledEvents)

            if taskStart and taskEnd:
                scheduledTask = ProjectItemDTO(
                    title=task.title,
                    startDate=taskStart,
                    endDate=taskEnd,
                    priority=task.priority,
                    size=task.size,
                    estimate=task.estimate,
                    status='Backlog',
                    description=task.description,
                    tasks=task.tasks
                )
                duration =  (taskEnd - taskStart).total_seconds() / 3600
                scheduledTasks.append(scheduledTask)
                scheduledEvents.append(scheduledTask)
                scheduledEvents.sort(key=lambda x: x.startDate)
                if(task.estimate > duration):
                   task.estimate -= duration
                else:
                    tasks.remove(task)
            else:
               break
        
        currentDate += timedelta(days=1)

    return scheduledTasks
