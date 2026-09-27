import pytest

from src.providers.error_tracking import traces_sampler


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/egx/stocks", 0.1),
        ("/health/live", 0.0),
        ("/health/ready", 0.0),
    ],
)
def test_probes_are_never_traced(
    path: str,
    expected: float,
) -> None:
    context = {"asgi_scope": {"path": path}}

    assert traces_sampler(context, rate=0.1) == expected


def test_work_outside_a_request_is_sampled() -> None:
    assert traces_sampler({}, rate=0.1) == 0.1
