from obs.analytics.pricing import Price, Pricing
from obs.models import Usage


def test_longest_prefix_wins_and_unknown_is_none():
    pricing = Pricing(
        {
            "gpt-4o": Price(input=2.5, output=10),
            "gpt-4o-mini": Price(input=0.15, output=0.6),
            "claude-sonnet-4": Price(input=3, output=15),
        }
    )
    assert pricing.match("gpt-4o-mini-2025").input == 0.15
    assert pricing.match("gpt-4o-2024").input == 2.5
    assert pricing.match("claude-sonnet-4-20250514").output == 15
    assert pricing.match("gpt-6.1-sol") is None
    assert pricing.estimate("missing", Usage(input_tokens=10, output_tokens=1)) is None
    assert pricing.estimate("gpt-4o", Usage()) is None
