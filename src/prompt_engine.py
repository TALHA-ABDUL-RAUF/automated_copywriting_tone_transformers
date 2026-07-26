"""
prompt_engine.py
-----------------
The "Master Instruction Template" from the blueprint.

Core idea (Protecting Brand Voice):
  - The END USER only ever supplies raw facts (product name, description,
    platform, tone).
  - The CODE — not the user — controls the actual structural prompt sent
    to the model. This is "Application Layer as Gatekeeper": no user
    input is ever concatenated directly into an instruction; it's always
    injected as a *value* inside a fixed, brand-safe template.
  - Platform-specific constraints are appended conditionally, not left
    to the model's judgment.

This is deliberately the ONLY place prompt text is constructed. Both
the real-time pipeline and the batch pipeline call this same function,
so brand voice can never drift between the two paths.
"""

from src.config import PLATFORM_RULES
from src.schemas import GenerationRequest

SYSTEM_PROMPT = (
    "You are a senior marketing copywriter at DecodeLabs. You write copy "
    "that is factually grounded in the product description you are given "
    "— never invent features, prices, or claims. You always respond with "
    "STRICT JSON matching the schema you are given, and nothing else: no "
    "markdown fences, no preamble, no trailing commentary."
)


def compile_master_prompt(request: GenerationRequest) -> tuple[str, str]:
    """
    Compiles (system_prompt, user_prompt) for a single generation request.

    Returns a tuple so callers can pass them straight into a
    chat.completions.create(messages=[...]) call.
    """
    platform_key = request.platform.lower()
    rules = PLATFORM_RULES.get(
        platform_key,
        {"max_chars": 2000, "style_hint": "Clear, professional marketing copy."},
    )

    # f-string injection of user-supplied VALUES into a fixed structural
    # template. The user never controls the *shape* of the instruction —
    # only the variables inside it.
    user_prompt = f"""
Generate marketing copy for the following product.

Product Name: {request.product_name}
Product Description: {request.description}
Target Platform: {platform_key}
Requested Tone: {request.tone}

Platform style guide: {rules['style_hint']}
Hard constraint: the combined headline + body + call_to_action MUST NOT
exceed {rules['max_chars']} characters.

Respond with ONLY a JSON object with exactly these keys:
{{
  "headline": "string",
  "body": "string",
  "call_to_action": "string",
  "hashtags": ["string", "..."]
}}
""".strip()

    return SYSTEM_PROMPT, user_prompt


def max_chars_for(platform: str) -> int:
    return PLATFORM_RULES.get(platform.lower(), {}).get("max_chars", 2000)
