"""Version-one API resources. All clocks are UTC; source dates remain date-only."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SessionInput(Input):
    token: str = Field(min_length=20, max_length=200)


class SyncInput(Input):
    mode: Literal['retained', 'fresh'] = 'retained'


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
    status: Literal['finished', 'scheduled']
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
