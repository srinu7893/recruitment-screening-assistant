"""Persisted synchronous workflow for a pasted profile."""

import copy
import hashlib
import json
from uuid import uuid4

from .contracts import MAX_PROFILE_CHARS, PROMPT_VERSION, text, validate_output, validate_role
from .providers import ProviderError
from .storage import now


class ScreeningService:
    def __init__(self, store, provider):
        self.store = store
        self.provider = provider

    def create_role(self, role):
        validate_role(role)
        return self.store.create_role(role)

    def screen(self, request, metadata=None):
        if not isinstance(request, dict) or set(request) != {"request_id", "role_version", "profile_text"}:
            raise ValueError("Expected request_id, role_version and profile_text")
        text(request["request_id"], "request_id", 120)
        text(request["role_version"], "role_version", 120)
        profile = text(request["profile_text"], "profile_text", MAX_PROFILE_CHARS)
        role = self.store.get_role(request["role_version"])
        fingerprint = hashlib.sha256(json.dumps({
            "request": request, "provider": self.provider.name,
            "model": self.provider.model, "prompt_version": PROMPT_VERSION,
            "metadata": metadata or {}
        }, sort_keys=True).encode()).hexdigest()
        source_id = str(uuid4())
        run = {
            "run_id": request["request_id"], "candidate_id": str(uuid4()),
            "role_version": role["role_version"], "role_snapshot": role,
            "source": {"source_id": source_id, "kind": "paste", "text": profile,
                       "sha256": hashlib.sha256(profile.encode()).hexdigest()},
            "provider": self.provider.name, "model": self.provider.model,
            "prompt_version": PROMPT_VERSION, "demo": getattr(self.provider, "is_demo", self.provider.name == "demo"),
            "status": "received", "events": [{"status": "received", "at": now()}],
            "result": None, "error": None
        }
        run["revision"] = 0
        run["created_at"] = now()
        run["source"]["metadata"] = metadata or {}
        if metadata and metadata.get("kind"):
            run["source"]["kind"] = metadata["kind"]
        run, created = self.store.start_run(run, fingerprint)
        if not created:
            return run
        try:
            self.transition(run, "evaluating")
            output = self.provider.analyze(copy.deepcopy(role), source_id, profile)
            self.transition(run, "validating")
            run["result"] = validate_output(output, role, source_id, profile)
            self.transition(run, "awaiting_review")
        except ProviderError as exc:
            # Built-in providers expose only controlled codes, not response bodies.
            safe_codes = {"provider_response_too_large", "provider_incomplete", "provider_refused",
                          "provider_invalid_response", "provider_unavailable"}
            safe_codes.update(f"provider_http_{code}" for code in range(100, 600))
            run["error"] = str(exc) if str(exc) in safe_codes else "provider_failed"
            self.transition(run, "failed")
        except ValueError:
            run["error"] = "invalid_model_output"
            self.transition(run, "failed")
        except Exception:
            run["error"] = "processing_failed"
            self.transition(run, "failed")
        return run

    def transition(self, run, status):
        run["status"] = status
        run["events"].append({"status": status, "at": now()})
        self.store.save_run(run)
