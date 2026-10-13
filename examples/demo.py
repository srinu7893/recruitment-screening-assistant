"""Run from repository root with: python -m examples.demo"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from screening.providers import DemoProvider
from screening.storage import Store
from screening.workflow import ScreeningService


def main():
    folder = Path(__file__).parent
    with TemporaryDirectory() as directory:
        service = ScreeningService(Store(Path(directory) / "demo.sqlite3"), DemoProvider())
        service.create_role(json.loads((folder / "role.json").read_text()))
        run = service.screen(json.loads((folder / "profile-request.json").read_text()))
        print(json.dumps({"demo": run["demo"], "status": run["status"], "result": run["result"]}, indent=2))


if __name__ == "__main__":
    main()
