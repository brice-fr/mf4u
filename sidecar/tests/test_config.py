"""
Tests for save_config / load_config handlers in __main__.py.

Covers the path-relativisation round-trip: DBC paths and output_folder are
stored as paths relative to the config file's location and resolved back to
absolute paths when the config is read back.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

SIDECAR_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SIDECAR_ROOT not in sys.path:
    sys.path.insert(0, SIDECAR_ROOT)

import importlib.util as _ilu

_spec   = _ilu.spec_from_file_location("sidecar_main",
              os.path.join(SIDECAR_ROOT, "__main__.py"))
sidecar = _ilu.module_from_spec(_spec)         # type: ignore[arg-type]
_spec.loader.exec_module(sidecar)              # type: ignore[union-attr]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _save_req(path: str, config: dict) -> dict:
    return {"id": 1, "method": "save_config", "params": {"path": path, "config": config}}


def _load_req(path: str) -> dict:
    return {"id": 2, "method": "load_config", "params": {"path": path}}


# --------------------------------------------------------------------------- #
# _to_relative / _to_absolute unit tests
# --------------------------------------------------------------------------- #

class TestPathHelpers:
    def test_relative_same_dir(self, tmp_path):
        base = str(tmp_path)
        target = str(tmp_path / "can_bus.dbc")
        rel = sidecar._to_relative(target, base)
        assert rel == "can_bus.dbc"

    def test_relative_subdir(self, tmp_path):
        base = str(tmp_path)
        target = str(tmp_path / "dbs" / "can_bus.dbc")
        rel = sidecar._to_relative(target, base)
        assert rel == "dbs/can_bus.dbc"

    def test_relative_parent_dir(self, tmp_path):
        base = str(tmp_path / "configs")
        target = str(tmp_path / "can_bus.dbc")
        rel = sidecar._to_relative(target, base)
        assert rel == "../can_bus.dbc"

    def test_absolute_roundtrip(self, tmp_path):
        base   = str(tmp_path)
        target = str(tmp_path / "dbs" / "can_bus.dbc")
        rel    = sidecar._to_relative(target, base)
        back   = sidecar._to_absolute(rel, base)
        assert back == os.path.normpath(target)

    def test_absolute_path_unchanged(self, tmp_path):
        base   = str(tmp_path)
        target = str(tmp_path / "can_bus.dbc")
        # Already absolute — _to_absolute should normalise but not change it.
        back = sidecar._to_absolute(target, base)
        assert back == os.path.normpath(target)

    def test_uses_forward_slashes(self, tmp_path):
        base   = str(tmp_path)
        target = str(tmp_path / "dbs" / "can_bus.dbc")
        rel    = sidecar._to_relative(target, base)
        assert "\\" not in rel


# --------------------------------------------------------------------------- #
# handle_save_config
# --------------------------------------------------------------------------- #

class TestSaveConfig:
    def test_writes_json_file(self, tmp_path):
        cfg_path = str(tmp_path / "config.mf4u")
        dbc_path = str(tmp_path / "can_bus.dbc")
        config = {
            "version": 1,
            "decoding": [{"group_index": 0, "group_name": "CAN1", "db_path": dbc_path}],
            "channel_filter": None,
            "flatten": False,
            "export_format": "csv",
            "output_folder": str(tmp_path / "exports"),
            "mat_link_groups": True,
        }
        resp = sidecar.handle_save_config(_save_req(cfg_path, config))
        assert resp.get("error") is None
        assert os.path.isfile(cfg_path)

    def test_dbc_path_stored_as_relative(self, tmp_path):
        cfg_path = str(tmp_path / "config.mf4u")
        dbc_path = str(tmp_path / "can_bus.dbc")
        config = {
            "version": 1,
            "decoding": [{"group_index": 0, "group_name": "CAN1", "db_path": dbc_path}],
            "channel_filter": None,
            "flatten": False,
            "export_format": "csv",
            "output_folder": "",
            "mat_link_groups": False,
        }
        sidecar.handle_save_config(_save_req(cfg_path, config))
        on_disk = json.loads(open(cfg_path).read())
        stored_path = on_disk["decoding"][0]["db_path"]
        assert not os.path.isabs(stored_path)
        assert stored_path == "can_bus.dbc"

    def test_output_folder_stored_as_relative(self, tmp_path):
        cfg_path    = str(tmp_path / "config.mf4u")
        out_folder  = str(tmp_path / "exports")
        config = {
            "version": 1, "decoding": [],
            "channel_filter": None, "flatten": False,
            "export_format": "csv",
            "output_folder": out_folder,
            "mat_link_groups": False,
        }
        sidecar.handle_save_config(_save_req(cfg_path, config))
        on_disk = json.loads(open(cfg_path).read())
        assert not os.path.isabs(on_disk["output_folder"])
        assert on_disk["output_folder"] == "exports"

    def test_dbc_in_subdir(self, tmp_path):
        cfg_path = str(tmp_path / "config.mf4u")
        dbc_path = str(tmp_path / "dbs" / "can_bus.dbc")
        config = {
            "version": 1,
            "decoding": [{"group_index": 0, "group_name": "CAN1", "db_path": dbc_path}],
            "channel_filter": None, "flatten": False,
            "export_format": "csv", "output_folder": "", "mat_link_groups": False,
        }
        sidecar.handle_save_config(_save_req(cfg_path, config))
        on_disk = json.loads(open(cfg_path).read())
        assert on_disk["decoding"][0]["db_path"] == "dbs/can_bus.dbc"

    def test_config_in_subdir_dbc_in_parent(self, tmp_path):
        (tmp_path / "configs").mkdir()
        cfg_path = str(tmp_path / "configs" / "config.mf4u")
        dbc_path = str(tmp_path / "can_bus.dbc")
        config = {
            "version": 1,
            "decoding": [{"group_index": 0, "group_name": "CAN1", "db_path": dbc_path}],
            "channel_filter": None, "flatten": False,
            "export_format": "csv", "output_folder": "", "mat_link_groups": False,
        }
        sidecar.handle_save_config(_save_req(cfg_path, config))
        on_disk = json.loads(open(cfg_path).read())
        assert on_disk["decoding"][0]["db_path"] == "../can_bus.dbc"

    def test_empty_dbc_path_unchanged(self, tmp_path):
        cfg_path = str(tmp_path / "config.mf4u")
        config = {
            "version": 1,
            "decoding": [{"group_index": 0, "group_name": "CAN1", "db_path": ""}],
            "channel_filter": None, "flatten": False,
            "export_format": "csv", "output_folder": "", "mat_link_groups": False,
        }
        sidecar.handle_save_config(_save_req(cfg_path, config))
        on_disk = json.loads(open(cfg_path).read())
        assert on_disk["decoding"][0]["db_path"] == ""

    def test_does_not_mutate_original_config(self, tmp_path):
        cfg_path = str(tmp_path / "config.mf4u")
        dbc_path = str(tmp_path / "can_bus.dbc")
        config = {
            "version": 1,
            "decoding": [{"group_index": 0, "group_name": "CAN1", "db_path": dbc_path}],
            "channel_filter": None, "flatten": False,
            "export_format": "csv", "output_folder": "", "mat_link_groups": False,
        }
        original_dbc = config["decoding"][0]["db_path"]
        sidecar.handle_save_config(_save_req(cfg_path, config))
        # Original dict must be untouched.
        assert config["decoding"][0]["db_path"] == original_dbc

    def test_missing_path_returns_error(self, tmp_path):
        resp = sidecar.handle_save_config({"id": 1, "method": "save_config",
                                           "params": {"path": "", "config": {}}})
        assert resp.get("error") is not None


# --------------------------------------------------------------------------- #
# handle_load_config
# --------------------------------------------------------------------------- #

class TestLoadConfig:
    def _write_raw(self, path: str, data: dict) -> None:
        with open(path, "w") as fh:
            json.dump(data, fh, indent=2)

    def test_relative_dbc_resolved_to_absolute(self, tmp_path):
        cfg_path = str(tmp_path / "config.mf4u")
        # Store the DBC path as relative (as save_config would write it).
        self._write_raw(cfg_path, {
            "version": 1,
            "decoding": [{"group_index": 0, "group_name": "CAN1", "db_path": "can_bus.dbc"}],
            "channel_filter": None, "flatten": False,
            "export_format": "csv", "output_folder": "", "mat_link_groups": False,
        })
        resp = sidecar.handle_load_config(_load_req(cfg_path))
        assert resp.get("error") is None
        db_path = resp["result"]["config"]["decoding"][0]["db_path"]
        assert os.path.isabs(db_path)
        assert db_path == os.path.normpath(str(tmp_path / "can_bus.dbc"))

    def test_relative_output_folder_resolved(self, tmp_path):
        cfg_path = str(tmp_path / "config.mf4u")
        self._write_raw(cfg_path, {
            "version": 1, "decoding": [],
            "channel_filter": None, "flatten": False,
            "export_format": "csv",
            "output_folder": "exports",
            "mat_link_groups": False,
        })
        resp = sidecar.handle_load_config(_load_req(cfg_path))
        folder = resp["result"]["config"]["output_folder"]
        assert os.path.isabs(folder)
        assert folder == os.path.normpath(str(tmp_path / "exports"))

    def test_absolute_dbc_preserved(self, tmp_path):
        cfg_path = str(tmp_path / "config.mf4u")
        abs_dbc  = str(tmp_path / "can_bus.dbc")
        self._write_raw(cfg_path, {
            "version": 1,
            "decoding": [{"group_index": 0, "group_name": "CAN1", "db_path": abs_dbc}],
            "channel_filter": None, "flatten": False,
            "export_format": "csv", "output_folder": "", "mat_link_groups": False,
        })
        resp   = sidecar.handle_load_config(_load_req(cfg_path))
        result = resp["result"]["config"]["decoding"][0]["db_path"]
        assert result == os.path.normpath(abs_dbc)

    def test_parent_dir_relative_resolved(self, tmp_path):
        (tmp_path / "configs").mkdir()
        cfg_path = str(tmp_path / "configs" / "config.mf4u")
        self._write_raw(cfg_path, {
            "version": 1,
            "decoding": [{"group_index": 0, "group_name": "CAN1", "db_path": "../can_bus.dbc"}],
            "channel_filter": None, "flatten": False,
            "export_format": "csv", "output_folder": "", "mat_link_groups": False,
        })
        resp   = sidecar.handle_load_config(_load_req(cfg_path))
        result = resp["result"]["config"]["decoding"][0]["db_path"]
        assert result == os.path.normpath(str(tmp_path / "can_bus.dbc"))

    def test_save_load_roundtrip(self, tmp_path):
        """Saving then loading must restore all absolute paths exactly."""
        cfg_path   = str(tmp_path / "config.mf4u")
        dbc_path   = str(tmp_path / "dbs" / "can_bus.dbc")
        out_folder = str(tmp_path / "exports")
        config = {
            "version": 1,
            "decoding": [{"group_index": 0, "group_name": "CAN1", "db_path": dbc_path}],
            "channel_filter": ["EngineSpeed", "VehicleSpeed"],
            "flatten": True,
            "export_format": "csv",
            "output_folder": out_folder,
            "mat_link_groups": False,
        }
        sidecar.handle_save_config(_save_req(cfg_path, config))
        resp = sidecar.handle_load_config(_load_req(cfg_path))
        loaded = resp["result"]["config"]

        assert loaded["decoding"][0]["db_path"]  == os.path.normpath(dbc_path)
        assert loaded["output_folder"]           == os.path.normpath(out_folder)
        assert loaded["flatten"]                 == True
        assert loaded["export_format"]           == "csv"
        assert loaded["channel_filter"]          == ["EngineSpeed", "VehicleSpeed"]

    def test_missing_path_returns_error(self):
        resp = sidecar.handle_load_config({"id": 2, "method": "load_config",
                                           "params": {"path": ""}})
        assert resp.get("error") is not None

    def test_nonexistent_file_returns_error(self, tmp_path):
        resp = sidecar.handle_load_config(_load_req(str(tmp_path / "nope.mf4u")))
        assert resp.get("error") is not None
