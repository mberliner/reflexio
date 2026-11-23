"""SPEC-104 FR-013: identificador canonico por caso en ambos loaders.

`case_id` si el CSV lo tiene; si no, `<split>:<fila>` con fila 0-based dentro
del split.
"""

from types import SimpleNamespace

import pytest

from dspy_gepa_poc.data_loader import CSVDataLoader
from gepa_standalone.data import data_loader as gepa_loader

# Splits intercalados: la fila es el indice dentro del split, no del CSV.
NO_ID_CSV = "split,text,label\ntrain,a,x\nval,b,y\ntrain,c,x\ntest,d,y\nval,e,x\ntrain,f,y\n"
WITH_ID_CSV = (
    "split,case_id,text,label\n"
    "train,caso-A,a,x\n"
    "val,caso-B,b,y\n"
    "train,caso-C,c,x\n"
    "test,caso-D,d,y\n"
)


@pytest.fixture
def gepa_load(tmp_path, monkeypatch):
    def _load(content, **kwargs):
        (tmp_path / "d.csv").write_text(content, encoding="utf-8")
        fake = SimpleNamespace(dataset=lambda name: str(tmp_path / name))
        monkeypatch.setattr(gepa_loader, "get_paths", lambda: fake)
        return gepa_loader.load_gepa_data("d.csv", **kwargs)

    return _load


@pytest.fixture
def dspy_load(tmp_path):
    def _load(content):
        (tmp_path / "d.csv").write_text(content, encoding="utf-8")
        return CSVDataLoader(datasets_dir=str(tmp_path)).load_dataset("d.csv", ["text"])

    return _load


class TestGepaStandaloneCaseId:
    def test_fallback_is_split_and_row_within_split(self, gepa_load):
        train, val, test = gepa_load(NO_ID_CSV, output_columns=["label"])
        assert [e["case_id"] for e in train] == ["train:0", "train:1", "train:2"]
        assert [e["case_id"] for e in val] == ["val:0", "val:1"]
        assert [e["case_id"] for e in test] == ["test:0"]

    def test_csv_case_id_is_kept(self, gepa_load):
        train, val, test = gepa_load(WITH_ID_CSV, output_columns=["label"])
        assert [e["case_id"] for e in train] == ["caso-A", "caso-C"]
        assert val[0]["case_id"] == "caso-B"
        assert test[0]["case_id"] == "caso-D"

    def test_csv_case_id_not_an_output_column_by_default(self, gepa_load):
        train, _, _ = gepa_load(WITH_ID_CSV)
        assert train[0]["case_id"] == "caso-A"
        assert train[0]["label"] == "x"
        assert "extracted" not in train[0]

    def test_case_id_present_with_multiple_outputs(self, gepa_load):
        csv_text = "split,text,a,b\ntrain,t,1,2\ntrain,u,3,4\n"
        train, _, _ = gepa_load(csv_text, output_columns=["a", "b"])
        assert [e["case_id"] for e in train] == ["train:0", "train:1"]
        assert train[0]["extracted"] == {"a": "1", "b": "2"}

    def test_blank_csv_case_id_falls_back(self, gepa_load):
        csv_text = "split,case_id,text,label\ntrain,,a,x\ntrain, k1 ,b,y\n"
        train, _, _ = gepa_load(csv_text, output_columns=["label"])
        assert [e["case_id"] for e in train] == ["train:0", "k1"]

    def test_ids_unique_across_splits(self, gepa_load):
        train, val, test = gepa_load(NO_ID_CSV, output_columns=["label"])
        ids = [e["case_id"] for e in train + val + test]
        assert len(ids) == len(set(ids))


class TestDspyCaseId:
    def test_fallback_is_split_and_row_within_split(self, dspy_load):
        train, val, test = dspy_load(NO_ID_CSV)
        assert [e.case_id for e in train] == ["train:0", "train:1", "train:2"]
        assert [e.case_id for e in val] == ["val:0", "val:1"]
        assert [e.case_id for e in test] == ["test:0"]

    def test_csv_case_id_is_kept(self, dspy_load):
        train, val, test = dspy_load(WITH_ID_CSV)
        assert [e.case_id for e in train] == ["caso-A", "caso-C"]
        assert val[0].case_id == "caso-B"
        assert test[0].case_id == "caso-D"

    def test_case_id_is_not_an_input(self, dspy_load):
        train, _, _ = dspy_load(NO_ID_CSV)
        assert "case_id" not in train[0].inputs().keys()
        assert "case_id" in train[0].labels().keys()

    def test_blank_csv_case_id_falls_back(self, dspy_load):
        csv_text = "split,case_id,text,label\ntrain,,a,x\ntrain,k1,b,y\n"
        train, _, _ = dspy_load(csv_text)
        assert [e.case_id for e in train] == ["train:0", "k1"]

    def test_rows_without_split_do_not_consume_an_index(self, dspy_load):
        csv_text = "split,text,label\ntrain,a,x\n,b,y\ntrain,c,x\n"
        train, _, _ = dspy_load(csv_text)
        assert [e.case_id for e in train] == ["train:0", "train:1"]
