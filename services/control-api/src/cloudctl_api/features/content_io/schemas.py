"""F11 content-io request schemas.

Reuses the frozen ``ProductImportItem`` contract from the legacy
``/products:import`` surface so both entry points validate identical rows;
this slice only adds the dry-run/apply policy and the import key.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ...schemas import ProductImportItem


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ContentImportRunRequest(StrictModel):
    items: list[ProductImportItem] = Field(min_length=1, max_length=100)
    group_id: str | None = Field(default=None, alias="groupId", min_length=1, max_length=36)
    apply: bool = False
    import_key: str | None = Field(
        default=None, alias="importKey", min_length=1, max_length=128
    )
