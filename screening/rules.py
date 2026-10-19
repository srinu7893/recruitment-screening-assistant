"""Conservative local matching. Evidence always needs recruiter confirmation."""
import re


class RulesProvider:
    name = 'rules'
    model = 'literal-evidence-v1'

    def analyze(self, role, source_id, profile):
        assessments = []
        for criterion in role['criteria']:
            description = criterion['description'].strip()
            # Recruiters explicitly approve literal phrases by quoting them.
            # Unstructured requirements remain unknown instead of guessed.
            terms = re.findall(r'"([^"\n]{1,120})"', description)
            evidence = []
            for term in terms:
                pattern = r'(?<!\w)' + re.escape(term) + r'(?!\w)'
                match = re.search(pattern, profile, re.I)
                if match:
                    start = profile.rfind('\n', 0, match.start()) + 1
                    end = profile.find('\n', match.end())
                    line = profile[start:end if end >= 0 else len(profile)]
                    # A mention is not proof of experience, proficiency or duration.
                    evidence.append({'source_id': source_id, 'quote': line[:500] if match.end()-start <= 500 else match.group()})
            assessments.append({'criterion_id': criterion['id'],
                'status': 'partial' if evidence else 'not_demonstrated',
                'rationale': ('Literal mention found; confirm context, proficiency and all requirements during review.'
                              if evidence else 'No approved literal evidence found. Missing information is not a qualification failure.'),
                'evidence': evidence})
        return {'facts': [], 'summary': [], 'assessments': assessments}
