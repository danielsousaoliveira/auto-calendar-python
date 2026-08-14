import requests
import os
import json
from src.utils.utils import parse_response_to_list


url = "https://api.github.com/graphql"

def get_github_auth():

    authDir = "auth"

    credentialsPath = os.path.join(authDir, "ghub.json")

    if os.path.exists(credentialsPath):
      with open(credentialsPath, 'r') as f:
        credentials = json.load(f)
        token = credentials.get('token')
        projectID = credentials.get('project_id')

    return token, projectID

def get_github_query(projectID):

    return f"""
    query{{
    node(id: "{projectID}") {{
        ... on ProjectV2 {{
            items(first: 100) {{
            nodes{{
                id
                fieldValues(first: 100) {{
                nodes{{                
                    ... on ProjectV2ItemFieldTextValue {{
                    text
                    field {{
                        ... on ProjectV2FieldCommon {{
                        name
                        }}
                    }}
                    }}
                    ... on ProjectV2ItemFieldDateValue {{
                    date
                    field {{
                        ... on ProjectV2FieldCommon {{
                        name
                        }}
                    }}
                    }}
                    ... on ProjectV2ItemFieldSingleSelectValue {{
                    name
                    field {{
                        ... on ProjectV2FieldCommon {{
                        name
                        }}
                    }}
                    }}
                    ... on ProjectV2ItemFieldNumberValue {{
                    number
                    }}
                }}              
                }}
                content{{              
                ... on DraftIssue {{
                    title
                    body
                }}
                ...on Issue {{
                    title
                    body
                    assignees(first: 10) {{
                    nodes{{
                        login
                    }} 
                    }}
                }}
                ...on PullRequest {{
                    title
                    body
                    assignees(first: 10) {{
                    nodes{{
                        login
                    }}
                    }}
                }}
                }}
            }}
            }}
        }}
        }}
    }}
    """

def get_github_headers(token):

    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

def get_github_project_items(token, projectID):

    query = get_github_query(projectID)
    headers = get_github_headers(token)

    try:
        response = requests.post(url, json={"query": query}, headers=headers)
        response.raise_for_status()
        data = response.json()
        projectItems = parse_response_to_list(data)
        return projectItems
        
    except requests.exceptions.RequestException as e:
        print("Error:", e)
        return None

def display_github_project_items(projectItems):
    for item in projectItems:
        item.display()
        print("\n")
