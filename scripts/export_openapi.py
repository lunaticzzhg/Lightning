"""Export the current FastAPI route contract without opening a database connection."""
import json

from sqlalchemy import create_engine
from backend.app.api import create_app

if __name__ == '__main__':
    schema = create_app(create_engine('sqlite://')).openapi()
    print(json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(',', ':')))
