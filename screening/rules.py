"""Conservative local matching. Evidence always needs recruiter confirmation."""
import re


def criterion_terms(criterion):
    if 'phrases' in criterion:
        return criterion['phrases']
    return re.findall(r'"([^"\n]{1,120})"', criterion['description'])


def preview(role, profile=''):
    from .contracts import validate_role, validate_output
    validate_role(role)
    warnings = [{'criterion_id': c['id'], 'message': 'Add at least one matching phrase.'}
                for c in role['criteria'] if not criterion_terms(c)]
    result = validate_output(RulesProvider().analyze(role, 'preview', profile), role, 'preview', profile)
    return {'criteria': [{'id': c['id'], 'phrases': criterion_terms(c)} for c in role['criteria']],
            'warnings': warnings, 'result': result, 'saved': False}


class RulesProvider:
    name = 'rules'
    model = 'literal-evidence-v2'

    def analyze(self, role, source_id, profile):
        assessments = []
        for criterion in role['criteria']:
            description = criterion['description'].strip()
            # Recruiters explicitly approve literal phrases by quoting them.
            # Unstructured requirements remain unknown instead of guessed.
            terms = criterion_terms(criterion)
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
