import pandas as pd
from database import SessionLocal, engine
from models import TeamMapping

db = SessionLocal()
mappings = db.query(TeamMapping).all()

if mappings:
    df = pd.DataFrame([m.__dict__ for m in mappings])
    df = df.drop(columns=['_sa_instance_state'])
    print("Team Mappings:")
    print(df.to_string())
else:
    print("No team mappings found.")

db.close()
