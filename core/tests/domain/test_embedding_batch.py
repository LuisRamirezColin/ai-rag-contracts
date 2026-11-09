import pytest

from contract_intel.domain.chunk import Embedding, EmbeddingBatch
from contract_intel.domain.errors import (
    BlankTextError,
    EmbeddingDimensionMismatchError,
    NegativeQuantityError,
)
from contract_intel.domain.ids import DocumentId
from contract_intel.domain.usage import UsageRecord


def _vector(dimensions: int) -> Embedding:
    return Embedding(values=(0.1,) * dimensions)


def test_batch_with_homogeneous_dimensions():
    batch = EmbeddingBatch((_vector(4), _vector(4)), input_tokens=12, model="m")
    assert len(batch.embeddings) == 2


def test_empty_batch_is_valid():
    assert EmbeddingBatch((), input_tokens=0, model="m").embeddings == ()


def test_mixed_dimensions_are_rejected():
    with pytest.raises(EmbeddingDimensionMismatchError):
        EmbeddingBatch((_vector(4), _vector(3)), input_tokens=1, model="m")


def test_negative_tokens_are_rejected():
    with pytest.raises(NegativeQuantityError):
        EmbeddingBatch((), input_tokens=-1, model="m")


def test_blank_model_is_rejected():
    with pytest.raises(BlankTextError):
        EmbeddingBatch((), input_tokens=0, model=" ")


def test_usage_record_can_reference_a_document():
    usage = UsageRecord(
        operation="embed_documents",
        model="voyage-law-2",
        input_tokens=100,
        output_tokens=0,
        cost_usd=0.000012,
        document_id=DocumentId("doc-1"),
    )
    assert usage.document_id == "doc-1"


def test_token_pricing_estimates_cost():
    from contract_intel.domain.usage import TokenPricing

    pricing = TokenPricing(input_per_million=4.0, output_per_million=20.0)

    assert pricing.cost_usd(1_000_000, 500_000) == pytest.approx(14.0)
    assert TokenPricing(input_per_million=0.12).cost_usd(46_000) == pytest.approx(
        0.00552
    )


def test_token_pricing_rejects_negative_prices():
    from contract_intel.domain.usage import TokenPricing

    with pytest.raises(NegativeQuantityError):
        TokenPricing(input_per_million=-1.0)
