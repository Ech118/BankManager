"""Unit tests for predictions.logger (plan.txt 15.14 P2 step 8: "append-only
log writer: file per run named <date>_<ticker>_<inputhash>.json")."""
import json
from pathlib import Path

from predictions.logger import grade_prediction, list_predictions, log_prediction


def load_verdict():
    fixtures = Path(__file__).resolve().parents[2] / "fixtures" / "mock"
    return json.loads((fixtures / "verdict.json").read_text())


def test_log_prediction_writes_the_documented_filename_shape(tmp_path):
    verdict = load_verdict()
    path = log_prediction("ACME", "2026-09-19", verdict, log_dir=tmp_path)
    assert path.parent == tmp_path
    assert path.name.startswith("2026-09-19_ACME_")
    assert path.name.endswith(".json")
    record = json.loads(path.read_text())
    assert record["ticker"] == "ACME"
    assert record["predicted_verdict"] == verdict["card"]["verdict"]
    assert record["graded"] is False


def test_log_prediction_is_idempotent_for_identical_inputs(tmp_path):
    verdict = load_verdict()
    p1 = log_prediction("ACME", "2026-09-19", verdict, log_dir=tmp_path)
    p2 = log_prediction("ACME", "2026-09-19", verdict, log_dir=tmp_path)
    assert p1 == p2
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_log_prediction_never_overwrites_an_existing_file(tmp_path):
    verdict = load_verdict()
    path = log_prediction("ACME", "2026-09-19", verdict, log_dir=tmp_path)
    original = path.read_text()
    path.write_text('{"tampered": true}')
    log_prediction("ACME", "2026-09-19", verdict, log_dir=tmp_path)
    assert path.read_text() == '{"tampered": true}'  # logger must not have rewritten it
    assert original != path.read_text()  # sanity: the tamper actually took effect


def test_list_predictions_filters_by_ticker(tmp_path):
    verdict = load_verdict()
    log_prediction("ACME", "2026-09-19", verdict, log_dir=tmp_path)
    log_prediction("OTHER", "2026-09-19", verdict, log_dir=tmp_path)
    assert len(list_predictions(log_dir=tmp_path)) == 2
    assert len(list_predictions(ticker="ACME", log_dir=tmp_path)) == 1


def test_list_predictions_on_missing_dir_is_empty(tmp_path):
    assert list_predictions(log_dir=tmp_path / "does_not_exist") == []


def test_grade_prediction_appends_a_new_file_and_leaves_original_untouched(tmp_path):
    verdict = load_verdict()
    log_prediction("ACME", "2026-09-19", verdict, log_dir=tmp_path)
    [record] = list_predictions(ticker="ACME", log_dir=tmp_path)
    original_path = tmp_path / f"2026-09-19_ACME_{record['input_hash']}.json"
    original_before = original_path.read_text()

    graded_path = grade_prediction(record, realized_annualized_return=0.20, log_dir=tmp_path)

    assert graded_path != original_path
    assert original_path.read_text() == original_before
    graded_record = json.loads(graded_path.read_text())
    assert graded_record["graded"] is True
    assert graded_record["grade"]["beat_sp500"] is True
