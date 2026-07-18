"""角色市场 Pydantic 请求/响应模型。"""
from pydantic import BaseModel, Field


class PublishRequest(BaseModel):
    market_name: str = Field(..., min_length=1, max_length=64)
    market_description: str = Field(..., min_length=1, max_length=500)
    tags: list[str] = Field(default_factory=list, max_length=10)
    icon: str = Field(default="🤖", max_length=8)


class UpdateListingRequest(BaseModel):
    market_name: str | None = Field(None, max_length=64)
    market_description: str | None = Field(None, max_length=500)
    tags: list[str] | None = None
    icon: str | None = Field(None, max_length=8)
    changelog: str | None = None


class ReviewRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = Field(None, max_length=500)
