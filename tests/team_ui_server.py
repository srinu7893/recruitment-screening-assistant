"""Isolated browser-test server without a configured source (never production)."""
import os
from screening.server import make_server
from screening.storage import Store
from screening.rules import RulesProvider
from screening.workflow import ScreeningService
from screening.providers import ProviderError
class FailOnceRules(RulesProvider):
    failed=False
    def analyze(self,role,source_id,profile):
        if 'FAIL-ONCE' in profile and not self.failed:
            self.failed=True
            raise ProviderError('provider_unavailable')
        return super().analyze(role,source_id,profile)
server=make_server(ScreeningService(Store(os.environ['TEST_UI_DATABASE']),FailOnceRules()),port=18768,
                   config={'allowed_hosts':set()})
print('Team test server ready',flush=True)
try:server.serve_forever()
finally:server.server_close()
