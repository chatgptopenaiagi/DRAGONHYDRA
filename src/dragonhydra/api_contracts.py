"""Version-one API resources. All clocks are UTC; source dates remain date-only."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SessionInput(Input):
    token: str = Field(min_length=20, max_length=200)


class SyncInput(Input):
    mode: Literal['retained', 'fresh'] = 'retained'


class ConnectionInput(Input):
    config: dict = Field(default_factory=dict)
    interval_seconds: int = Field(default=0, ge=0, le=604800)
    credential: str | None = Field(default=None, min_length=1, max_length=4096, repr=False)
    remove_credential: bool = False


class LocalModelInput(Input):
    endpoint: str = Field(max_length=256)
    credential: str | None = Field(default=None, min_length=20, max_length=4096, repr=False)
    remove_credential: bool = False


class ExportInput(Input):
    match_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    format: Literal['xlsx', 'json', 'csv'] = 'xlsx'


class JobInput(Input):
    kind: Literal['import_public', 'explanation', 'export']
    mode: Literal['retained', 'fresh'] = 'retained'
    match_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    format: Literal['xlsx', 'json', 'csv'] = 'xlsx'


class EmptyInput(Input):
    pass


class LocalExplanationInput(Input):
    context_record_id: str | None = Field(default=None, strict=True, pattern=r'^source_context:[a-f0-9]{64}$')

    @model_validator(mode='before')
    @classmethod
    def explicit_context_must_not_be_null(cls, value):
        if isinstance(value, dict) and 'context_record_id' in value and value['context_record_id'] is None:
            raise ValueError('A supplied context record ID must be a string.')
        return value


class TeamRef(BaseModel):
    id: str
    name: str


class Score(BaseModel):
    home: int
    away: int


class Match(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str
    version: str
    identity_version: int
    competition_id: str
    competition: str
    season: str | None
    home: TeamRef
    away: TeamRef
    event_date: str
    kickoff_utc: str | None
    time_precision: str
    status: Literal['finished', 'scheduled', 'live', 'cancelled', 'synthetic']
    score: Score | None
    source_id: str
    source_url: str
    evidence_id: str
    received_at: str
    usable_at: str
    data_state: str
    capabilities: dict[str, bool]


class MatchPage(BaseModel):
    items: list[Match]
    total: int
    limit: int
    offset: int
    as_of: str
    timestamp_semantics: str


class Job(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str
    owner: str
    kind: str
    status: Literal['queued', 'running', 'succeeded', 'failed', 'cancelled', 'interrupted']
    progress: int
    attempts: int
    created_at: str
    updated_at: str
    heartbeat: float | None
    lease_until: float | None
    deadline: float | None
    result: dict | None
    error: dict | None


class Health(BaseModel):
    status: str
    backend: Literal['sqlite']
    version: str
    schema_version: int
    optional_ai: str
    source_sha: str | None = None
