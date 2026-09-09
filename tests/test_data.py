from unittest.mock import Mock

import requests

from vaimea import data


def test_ingest_can_skip_a_season_that_is_not_published_yet(tmp_path, monkeypatch):
    response = Mock(status_code=404)
    error = requests.HTTPError(response=response)
    monkeypatch.setattr(data, "fetch", Mock(side_effect=error))
    assert data.ingest(tmp_path, [2026], allow_missing=True) == []
