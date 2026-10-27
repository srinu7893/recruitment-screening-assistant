"""Build a portable manager presentation and synthetic resume files."""
import base64
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(output=None):
    data = json.loads((ROOT/'screening/fixtures/manager_demo.json').read_text(encoding='utf-8'))
    output = Path(output or ROOT/'artifacts/manager-demo')
    resumes = output/'resumes'; resumes.mkdir(parents=True, exist_ok=True)
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    import textwrap
    for profile in data['profiles']:
        stem = profile['id']+'-FICTIONAL-'+profile['name'].replace(' ','-')
        (resumes/(stem+'.txt')).write_text(profile['text'], encoding='utf-8')
        pdf = canvas.Canvas(str(resumes/(stem+'.pdf')), pagesize=A4, invariant=1)
        pdf.setTitle('Fictional demonstration resume - '+profile['id'])
        pdf.setFillColor(colors.HexColor('#155d50')); pdf.setFont('Helvetica-Bold',19)
        pdf.drawString(48,790,profile['name']+' | '+profile['id'])
        pdf.setFillColor(colors.HexColor('#9a4d00'));pdf.setFont('Helvetica-Bold',10)
        pdf.drawString(48,767,'FICTIONAL DEMONSTRATION ONLY - NOT A REAL APPLICANT')
        pdf.setFillColor(colors.HexColor('#172c32'));pdf.setFont('Helvetica',11)
        y=735
        for line in profile['text'].splitlines()[2:]:
            for wrapped in textwrap.wrap(line,83) or ['']:
                pdf.drawString(48,y,wrapped);y-=18
            y-=8
        pdf.save()
    (output/'approved-role.json').write_text(json.dumps(data['role'],indent=2),encoding='utf-8')
    rows = ''.join('<tr><td><b>'+html.escape(p['id'])+'</b><br>'+html.escape(p['name'])+'</td><td>'+html.escape(p['scenario'])+'</td><td>'+str(p['expected_mentions'])+' / 5</td><td><button class="download" data-id="'+p['id']+'">Download TXT</button></td></tr>' for p in data['profiles'])
    fixture = base64.b64encode(json.dumps(data).encode()).decode()
    template = (ROOT/'docs/manager-demo/presentation.template.html').read_text(encoding='utf-8')
    presentation = template.replace('<!--PROFILE_ROWS-->',rows).replace('__FIXTURE_BASE64__',fixture)
    (output/'manager-presentation.html').write_text(presentation,encoding='utf-8')
    (ROOT/'docs/manager-demo/presentation.html').write_text(presentation,encoding='utf-8')
    for source, target in [('docs/manager-demo/README.md', 'DEMO-GUIDE.md'),
                           ('docs/manager-demo/PROCESS.md', 'SIMPLE-PROCESS.md'),
                           ('docs/PLAN.md', 'FEATURE-ROADMAP.md'),
                           ('docs/PRODUCT_REVIEW.md', 'PRODUCT-REVIEW.md'),
                           ('docs/TEAM_WORKFLOWS.md', 'TEAM_WORKFLOWS.md'),
                           ('docs/SCHEDULED_BACKUPS.md', 'SCHEDULED_BACKUPS.md'),
                           ('docs/ROLLOUT_CHECKLIST.md', 'ROLLOUT_CHECKLIST.md')]:
        content = (ROOT/source).read_text(encoding='utf-8')
        links = {'../PRODUCT_REVIEW.md':'PRODUCT-REVIEW.md', '../PLAN.md':'FEATURE-ROADMAP.md',
                 'manager-demo/PROCESS.md':'SIMPLE-PROCESS.md', 'PRODUCT_REVIEW.md':'PRODUCT-REVIEW.md',
                 '(PROCESS.md)':'(SIMPLE-PROCESS.md)', '(README.md)':'(DEMO-GUIDE.md)'}
        for before, after in links.items():
            content = content.replace(before, after)
        (output/target).write_text(content,encoding='utf-8')
    print('Built manager HTML presentation and five fictional resumes in PDF and TXT: '+str(output))
    return output


if __name__ == '__main__':
    build()
