import os

from dotenv import load_dotenv
from shotgun_api3 import Shotgun

load_dotenv("/Users/lolot/html_server/.env")

SERVER_PATH = os.environ["SHOTGRID_SERVER_URL"]
LOGIN = os.environ["SHOTGRID_LOGIN"]
PASSPHRASE = os.environ["SHOTGRID_PASSPHRASE"]
PAT = os.environ["SHOTGRID_PAT"]

sg = Shotgun(
    SERVER_PATH,
    login=LOGIN,
    password=PASSPHRASE,
)

if __name__ == "__main__":
  # Constrain users to status==active
  filters = [['sg_status_list', 'is', 'act']]
  fields = ['id']
  users = sg.find('HumanUser', filters, fields)

  # Print a single count of active user accounts
  print(f"Active user accounts: {len(users)}")

  projects = sg.find(
    "Project",
    [],
    ["id", "name", "sg_status", "start_date", "end_date", "is_demo"]
  )

  print(f"Total projects: {len(projects)}")
  for project in projects:
    print(f"{project['id']}: {project['name']} [{project.get('sg_status')}]")