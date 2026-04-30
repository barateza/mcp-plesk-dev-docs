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
    import plesk_unified.settings as ps

    for k in list(os.environ):
        if k.startswith("PLESK_"):
            del os.environ[k]
    os.environ.update(env)
    os.environ["PLESK_ENV_FILE"] = ""  # Suppress .env loading

    importlib.reload(ps)
    importlib.reload(mc)
    # Re-import after reload so we get the fresh module object
    import plesk_unified.model_config as mc2

    return mc2


# ---------------------------------------------------------------------------
# Profile selection
# ---------------------------------------------------------------------------


class TestProfileSelection:
    def test_default_profile_is_pro(self):
        mc = reload_config({})
        p = mc.get_active_profile()
        assert p.name == "pro"
        assert p.embed_model == "snowflake/snowflake-arctic-embed-m-v1.5"
        assert p.embed_dim == 768

    def test_local_profile(self):
        mc = reload_config({"PLESK_MODEL_PROFILE": "local"})
        p = mc.get_active_profile()
        assert p.name == "local"
        assert p.embed_model == "snowflake/snowflake-arctic-embed-s"
        assert p.embed_dim == 384
        assert p.reranker_model == "cross-encoder/ms-marco-MiniLM-L-6-v2"
        assert p.reranker_enabled is True

    def test_pro_profile(self):
        mc = reload_config({"PLESK_MODEL_PROFILE": "pro"})
        p = mc.get_active_profile()
        assert p.name == "pro"
        assert p.embed_dim == 768

    def test_sandbox_profile(self):
        mc = reload_config({"PLESK_MODEL_PROFILE": "sandbox"})
        p = mc.get_active_profile()
        assert p.name == "sandbox"
        assert p.embed_model == "Alibaba-NLP/gte-large-en-v1.5"
        assert p.reranker_model == "BAAI/bge-reranker-base"
        assert p.use_turboquant is True

    def test_unknown_profile_falls_back_to_pro(self, caplog):
        mc = reload_config({"PLESK_MODEL_PROFILE": "nonexistent"})
        import logging

        with caplog.at_level(logging.WARNING, logger="plesk_unified"):
            p = mc.get_active_profile()
        assert p.name == "pro"
        assert "Unknown PLESK_MODEL_PROFILE" in caplog.text

    def test_profile_name_is_case_insensitive(self):
        mc = reload_config({"PLESK_MODEL_PROFILE": "LOCAL"})
        p = mc.get_active_profile()
        assert p.name == "local"


# ---------------------------------------------------------------------------
# Per-component overrides
# ---------------------------------------------------------------------------


class TestComponentOverrides:
    def test_embed_model_override(self):
        mc = reload_config(
            {
                "PLESK_MODEL_PROFILE": "local",
                "PLESK_EMBED_MODEL": "snowflake/snowflake-arctic-embed-m-v1.5",
                "PLESK_EMBED_DIM": "768",
            }
        )
        p = mc.get_active_profile()
        assert p.embed_model == "snowflake/snowflake-arctic-embed-m-v1.5"
        assert p.embed_dim == 768

    def test_embed_dim_override_without_model_uses_profile_dim(self, caplog):
        """Changing model without setting dim should warn and use profile default."""
        mc = reload_config(
            {
                "PLESK_MODEL_PROFILE": "local",
                "PLESK_EMBED_MODEL": "some/custom-model",
                # No PLESK_EMBED_DIM
            }
        )
        import logging

        with caplog.at_level(logging.WARNING, logger="plesk_unified"):
            p = mc.get_active_profile()
        assert p.embed_dim == 384  # local profile default
        assert "PLESK_EMBED_DIM" in caplog.text

    def test_reranker_model_override(self):
        mc = reload_config(
            {
                "PLESK_MODEL_PROFILE": "pro",
                "PLESK_RERANKER_MODEL": "cross-encoder/ms-marco-MiniLM-L-6-v2",
            }
        )
        p = mc.get_active_profile()
        assert p.reranker_model == "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def test_disable_reranker_via_env_false(self):
        mc = reload_config(
            {
                "PLESK_MODEL_PROFILE": "pro",
                "PLESK_RERANKER_ENABLED": "false",
            }
        )
        p = mc.get_active_profile()
        assert p.reranker_enabled is False

    def test_disable_reranker_via_env_zero(self):
        mc = reload_config(
            {
                "PLESK_MODEL_PROFILE": "pro",
                "PLESK_RERANKER_ENABLED": "0",
            }
        )
        p = mc.get_active_profile()
        assert p.reranker_enabled is False

    def test_enable_reranker_via_env_true(self):
        mc = reload_config(
            {
                "PLESK_MODEL_PROFILE": "pro",
                "PLESK_RERANKER_ENABLED": "true",
            }
        )
        p = mc.get_active_profile()
        assert p.reranker_enabled is True

    def test_reranker_disabled_when_model_is_empty(self):
        mc = reload_config(
            {
                "PLESK_MODEL_PROFILE": "pro",
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
        assert set(profiles.keys()) == {"local", "pro", "sandbox"}

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
        assert profiles["local"]["approx_ram_mb"] < profiles["pro"]["approx_ram_mb"]
        assert profiles["pro"]["approx_ram_mb"] < profiles["sandbox"]["approx_ram_mb"]
