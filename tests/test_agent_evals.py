"""Explicit live-agent checks. Run only with: pytest -m agent_eval"""

import os

import pytest

pytestmark = pytest.mark.agent_eval


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY is required for live agent evaluations")
def test_live_agent_evaluations_require_real_dataset():
    pytest.skip("Download assignment SQLite datasets before enabling the live benchmark cases.")
