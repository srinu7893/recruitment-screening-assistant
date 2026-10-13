"""Build the offline, synthetic-only manager walkthrough."""
import json
from pathlib import Path
from .showcase import export_dataset


def build():
    root = Path(__file__).resolve().parents[1]
    template = (root / 'screening/static/showcase-template.html').read_text()
    data = json.dumps(export_dataset(), ensure_ascii=False).replace('<', '\\u003c')
    output = root / 'showcase/index.html'
    output.parent.mkdir(exist_ok=True)
    output.write_text(template.replace('__SHOWCASE_DATA__', data))
    return output


if __name__ == '__main__':
    print(build())
