"""
schemas.py
----------
The model's raw text output is NOT trusted. Every generation is parsed
into one of these Pydantic models before it's considered "done." This
is the "Pydantic Validation" gate at the end of the architecture flow.

Why this matters at production level:
An LLM can return well-formed prose that is still structurally wrong
(missing a CTA, no hashtags when the platform needs them, wrong field
names in JSON mode). Pydantic turns "looks right" into "IS right, or
we retry."
"""

from pydantic import BaseModel, Field, field_validator


class GenerationRequest(BaseModel):
    """The compiled input contract for a single generation."""

    product_name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    platform: str = Field(..., description="linkedin | instagram | twitter | email | facebook")
    tone: str = Field(..., description="e.g. witty, professional, urgent, luxury")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("platform")
    @classmethod
    def platform_lowercase(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("tone")
    @classmethod
    def tone_lowercase(cls, v: str) -> str:
        return v.strip().lower()


class MarketingCopy(BaseModel):
    """The structured output contract the model MUST satisfy."""

    headline: str = Field(..., description="A short, attention-grabbing hook")
    body: str = Field(..., description="The main marketing copy")
    call_to_action: str = Field(..., description="A clear next step for the reader")
    hashtags: list[str] = Field(default_factory=list)
    platform: str
    tone: str
    char_count: int = 0

    def finalize(self) -> "MarketingCopy":
        """Compute char_count after construction (body + headline + cta)."""
        self.char_count = len(self.headline) + len(self.body) + len(self.call_to_action)
        return self


class BatchJobRecord(BaseModel):
    """One row of a bulk CSV input, before it's compiled into a prompt."""

    product_name: str
    description: str
    platform: str
    tone: str
