from pydantic import BaseModel, Field, field_validator


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    geo: str = Field(pattern=r"^[A-Za-z]{2}$")
    offer_id: int = Field(gt=0)
    domain_id: int = Field(gt=0)
    group_id: int = Field(gt=0)
    source_id: int = Field(gt=0)

    @field_validator("name")
    @classmethod
    def nonempty_name(cls, value: str):
        value = value.strip()
        if not value:
            raise ValueError("Campaign name is required")
        return value


class AddOffer(BaseModel):
    offer_id: int = Field(gt=0)


class PinOffer(BaseModel):
    pinned: bool
    share: int | None = Field(default=None, ge=0, le=100)
