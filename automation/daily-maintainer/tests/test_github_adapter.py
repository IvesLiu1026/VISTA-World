from __future__ import annotations

import json
import unittest
from dataclasses import replace

from vista_daily_maintainer.github_adapter import (
    EXACT_INSTALLATION_PERMISSIONS,
    GitHubAdapterError,
    GitHubAppAuthorityAttestation,
    GitHubAppRestAdapter,
    GitHubRequest,
    GitHubResponse,
    InstallationToken,
    MAX_RESPONSE_BYTES,
    MAX_RESPONSE_HEADER_CHARACTERS,
    MAX_RESPONSE_HEADERS,
)
from vista_daily_maintainer.publisher import (
    CANONICAL_REPOSITORY,
    DraftPullRequestSpec,
    GitIdentity,
    PrincipalMode,
    PublicationConflictError,
)


NOW = 2_000_000
BASE = "1" * 40
HEAD = "2" * 40
PATCH = "a" * 64
BRANCH = "codex/daily/2026-08-21-vw-dm-0001-11111111"
ACTOR = "vista-world-publisher[bot]"
COMMITTER = GitIdentity(
    "VISTA World Publisher",
    "publisher@users.noreply.github.com",
)
TOKEN_SECRET = "ghs_" + "S" * 48
POLICY_SHA256 = "b" * 64


def authority(**changes: object) -> GitHubAppAuthorityAttestation:
    values: dict[str, object] = {
        "issued_at": NOW - 30,
        "expires_at": NOW + 1800,
        "app_id": 1234,
        "installation_id": 5678,
        "actor": ACTOR,
        "repository": CANONICAL_REPOSITORY,
        "effective_repositories": (CANONICAL_REPOSITORY,),
        "permissions": EXACT_INSTALLATION_PERMISSIONS,
        "repository_scoped": True,
        "is_admin": False,
        "can_bypass_branch_protection": False,
        "committer": COMMITTER,
        "attested_by": "root-owned-ruleset-auditor",
        "protected_policy_sha256": POLICY_SHA256,
    }
    values.update(changes)
    return GitHubAppAuthorityAttestation.attest(**values)  # type: ignore[arg-type]


def token(**changes: object) -> InstallationToken:
    values: dict[str, object] = {
        "token": TOKEN_SECRET,
        "issued_at": NOW - 30,
        "expires_at": NOW + 1800,
        "app_id": 1234,
        "installation_id": 5678,
        "actor": ACTOR,
        "repository": CANONICAL_REPOSITORY,
        "permissions": EXACT_INSTALLATION_PERMISSIONS,
        "committer": COMMITTER,
        "authority_sha256": authority().evidence_sha256,
    }
    values.update(changes)
    return InstallationToken.bind(**values)  # type: ignore[arg-type]


class Provider:
    def __init__(self, *values: InstallationToken) -> None:
        self.values = values or (token(),)
        self.calls = 0

    def issue(self, repository: str) -> InstallationToken:
        self.calls += 1
        return self.values[min(self.calls - 1, len(self.values) - 1)]


class Authority:
    def __init__(self, *values: GitHubAppAuthorityAttestation) -> None:
        self.values = values or (authority(),)
        self.calls = 0

    def read(self, repository: str) -> GitHubAppAuthorityAttestation:
        self.calls += 1
        return self.values[min(self.calls - 1, len(self.values) - 1)]


class Transport:
    def __init__(self, *values: GitHubResponse | Exception) -> None:
        self.values = list(values)
        self.requests: list[GitHubRequest] = []
        self.bounds: list[tuple[int, int, int]] = []

    def send(
        self,
        request: GitHubRequest,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
        max_response_headers: int,
        max_response_header_characters: int,
    ) -> GitHubResponse:
        self.requests.append(request)
        self.bounds.append(
            (
                max_response_bytes,
                max_response_headers,
                max_response_header_characters,
            )
        )
        if not self.values:
            raise AssertionError("unexpected GitHub request")
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def response(
    value: object,
    *,
    status: int = 200,
    headers: tuple[tuple[str, str], ...] = (),
) -> GitHubResponse:
    return GitHubResponse(
        status=status,
        headers=(("Content-Type", "application/json; charset=utf-8"), *headers),
        body=json.dumps(value, separators=(",", ":")).encode("utf-8"),
    )


def installation_repositories() -> dict[str, object]:
    return {
        "total_count": 1,
        "repositories": [
            {
                "id": 42,
                "full_name": CANONICAL_REPOSITORY,
                "private": False,
                "fork": False,
            }
        ],
    }


def reference(branch: str, sha: str) -> dict[str, object]:
    return {"ref": f"refs/heads/{branch}", "object": {"type": "commit", "sha": sha}}


def pull_request(
    spec: DraftPullRequestSpec,
    *,
    number: int = 7,
    actor: str = ACTOR,
    draft: bool = True,
    title: str | None = None,
) -> dict[str, object]:
    return {
        "number": number,
        "html_url": f"https://github.com/{CANONICAL_REPOSITORY}/pull/{number}",
        "base": {"ref": "main"},
        "head": {
            "ref": spec.head_branch,
            "sha": HEAD,
            "repo": {"full_name": CANONICAL_REPOSITORY},
        },
        "user": {"login": actor},
        "title": title or spec.title,
        "body": spec.body,
        "state": "open",
        "draft": draft,
    }


def draft_spec() -> DraftPullRequestSpec:
    return DraftPullRequestSpec(
        repository=CANONICAL_REPOSITORY,
        base_branch="main",
        head_branch=BRANCH,
        title="[Daily Maintainer] VW-DM-0001 verified patch",
        body="Verified evidence\n\nAutomated-by: Codex Daily Maintainer\n",
        draft=True,
    )


class GitHubAppRestAdapterTests(unittest.TestCase):
    def adapter(
        self,
        transport: Transport,
        *,
        provider: Provider | None = None,
        authority_port: Authority | None = None,
    ) -> GitHubAppRestAdapter:
        return GitHubAppRestAdapter(
            authority=authority_port or Authority(),
            tokens=provider or Provider(),
            transport=transport,
            clock=lambda: NOW,
        )

    def test_request_and_token_repr_never_expose_secret(self) -> None:
        binding = token()
        request = GitHubRequest(
            method="GET",
            url="https://api.github.com/installation/repositories",
            body=None,
            authorization=f"Bearer {TOKEN_SECRET}",
        )
        self.assertNotIn(TOKEN_SECRET, repr(binding))
        self.assertNotIn(TOKEN_SECRET, repr(request))
        self.assertIn(("Authorization", f"Bearer {TOKEN_SECRET}"), request.headers)

    def test_principal_requires_exact_repository_scoped_app_authority(self) -> None:
        transport = Transport(response(installation_repositories()))
        principal = self.adapter(transport).inspect_principal(
            CANONICAL_REPOSITORY, PrincipalMode.GITHUB_APP
        )
        self.assertEqual(principal.actor, ACTOR)
        self.assertEqual(principal.permissions, EXACT_INSTALLATION_PERMISSIONS)
        self.assertTrue(principal.repository_scoped)
        self.assertFalse(principal.is_admin)
        self.assertFalse(principal.can_bypass_branch_protection)
        self.assertEqual(principal.authority_sha256, authority().evidence_sha256)
        self.assertEqual(principal.protected_policy_sha256, POLICY_SHA256)
        self.assertEqual(
            transport.requests[0].url.split("?", 1)[0],
            "https://api.github.com/installation/repositories",
        )
        self.assertEqual(
            transport.bounds[0],
            (
                MAX_RESPONSE_BYTES,
                MAX_RESPONSE_HEADERS,
                MAX_RESPONSE_HEADER_CHARACTERS,
            ),
        )
        with self.assertRaisesRegex(GitHubAdapterError, "GitHub App mode"):
            self.adapter(Transport()).inspect_principal(
                CANONICAL_REPOSITORY, PrincipalMode.CLI_BOOTSTRAP
            )
        with self.assertRaisesRegex(GitHubAdapterError, "not repository-scoped"):
            self.adapter(
                Transport(
                    response(
                        {
                            "total_count": 2,
                            "repositories": installation_repositories()["repositories"]
                            * 2,
                        }
                    )
                )
            ).inspect_principal(CANONICAL_REPOSITORY, PrincipalMode.GITHUB_APP)

    def test_stale_permission_drift_and_authority_rotation_fail_closed(self) -> None:
        with self.assertRaisesRegex(GitHubAdapterError, "permissions are not exact"):
            token(permissions=(*EXACT_INSTALLATION_PERMISSIONS, "issues:write"))
        stale = token(issued_at=NOW - 3600, expires_at=NOW + 30)
        with self.assertRaisesRegex(GitHubAdapterError, "stale"):
            self.adapter(Transport(), provider=Provider(stale)).read_branch_sha(
                CANONICAL_REPOSITORY, "main"
            )
        first = authority()
        second = authority(app_id=9999)
        adapter = self.adapter(
            Transport(
                response(installation_repositories()),
                response(reference("main", BASE)),
            ),
            authority_port=Authority(first, second),
        )
        adapter.inspect_principal(CANONICAL_REPOSITORY, PrincipalMode.GITHUB_APP)
        with self.assertRaisesRegex(GitHubAdapterError, "authority changed"):
            adapter.read_branch_sha(CANONICAL_REPOSITORY, "main")

    def test_repository_and_branch_readback_are_exact(self) -> None:
        transport = Transport(
            response(
                {
                    "full_name": CANONICAL_REPOSITORY,
                    "default_branch": "main",
                    "private": False,
                    "fork": False,
                }
            ),
            response(reference("main", BASE)),
            GitHubResponse(status=404, headers=(), body=b"{}"),
        )
        adapter = self.adapter(transport)
        repository = adapter.inspect_repository(CANONICAL_REPOSITORY)
        self.assertEqual(repository.main_sha, BASE)
        self.assertTrue(repository.public)
        self.assertFalse(repository.is_fork)
        self.assertIsNone(adapter.read_branch_sha(CANONICAL_REPOSITORY, BRANCH))

    def test_get_retries_transient_status_but_rejects_redirect(self) -> None:
        transient = GitHubResponse(status=503, headers=(), body=b"")
        adapter = self.adapter(
            Transport(transient, transient, response(reference("main", BASE)))
        )
        self.assertEqual(adapter.read_branch_sha(CANONICAL_REPOSITORY, "main"), BASE)
        redirect = GitHubResponse(
            status=302,
            headers=(("Location", "https://evil.invalid/steal"),),
            body=b"",
        )
        with self.assertRaisesRegex(GitHubAdapterError, "redirect"):
            self.adapter(Transport(redirect)).read_branch_sha(
                CANONICAL_REPOSITORY, "main"
            )

    def test_strict_json_content_type_size_and_duplicate_keys(self) -> None:
        duplicate = GitHubResponse(
            status=200,
            headers=(("Content-Type", "application/json"),),
            body=b'{"ref":"a","ref":"b"}',
        )
        with self.assertRaisesRegex(GitHubAdapterError, "strict JSON"):
            self.adapter(Transport(duplicate)).read_branch_sha(
                CANONICAL_REPOSITORY, "main"
            )
        wrong_type = GitHubResponse(
            status=200,
            headers=(("Content-Type", "text/html"),),
            body=b"{}",
        )
        with self.assertRaisesRegex(GitHubAdapterError, "content type"):
            self.adapter(Transport(wrong_type)).read_branch_sha(
                CANONICAL_REPOSITORY, "main"
            )
        oversized = GitHubResponse(
            status=200,
            headers=(("Content-Type", "application/json"),),
            body=b" " * (1024 * 1024 + 1),
        )
        with self.assertRaisesRegex(GitHubAdapterError, "oversized"):
            self.adapter(Transport(oversized)).read_branch_sha(
                CANONICAL_REPOSITORY, "main"
            )
        oversized_not_found = GitHubResponse(
            status=404,
            headers=(),
            body=b" " * (MAX_RESPONSE_BYTES + 1),
        )
        with self.assertRaisesRegex(GitHubAdapterError, "oversized"):
            self.adapter(Transport(oversized_not_found)).read_branch_sha(
                CANONICAL_REPOSITORY, BRANCH
            )
        oversized_retry = GitHubResponse(
            status=503,
            headers=(),
            body=b" " * (MAX_RESPONSE_BYTES + 1),
        )
        with self.assertRaisesRegex(GitHubAdapterError, "oversized"):
            self.adapter(Transport(oversized_retry)).read_branch_sha(
                CANONICAL_REPOSITORY, "main"
            )
        nonfinite = GitHubResponse(
            status=200,
            headers=(("Content-Type", "application/json"),),
            body=b'{"value":NaN}',
        )
        with self.assertRaisesRegex(GitHubAdapterError, "strict JSON"):
            self.adapter(Transport(nonfinite)).read_branch_sha(
                CANONICAL_REPOSITORY, "main"
            )

    def test_malformed_transport_and_clock_values_fail_closed(self) -> None:
        invalid_status = GitHubResponse(  # type: ignore[arg-type]
            status="200",
            headers=(("Content-Type", "application/json"),),
            body=b"{}",
        )
        with self.assertRaisesRegex(GitHubAdapterError, "invalid data"):
            self.adapter(Transport(invalid_status)).read_branch_sha(
                CANONICAL_REPOSITORY, "main"
            )
        invalid_body = GitHubResponse(  # type: ignore[arg-type]
            status=200,
            headers=(("Content-Type", "application/json"),),
            body="{}",
        )
        with self.assertRaisesRegex(GitHubAdapterError, "invalid data"):
            self.adapter(Transport(invalid_body)).read_branch_sha(
                CANONICAL_REPOSITORY, "main"
            )
        adapter = GitHubAppRestAdapter(
            authority=Authority(),
            tokens=Provider(),
            transport=Transport(),
            clock=lambda: float("nan"),
        )
        with self.assertRaisesRegex(GitHubAdapterError, "clock failed"):
            adapter.read_branch_sha(CANONICAL_REPOSITORY, "main")

    def test_pull_request_listing_is_bounded_and_identity_checked(self) -> None:
        spec = draft_spec()
        adapter = self.adapter(Transport(response([pull_request(spec)])))
        values = adapter.list_pull_requests(CANONICAL_REPOSITORY, BRANCH)
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0].body_sha256, spec.body_sha256)
        self.assertIn("state=all", adapter._transport.requests[0].url)
        wrong_actor = pull_request(spec, actor="bad actor")
        with self.assertRaisesRegex(GitHubAdapterError, "actor"):
            self.adapter(Transport(response([wrong_actor]))).list_pull_requests(
                CANONICAL_REPOSITORY, BRANCH
            )
        closed = pull_request(spec)
        closed["state"] = "closed"
        with self.assertRaises(PublicationConflictError):
            self.adapter(Transport(response([closed]))).open_draft_pull_request(spec)

    def test_open_draft_posts_closed_payload_and_has_no_promotion_surface(self) -> None:
        spec = draft_spec()
        transport = Transport(response([]), response(pull_request(spec), status=201))
        adapter = self.adapter(transport)
        adapter.open_draft_pull_request(spec)
        self.assertEqual([item.method for item in transport.requests], ["GET", "POST"])
        payload = json.loads(transport.requests[-1].body or b"{}")
        self.assertEqual(
            payload,
            {
                "base": "main",
                "body": spec.body,
                "draft": True,
                "head": BRANCH,
                "title": spec.title,
            },
        )
        for method in (
            "read_commit",
            "merge",
            "mark_ready",
            "enable_auto_merge",
            "delete_branch",
        ):
            self.assertFalse(hasattr(adapter, method))

    def test_existing_and_ambiguous_creation_reconcile_only_exact_draft(self) -> None:
        spec = draft_spec()
        existing_transport = Transport(response([pull_request(spec)]))
        self.adapter(existing_transport).open_draft_pull_request(spec)
        self.assertEqual(len(existing_transport.requests), 1)

        ambiguous = Transport(
            response([]),
            RuntimeError(TOKEN_SECRET),
            response([pull_request(spec)]),
        )
        self.adapter(ambiguous).open_draft_pull_request(spec)
        self.assertNotIn(TOKEN_SECRET, repr(ambiguous.requests))

        conflicting = Transport(
            response([pull_request(spec, title="wrong")]),
        )
        with self.assertRaises(PublicationConflictError):
            self.adapter(conflicting).open_draft_pull_request(spec)

    def test_wrong_repository_and_transport_errors_are_sanitized(self) -> None:
        with self.assertRaisesRegex(GitHubAdapterError, "not canonical"):
            self.adapter(Transport()).read_branch_sha("other/repo", "main")
        with self.assertRaises(GitHubAdapterError) as context:
            self.adapter(Transport(RuntimeError(TOKEN_SECRET))).read_branch_sha(
                CANONICAL_REPOSITORY, "main"
            )
        self.assertNotIn(TOKEN_SECRET, str(context.exception))

    def test_independent_authority_and_token_binding_are_required(self) -> None:
        with self.assertRaisesRegex(
            GitHubAdapterError, "evidence digest does not match"
        ):
            replace(authority(), evidence_sha256="0" * 64)
        unbound = replace(token(), authority_sha256="0" * 64)
        with self.assertRaisesRegex(GitHubAdapterError, "not authority bound"):
            self.adapter(Transport(), provider=Provider(unbound)).read_branch_sha(
                CANONICAL_REPOSITORY, "main"
            )
        for change in (
            {"repository_scoped": False},
            {"is_admin": True},
            {"can_bypass_branch_protection": True},
            {"effective_repositories": (CANONICAL_REPOSITORY, "other/repo")},
        ):
            with self.subTest(change=change), self.assertRaises(GitHubAdapterError):
                authority(**change)


if __name__ == "__main__":
    unittest.main()
