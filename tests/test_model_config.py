"""
Tests for plesk_unified.model_config

All tests are pure-unit (no model downloads, no LanceDB, no torch).
"""

import importlib
import os

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def reload_config(env: dict):
    """
    Reload model_config with a clean environment.
    Returns the module so tests can call get_active_profile() on it.
    """
    import plesk_unified.model_config as mc  # noqa: F401

    for k in list(os.environ):
        if k.startswith("PLESK_"):
            del os.environ[k]
    os.environ.update(env)
    importlib.reload(mc)
    # Re-import after reload so we get the fresh module object
    import plesk_unified.model_config as mc2

    return mc2


# ---------------------------------------------------------------------------
# Profile selection
# ---------------------------------------------------------------------------


class TestProfileSelection:
    def test_default_profile_is_medium(self):
        mc = reload_config({})
        p = mc.get_active_profile()
        assert p.name == "medium"
        assert p.embed_model == "BAAI/bge-base-en-v1.5"
        assert p.embed_dim == 768

    def test_light_profile(self):
        mc = reload_config({"PLESK_MODEL_PROFILE": "light"})
        p = mc.get_active_profile()
        assert p.name == "light"
        assert p.embed_model == "BAAI/bge-small-en-v1.5"
        assert p.embed_dim == 384
        assert p.reranker_model == "cross-encoder/ms-marco-MiniLM-L-6-v2"
        assert p.reranker_enabled is True

    def test_medium_profile(self):
        mc = reload_config({"PLESK_MODEL_PROFILE": "medium"})
        p = mc.get_active_profile()
        assert p.name == "medium"
        assert p.embed_dim == 768

    def test_full_profile(self):
        mc = reload_config({"PLESK_MODEL_PROFILE": "full"})
        p = mc.get_active_profile()
        assert p.name == "full"
        assert p.embed_model == "BAAI/bge-m3"
        assert p.reranker_model == "BAAI/bge-reranker-base"

    def test_unknown_profile_falls_back_to_medium(self, caplog):
        mc = reload_config({"PLESK_MODEL_PROFILE": "nonexistent"})
        import logging

        with caplog.at_level(logging.WARNING, logger="plesk_unified"):
            p = mc.get_active_profile()
        assert p.name == "medium"
        assert "Unknown PLESK_MODEL_PROFILE" in caplog.text

    def test_profile_name_is_case_insensitive(self):
        mc = reload_config({"PLESK_MODEL_PROFILE": "LIGHT"})
        p = mc.get_active_profile()
        assert p.name == "light"


# ---------------------------------------------------------------------------
# Per-component overrides
# ---------------------------------------------------------------------------


class TestComponentOverrides:
    def test_embed_model_override(self):
        mc = reload_config(
            {
                "PLESK_MODEL_PROFILE": "light",
                "PLESK_EMBED_MODEL": "BAAI/bge-base-en-v1.5",
                "PLESK_EMBED_DIM": "768",
            }
        )
        p = mc.get_active_profile()
        assert p.embed_model == "BAAI/bge-base-en-v1.5"
        assert p.embed_dim == 768

    def test_embed_dim_override_without_model_uses_profile_dim(self, caplog):
        """Changing model without setting dim should warn and use profile default."""
        mc = reload_config(
            {
                "PLESK_MODEL_PROFILE": "light",
                "PLESK_EMBED_MODEL": "some/custom-model",
                # No PLESK_EMBED_DIM
            }
        )
        import logging

        with caplog.at_level(logging.WARNING, logger="plesk_unified"):
            p = mc.get_active_profile()
        assert p.embed_dim == 384  # light profile default
        assert "PLESK_EMBED_DIM" in caplog.text

    def test_reranker_model_override(self):
        mc = reload_config(
            {
                "PLESK_MODEL_PROFILE": "full",
                "PLESK_RERANKER_MODEL": "cross-encoder/ms-marco-MiniLM-L-6-v2",
            }
        )
        p = mc.get_active_profile()
        assert p.reranker_model == "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def test_disable_reranker_via_env_false(self):
        mc = reload_config(
            {
                "PLESK_MODEL_PROFILE": "full",
                "PLESK_RERANKER_ENABLED": "false",
            }
        )
        p = mc.get_active_profile()
        assert p.reranker_enabled is False

    def test_disable_reranker_via_env_zero(self):
        mc = reload_config(
            {
                "PLESK_MODEL_PROFILE": "full",
                "PLESK_RERANKER_ENABLED": "0",
            }
        )
        p = mc.get_active_profile()
        assert p.reranker_enabled is False

    def test_enable_reranker_via_env_true(self):
        mc = reload_config(
            {
                "PLESK_MODEL_PROFILE": "full",
                "PLESK_RERANKER_ENABLED": "true",
            }
        )
        p = mc.get_active_profile()
        assert p.reranker_enabled is True

    def test_reranker_disabled_when_model_is_empty(self):
        mc = reload_config(
            {
                "PLESK_MODEL_PROFILE": "full",
                "PLESK_RERANKER_MODEL": "",
            }
        )
        p = mc.get_active_profile()
        assert p.reranker_enabled is False
        assert p.reranker_model is None


# ---------------------------------------------------------------------------
# list_profiles
# ---------------------------------------------------------------------------


class TestListProfiles:
    def test_list_profiles_returns_all_profiles(self):
        mc = reload_config({})
        profiles = mc.list_profiles()
        assert set(profiles.keys()) == {"light", "medium", "full", "full-tq"}

    def test_list_profiles_has_required_keys(self):
        mc = reload_config({})
        for _name, info in mc.list_profiles().items():
            assert "embed_model" in info
            assert "embed_dim" in info
            assert "reranker_model" in info
            assert "approx_ram_mb" in info
            assert "description" in info

    def test_ram_estimates_are_ordered(self):
        mc = reload_config({})
        profiles = mc.list_profiles()
        assert profiles["light"]["approx_ram_mb"] < profiles["medium"]["approx_ram_mb"]
        assert profiles["medium"]["approx_ram_mb"] < profiles["full"]["approx_ram_mb"]
