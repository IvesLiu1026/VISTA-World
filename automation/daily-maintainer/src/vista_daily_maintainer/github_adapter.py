from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Callable, Mapping, Protocol

from .naming import is_v1_daily_branch_name
from .publisher import (
    CANONICAL_REPOSITORY,
    DEFAULT_BRANCH,
    DraftPullRequestSpec,
    GitIdentity,
    PrincipalMode,
    PrincipalSnapshot,
    PublicationConflictError,
    PublicationPreflightError,
    PullRequestSnapshot,
    RepositorySnapshot,
)


GITHUB_API_ORIGIN = "https://api.github.com"
GITHUB_API_VERSION = "2026-03-10"
GITHUB_ACCEPT = "application/vnd.github+json"
EXACT_INSTALLATION_PERMISSIONS = (
    "contents:write",
    "metadata:read",
    "pull_requests:write",
)
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_RESPONSE_HEADERS = 100
MAX_RESPONSE_HEADER_CHARACTERS = 64 * 1024
MAX_REQUEST_BYTES = 64 * 1024
MAX_TEXT_CHARACTERS = 64 * 1024
MIN_TOKEN_REMAINING_SECONDS = 60
MAX_TOKEN_LIFETIME_SECONDS = 3700
MAX_AUTHORITY_LIFETIME_SECONDS = 3700
MAX_GET_ATTEMPTS = 3

_ACTOR = re.compile(
    r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})|"
    r"[A-Za-z0-9][A-Za-z0-9-]{0,93}\[bot\])$"
)
_OBJECT_ID = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_ATTESTOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,127}$")


class GitHubAdapterError(PublicationPreflightError):
    """A sanitized, fail-closed GitHub adapter failure."""


@dataclass(frozen=True)
class GitHubAppAuthorityAttestation:
    """Short-lived T3 evidence produced outside the token provider.

    The attestor must independently inspect the protected policy, effective
    installation repository set, and all branch/ruleset bypass actors.  The
    publishing App deliberately lacks the administrative authority required to
    self-certify the absence of those bypasses.
    """

    issued_at: int
    expires_at: int
    app_id: int
    installation_id: int
    actor: str
    repository: str
    effective_repositories: tuple[str, ...]
    permissions: tuple[str, ...]
    repository_scoped: bool
    is_admin: bool
    can_bypass_branch_protection: bool
    committer: GitIdentity
    attested_by: str
    protected_policy_sha256: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        for name in ("issued_at", "expires_at", "app_id", "installation_id"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise GitHubAdapterError(f"App authority {name} is invalid")
        if (
            self.expires_at <= self.issued_at
            or self.expires_at - self.issued_at > MAX_AUTHORITY_LIFETIME_SECONDS
        ):
            raise GitHubAdapterError("App authority lifetime is invalid")
        if self.repository != CANONICAL_REPOSITORY:
            raise GitHubAdapterError("App authority repository is not canonical")
        if self.effective_repositories != (CANONICAL_REPOSITORY,):
            raise GitHubAdapterError("App authority repository set is not exact")
        if self.permissions != EXACT_INSTALLATION_PERMISSIONS:
            raise GitHubAdapterError("App authority permissions are not exact")
        if not isinstance(self.actor, str) or not _ACTOR.fullmatch(self.actor):
            raise GitHubAdapterError("App authority actor is invalid")
        if not isinstance(self.committer, GitIdentity):
            raise GitHubAdapterError("App authority committer is invalid")
        if (
            self.repository_scoped is not True
            or self.is_admin is not False
            or self.can_bypass_branch_protection is not False
        ):
            raise GitHubAdapterError(
                "App authority is privileged or not repository scoped"
            )
        if not isinstance(self.attested_by, str) or not _ATTESTOR.fullmatch(
            self.attested_by
        ):
            raise GitHubAdapterError("App authority attestor is invalid")
        if not isinstance(self.protected_policy_sha256, str) or not _SHA256.fullmatch(
            self.protected_policy_sha256
        ):
            raise GitHubAdapterError("App authority policy digest is invalid")
        if not isinstance(self.evidence_sha256, str) or not _SHA256.fullmatch(
            self.evidence_sha256
        ):
            raise GitHubAdapterError("App authority evidence digest is invalid")
        if self.evidence_sha256 != _authority_evidence_digest(self):
            raise GitHubAdapterError("App authority evidence digest does not match")

    @classmethod
    def attest(
        cls,
        *,
        issued_at: int,
        expires_at: int,
        app_id: int,
        installation_id: int,
        actor: str,
        repository: str,
        effective_repositories: tuple[str, ...],
        permissions: tuple[str, ...],
        repository_scoped: bool,
        is_admin: bool,
        can_bypass_branch_protection: bool,
        committer: GitIdentity,
        attested_by: str,
        protected_policy_sha256: str,
    ) -> GitHubAppAuthorityAttestation:
        values = {
            "issued_at": issued_at,
            "expires_at": expires_at,
            "app_id": app_id,
            "installation_id": installation_id,
            "actor": actor,
            "repository": repository,
            "effective_repositories": effective_repositories,
            "permissions": permissions,
            "repository_scoped": repository_scoped,
            "is_admin": is_admin,
            "can_bypass_branch_protection": can_bypass_branch_protection,
            "committer": committer,
            "attested_by": attested_by,
            "protected_policy_sha256": protected_policy_sha256,
        }
        provisional = cls.__new__(cls)
        for name, value in values.items():
            object.__setattr__(provisional, name, value)
        evidence_sha256 = _authority_evidence_digest(provisional)
        return cls(**values, evidence_sha256=evidence_sha256)


class GitHubAppAuthorityPort(Protocol):
    def read(self, repository: str) -> GitHubAppAuthorityAttestation: ...


@dataclass(frozen=True)
class InstallationToken:
    token: str = field(repr=False, compare=False)
    issued_at: int
    expires_at: int
    app_id: int
    installation_id: int
    actor: str
    repository: str
    permissions: tuple[str, ...]
    committer: GitIdentity
    authority_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.token) is not str
            or not 20 <= len(self.token) <= 512
            or any(character.isspace() for character in self.token)
            or _CONTROL.search(self.token)
        ):
            raise GitHubAdapterError("installation token is invalid")
        for name in ("issued_at", "expires_at", "app_id", "installation_id"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise GitHubAdapterError(f"installation token {name} is invalid")
        if (
            self.expires_at <= self.issued_at
            or self.expires_at - self.issued_at > MAX_TOKEN_LIFETIME_SECONDS
        ):
            raise GitHubAdapterError("installation token lifetime is invalid")
        if self.repository != CANONICAL_REPOSITORY:
            raise GitHubAdapterError("installation token repository is not canonical")
        if self.permissions != EXACT_INSTALLATION_PERMISSIONS:
            raise GitHubAdapterError("installation token permissions are not exact")
        if not isinstance(self.actor, str) or not _ACTOR.fullmatch(self.actor):
            raise GitHubAdapterError("installation token actor is invalid")
        if not isinstance(self.committer, GitIdentity):
            raise GitHubAdapterError("installation token committer is invalid")
        if not isinstance(self.authority_sha256, str) or not _SHA256.fullmatch(
            self.authority_sha256
        ):
            raise GitHubAdapterError("installation authority digest is invalid")

    @classmethod
    def bind(
        cls,
        *,
        token: str,
        issued_at: int,
        expires_at: int,
        app_id: int,
        installation_id: int,
        actor: str,
        repository: str,
        permissions: tuple[str, ...],
        committer: GitIdentity,
        authority_sha256: str,
    ) -> InstallationToken:
        return cls(
            token=token,
            issued_at=issued_at,
            expires_at=expires_at,
            app_id=app_id,
            installation_id=installation_id,
            actor=actor,
            repository=repository,
            permissions=permissions,
            committer=committer,
            authority_sha256=authority_sha256,
        )


class InstallationTokenProvider(Protocol):
    def issue(self, repository: str) -> InstallationToken: ...


@dataclass(frozen=True)
class GitHubRequest:
    method: str
    url: str
    body: bytes | None
    authorization: str = field(repr=False, compare=False)

    @property
    def headers(self) -> tuple[tuple[str, str], ...]:
        return (
            ("Accept", GITHUB_ACCEPT),
            ("Authorization", self.authorization),
            ("Content-Type", "application/json"),
            ("User-Agent", "vista-world-daily-maintainer/0.1"),
            ("X-GitHub-Api-Version", GITHUB_API_VERSION),
        )


@dataclass(frozen=True)
class GitHubResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes = field(repr=False)


class GitHubTransport(Protocol):
    """Trusted transport that enforces bounds while streaming the response.

    A production implementation must pin normal verified TLS to api.github.com,
    disable proxies and redirects, and stop reading as soon as any supplied
    body/header bound is exceeded.  Returning an already-unbounded buffer does
    not satisfy this port contract.
    """

    def send(
        self,
        request: GitHubRequest,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
        max_response_headers: int,
        max_response_header_characters: int,
    ) -> GitHubResponse: ...


class GitHubAppRestAdapter:
    """Draft-only GitHub port backed by a short-lived installation token.

    Token minting and App-JWT custody intentionally remain outside this adapter.
    Independent, protected T3 authority evidence is re-read separately from the
    token provider before every request and is pinned for the adapter lifetime.
    Remote commit content is intentionally outside this REST surface: the Git
    adapter must fetch the exact branch OID and recompute the canonical patch
    digest from real Git objects before Publisher accepts reconciliation.
    """

    def __init__(
        self,
        *,
        authority: GitHubAppAuthorityPort,
        tokens: InstallationTokenProvider,
        transport: GitHubTransport,
        clock: Callable[[], float] = time.time,
        timeout_seconds: float = 15.0,
    ) -> None:
        if not callable(clock):
            raise GitHubAdapterError("GitHub clock is invalid")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 0 < timeout_seconds <= 30
        ):
            raise GitHubAdapterError("GitHub timeout is invalid")
        self._authority = authority
        self._tokens = tokens
        self._transport = transport
        self._clock = clock
        self._timeout_seconds = float(timeout_seconds)
        self._authority_sha256: str | None = None

    def inspect_principal(
        self, repository: str, mode: PrincipalMode
    ) -> PrincipalSnapshot:
        self._require_repository(repository)
        if mode is not PrincipalMode.GITHUB_APP:
            raise GitHubAdapterError("GitHub App adapter requires GitHub App mode")
        binding, authority = self._binding()
        payload, headers = self._request_json(
            "GET",
            "/installation/repositories",
            query=(("page", "1"), ("per_page", "100")),
            binding=binding,
        )
        self._reject_next_page(headers)
        mapping = _mapping(payload, "installation repositories")
        repositories = _list(mapping.get("repositories"), "installation repositories")
        total = _integer(mapping.get("total_count"), "installation repository count")
        if total != 1 or len(repositories) != 1:
            raise GitHubAdapterError("GitHub App installation is not repository-scoped")
        repository_view = _mapping(repositories[0], "installation repository")
        if (
            _string(repository_view.get("full_name"), "repository full name")
            != repository
        ):
            raise GitHubAdapterError(
                "GitHub App installation repository does not match"
            )
        return PrincipalSnapshot(
            mode=PrincipalMode.GITHUB_APP,
            actor=authority.actor,
            app_id=authority.app_id,
            installation_id=authority.installation_id,
            repository=repository,
            permissions=authority.permissions,
            repository_scoped=authority.repository_scoped,
            is_admin=authority.is_admin,
            can_bypass_branch_protection=authority.can_bypass_branch_protection,
            committer=authority.committer,
            authority_sha256=authority.evidence_sha256,
            protected_policy_sha256=authority.protected_policy_sha256,
        )

    def inspect_repository(self, repository: str) -> RepositorySnapshot:
        self._require_repository(repository)
        payload, _headers = self._request_json("GET", self._repo_path())
        mapping = _mapping(payload, "repository")
        full_name = _string(mapping.get("full_name"), "repository full name")
        default_branch = _string(mapping.get("default_branch"), "default branch")
        private = _boolean(mapping.get("private"), "repository private flag")
        fork = _boolean(mapping.get("fork"), "repository fork flag")
        if full_name != repository:
            raise GitHubAdapterError("remote repository identity does not match")
        main_sha = self.read_branch_sha(repository, DEFAULT_BRANCH)
        if main_sha is None:
            raise GitHubAdapterError("remote main branch is missing")
        return RepositorySnapshot(
            repository=repository,
            default_branch=default_branch,
            main_sha=main_sha,
            public=not private,
            is_fork=fork,
        )

    def read_branch_sha(self, repository: str, branch: str) -> str | None:
        self._require_repository(repository)
        _validate_branch(branch)
        encoded = urllib.parse.quote(branch, safe="")
        payload, _headers = self._request_json(
            "GET",
            f"{self._repo_path()}/git/ref/heads/{encoded}",
            allow_not_found=True,
        )
        if payload is None:
            return None
        mapping = _mapping(payload, "Git reference")
        if _string(mapping.get("ref"), "Git reference name") != f"refs/heads/{branch}":
            raise GitHubAdapterError("Git reference name does not match")
        target = _mapping(mapping.get("object"), "Git reference target")
        if _string(target.get("type"), "Git reference type") != "commit":
            raise GitHubAdapterError("Git reference does not target a commit")
        return _object_id(target.get("sha"), "Git reference SHA")

    def list_pull_requests(
        self, repository: str, head_branch: str
    ) -> tuple[PullRequestSnapshot, ...]:
        self._require_repository(repository)
        _validate_daily_branch(head_branch)
        payload, headers = self._request_json(
            "GET",
            f"{self._repo_path()}/pulls",
            query=(
                ("base", DEFAULT_BRANCH),
                ("head", f"IvesLiu1026:{head_branch}"),
                ("page", "1"),
                ("per_page", "100"),
                ("state", "all"),
            ),
        )
        self._reject_next_page(headers)
        values = _list(payload, "pull requests")
        if len(values) > 2:
            raise GitHubAdapterError("pull request result is oversized")
        snapshots = tuple(
            sorted(
                (self._pull_request(item, head_branch) for item in values),
                key=lambda item: item.number,
            )
        )
        if len({item.number for item in snapshots}) != len(snapshots):
            raise GitHubAdapterError("pull request numbers are duplicated")
        return snapshots

    def open_draft_pull_request(self, spec: DraftPullRequestSpec) -> None:
        if not isinstance(spec, DraftPullRequestSpec):
            raise GitHubAdapterError("draft pull request spec is invalid")
        self._require_repository(spec.repository)
        if not spec.draft:
            raise GitHubAdapterError("GitHub adapter only creates draft PRs")
        existing = self.list_pull_requests(spec.repository, spec.head_branch)
        if existing:
            self._require_reconcilable_pr(existing, spec)
            return
        body = _canonical_json_bytes(
            {
                "base": spec.base_branch,
                "body": spec.body,
                "draft": True,
                "head": spec.head_branch,
                "title": spec.title,
            }
        )
        try:
            self._request_json("POST", f"{self._repo_path()}/pulls", body=body)
        except GitHubAdapterError:
            reconciled = self.list_pull_requests(spec.repository, spec.head_branch)
            if reconciled:
                self._require_reconcilable_pr(reconciled, spec)
                return
            raise

    def _pull_request(self, value: object, head_branch: str) -> PullRequestSnapshot:
        mapping = _mapping(value, "pull request")
        number = _integer(mapping.get("number"), "pull request number")
        if number < 1:
            raise GitHubAdapterError("pull request number is invalid")
        url = _string(mapping.get("html_url"), "pull request URL")
        expected_url = f"https://github.com/{CANONICAL_REPOSITORY}/pull/{number}"
        if url != expected_url:
            raise GitHubAdapterError("pull request URL does not match")
        base = _mapping(mapping.get("base"), "pull request base")
        head = _mapping(mapping.get("head"), "pull request head")
        head_repo = _mapping(head.get("repo"), "pull request head repository")
        if (
            _string(base.get("ref"), "pull request base branch") != DEFAULT_BRANCH
            or _string(head.get("ref"), "pull request head branch") != head_branch
            or _string(head_repo.get("full_name"), "pull request head repository")
            != CANONICAL_REPOSITORY
        ):
            raise GitHubAdapterError("pull request branch identity does not match")
        user = _mapping(mapping.get("user"), "pull request user")
        actor = _string(user.get("login"), "pull request actor")
        if not _ACTOR.fullmatch(actor):
            raise GitHubAdapterError("pull request actor is invalid")
        body = _multiline_text(mapping.get("body"), "pull request body")
        return PullRequestSnapshot(
            number=number,
            url=url,
            repository=CANONICAL_REPOSITORY,
            base_branch=DEFAULT_BRANCH,
            head_branch=head_branch,
            head_sha=_object_id(head.get("sha"), "pull request head SHA"),
            actor=actor,
            title=_string(mapping.get("title"), "pull request title"),
            body_sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
            state=_string(mapping.get("state"), "pull request state"),
            draft=_boolean(mapping.get("draft"), "pull request draft flag"),
        )

    @staticmethod
    def _require_reconcilable_pr(
        values: tuple[PullRequestSnapshot, ...], spec: DraftPullRequestSpec
    ) -> None:
        if len(values) != 1:
            raise PublicationConflictError("draft pull request cannot be reconciled")
        existing = values[0]
        if (
            existing.repository != spec.repository
            or existing.base_branch != spec.base_branch
            or existing.head_branch != spec.head_branch
            or existing.title != spec.title
            or existing.body_sha256 != spec.body_sha256
            or existing.state != "open"
            or not existing.draft
        ):
            raise PublicationConflictError("existing pull request does not match")

    def _binding(
        self,
    ) -> tuple[InstallationToken, GitHubAppAuthorityAttestation]:
        try:
            authority = self._authority.read(CANONICAL_REPOSITORY)
        except Exception:
            raise GitHubAdapterError("App authority reader failed") from None
        if not isinstance(authority, GitHubAppAuthorityAttestation):
            raise GitHubAdapterError("App authority reader returned invalid data")
        now = self._now()
        if (
            now < authority.issued_at - 30
            or authority.expires_at - now < MIN_TOKEN_REMAINING_SECONDS
        ):
            raise GitHubAdapterError("App authority is stale or not yet valid")
        if self._authority_sha256 is None:
            self._authority_sha256 = authority.evidence_sha256
        elif authority.evidence_sha256 != self._authority_sha256:
            raise GitHubAdapterError("App authority changed during publication")
        try:
            binding = self._tokens.issue(CANONICAL_REPOSITORY)
        except Exception:
            raise GitHubAdapterError("installation token provider failed") from None
        if not isinstance(binding, InstallationToken):
            raise GitHubAdapterError(
                "installation token provider returned invalid data"
            )
        if (
            now < binding.issued_at - 30
            or binding.expires_at - now < MIN_TOKEN_REMAINING_SECONDS
        ):
            raise GitHubAdapterError("installation token is stale or not yet valid")
        if (
            binding.authority_sha256 != authority.evidence_sha256
            or binding.app_id != authority.app_id
            or binding.installation_id != authority.installation_id
            or binding.actor != authority.actor
            or binding.repository != authority.repository
            or binding.permissions != authority.permissions
            or binding.committer != authority.committer
        ):
            raise GitHubAdapterError("installation token is not authority bound")
        return binding, authority

    def _now(self) -> int:
        try:
            return int(self._clock())
        except (OverflowError, TypeError, ValueError):
            raise GitHubAdapterError("GitHub clock failed") from None

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        query: tuple[tuple[str, str], ...] = (),
        body: bytes | None = None,
        allow_not_found: bool = False,
        binding: InstallationToken | None = None,
    ) -> tuple[object | None, Mapping[str, str]]:
        if method not in {"GET", "POST"}:
            raise GitHubAdapterError("GitHub method is not allowlisted")
        if not path.startswith("/") or "//" in path or _CONTROL.search(path):
            raise GitHubAdapterError("GitHub API path is invalid")
        if body is not None and (len(body) > MAX_REQUEST_BYTES or method != "POST"):
            raise GitHubAdapterError("GitHub request body is invalid")
        encoded_query = urllib.parse.urlencode(sorted(query))
        url = f"{GITHUB_API_ORIGIN}{path}"
        if encoded_query:
            url = f"{url}?{encoded_query}"
        parsed = urllib.parse.urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "api.github.com"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise GitHubAdapterError("GitHub API origin is invalid")

        attempts = MAX_GET_ATTEMPTS if method == "GET" else 1
        last_response: GitHubResponse | None = None
        for _attempt in range(attempts):
            request_binding = binding or self._binding()[0]
            request = GitHubRequest(
                method=method,
                url=url,
                body=body,
                authorization=f"Bearer {request_binding.token}",
            )
            try:
                response = self._transport.send(
                    request,
                    timeout_seconds=self._timeout_seconds,
                    max_response_bytes=MAX_RESPONSE_BYTES,
                    max_response_headers=MAX_RESPONSE_HEADERS,
                    max_response_header_characters=MAX_RESPONSE_HEADER_CHARACTERS,
                )
            except Exception:
                raise GitHubAdapterError("GitHub transport failed") from None
            if not isinstance(response, GitHubResponse):
                raise GitHubAdapterError("GitHub transport returned invalid data")
            if (
                isinstance(response.status, bool)
                or not isinstance(response.status, int)
                or not 100 <= response.status <= 599
                or type(response.body) is not bytes
            ):
                raise GitHubAdapterError("GitHub transport returned invalid data")
            if len(response.body) > MAX_RESPONSE_BYTES:
                raise GitHubAdapterError("GitHub response is oversized")
            _headers(response.headers)
            if 300 <= response.status < 400:
                raise GitHubAdapterError("GitHub redirect is forbidden")
            if method == "GET" and response.status in {502, 503, 504}:
                last_response = response
                continue
            last_response = response
            break
        if last_response is None:
            raise GitHubAdapterError("GitHub request did not complete")
        response = last_response
        headers = _headers(response.headers)
        if allow_not_found and response.status == 404:
            return None, headers
        expected_status = 201 if method == "POST" else 200
        if response.status != expected_status:
            raise GitHubAdapterError("GitHub API returned an unexpected status")
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type not in {"application/json", "application/vnd.github+json"}:
            raise GitHubAdapterError("GitHub response content type is invalid")
        try:
            decoded = response.body.decode("utf-8", "strict")
            payload = json.loads(
                decoded,
                object_pairs_hook=_strict_pairs,
                parse_constant=_reject_json_constant,
            )
        except (
            UnicodeDecodeError,
            ValueError,
            RecursionError,
            GitHubAdapterError,
        ):
            raise GitHubAdapterError("GitHub response is not strict JSON") from None
        return payload, headers

    @staticmethod
    def _reject_next_page(headers: Mapping[str, str]) -> None:
        if 'rel="next"' in headers.get("link", ""):
            raise GitHubAdapterError("paginated GitHub response exceeds the bound")

    @staticmethod
    def _require_repository(repository: str) -> None:
        if repository != CANONICAL_REPOSITORY:
            raise GitHubAdapterError("GitHub repository is not canonical")

    @staticmethod
    def _repo_path() -> str:
        owner, name = CANONICAL_REPOSITORY.split("/", 1)
        return f"/repos/{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(name, safe='')}"


def _authority_evidence_digest(value: GitHubAppAuthorityAttestation) -> str:
    payload = {
        "schema_version": "vista.world.daily-maintainer.github-app-authority.v2",
        "issued_at": value.issued_at,
        "expires_at": value.expires_at,
        "app_id": value.app_id,
        "installation_id": value.installation_id,
        "actor": value.actor,
        "repository": value.repository,
        "effective_repositories": list(value.effective_repositories),
        "permissions": list(value.permissions),
        "repository_scoped": value.repository_scoped,
        "is_admin": value.is_admin,
        "can_bypass_branch_protection": value.can_bypass_branch_protection,
        "committer": {
            "name": value.committer.name,
            "email": value.committer.email,
        },
        "attested_by": value.attested_by,
        "protected_policy_sha256": value.protected_policy_sha256,
    }
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise GitHubAdapterError("GitHub JSON payload is invalid") from exc


def _strict_pairs(values: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in values:
        if key in result:
            raise GitHubAdapterError("GitHub response contains duplicate keys")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise GitHubAdapterError("GitHub response contains a non-finite number")


def _headers(values: tuple[tuple[str, str], ...]) -> Mapping[str, str]:
    if not isinstance(values, tuple) or len(values) > MAX_RESPONSE_HEADERS:
        raise GitHubAdapterError("GitHub response headers are invalid")
    result: dict[str, str] = {}
    character_count = 0
    for item in values:
        if (
            not isinstance(item, tuple)
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not str
            or _CONTROL.search(item[0])
            or _CONTROL.search(item[1])
        ):
            raise GitHubAdapterError("GitHub response header is invalid")
        character_count += len(item[0]) + len(item[1])
        if character_count > MAX_RESPONSE_HEADER_CHARACTERS:
            raise GitHubAdapterError("GitHub response headers are oversized")
        name = item[0].lower()
        if name in result:
            raise GitHubAdapterError("GitHub response header is duplicated")
        result[name] = item[1]
    return result


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise GitHubAdapterError(f"{label} is not an object")
    return value


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise GitHubAdapterError(f"{label} is not a list")
    return value


def _string(value: object, label: str) -> str:
    if type(value) is not str or not value or _CONTROL.search(value):
        raise GitHubAdapterError(f"{label} is invalid")
    return value


def _multiline_text(value: object, label: str) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > MAX_TEXT_CHARACTERS
        or "\r" in value
        or any(
            ord(character) < 32 and character not in {"\n", "\t"} for character in value
        )
        or "\x7f" in value
    ):
        raise GitHubAdapterError(f"{label} is invalid")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise GitHubAdapterError(f"{label} is invalid")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GitHubAdapterError(f"{label} is invalid")
    return value


def _object_id(value: object, label: str) -> str:
    text = _string(value, label)
    if not _OBJECT_ID.fullmatch(text):
        raise GitHubAdapterError(f"{label} is invalid")
    return text


def _validate_branch(branch: str) -> None:
    if branch == DEFAULT_BRANCH:
        return
    _validate_daily_branch(branch)


def _validate_daily_branch(branch: str) -> None:
    if not is_v1_daily_branch_name(branch):
        raise GitHubAdapterError("GitHub branch is invalid")
