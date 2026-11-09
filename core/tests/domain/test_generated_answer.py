import pytest

from contract_intel.domain.answer import Answer, GeneratedAnswer
from contract_intel.domain.errors import (
    AnswerRefusedError,
    BlankTextError,
    NegativeQuantityError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
)

ANSWER = Answer(question="Which law governs?", text="New York law.")


def test_generated_answer_carries_model_and_tokens():
    generated = GeneratedAnswer(ANSWER, "claude-sonnet-5-5", 7_500, 900)
    assert generated.answer is ANSWER
    assert (generated.input_tokens, generated.output_tokens) == (7_500, 900)


@pytest.mark.parametrize(("input_tokens", "output_tokens"), [(-1, 0), (0, -1)])
def test_negative_tokens_are_rejected(input_tokens, output_tokens):
    with pytest.raises(NegativeQuantityError):
        GeneratedAnswer(ANSWER, "m", input_tokens, output_tokens)


def test_blank_model_is_rejected():
    with pytest.raises(BlankTextError):
        GeneratedAnswer(ANSWER, " ", 1, 1)


def test_provider_errors_name_the_provider():
    assert ProviderRateLimitedError("voyage", "3 RPM").provider == "voyage"
    assert "anthropic" in str(ProviderUnavailableError("anthropic", "timeout"))


def test_refusal_keeps_its_category():
    assert AnswerRefusedError("cyber").category == "cyber"
    assert "category" not in str(AnswerRefusedError(None))
