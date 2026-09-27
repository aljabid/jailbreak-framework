import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from utils.config import Config, _coerce_value, _load_dotenv, _load_yaml


class TestConfigDefaults:
    def test_defaults_exist(self):

        assert len(Config.DEFAULTS) > 0
        assert "model.provider" in Config.DEFAULTS
        assert "attack.strategies" in Config.DEFAULTS

    def test_config_init_no_file(self):

        cfg = Config(config_file="/nonexistent/path.yaml")

        assert cfg.model_provider is not None

    def test_model_provider_default(self):

        cfg = Config(config_file="/nonexistent/path.yaml")
        assert cfg.model_provider == "openai"

    def test_strategies_default(self):

        cfg = Config(config_file="/nonexistent/path.yaml")
        strategies = cfg.strategies
        assert isinstance(strategies, list)
        assert len(strategies) > 0

    def test_eval_mode_default(self):

        cfg = Config(config_file="/nonexistent/path.yaml")
        assert cfg.eval_mode == "keyword"


class TestConfigTypeCoercion:
    def test_int_coercion(self):

        cfg = Config(config_file="/nonexistent/path.yaml")
        assert isinstance(cfg.max_tokens, int)
        assert cfg.max_tokens > 0

    def test_float_coercion(self):

        cfg = Config(config_file="/nonexistent/path.yaml")
        assert isinstance(cfg.temperature, float)
        assert 0.0 <= cfg.temperature <= 2.0

    def test_list_coercion_from_csv(self):

        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
attack:
  strategies: "roleplay, encoding_attack"
""")
            f.flush()
            try:
                cfg = Config(config_file=f.name)
                strategies = cfg.strategies
                assert isinstance(strategies, list)
                assert "roleplay" in strategies
                assert "encoding_attack" in strategies
            finally:
                os.unlink(f.name)


class TestConfigEnvironmentOverride:
    def test_env_override_with_jbf_prefix(self):

        os.environ["JBF_MODEL_NAME"] = "test-model-override"
        try:
            cfg = Config(config_file="/nonexistent/path.yaml")
            assert cfg.model_name == "test-model-override"
        finally:
            del os.environ["JBF_MODEL_NAME"]

    def test_openai_api_key_from_env(self):

        os.environ["OPENAI_API_KEY"] = "sk-test-key-12345"
        try:
            cfg = Config(config_file="/nonexistent/path.yaml")
            assert cfg.openai_api_key == "sk-test-key-12345"
        finally:
            del os.environ["OPENAI_API_KEY"]

    def test_eval_mode_override(self):

        os.environ["JBF_EVALUATION_MODE"] = "ai_judge"
        try:
            cfg = Config(config_file="/nonexistent/path.yaml")
            assert cfg.eval_mode == "ai_judge"
        finally:
            del os.environ["JBF_EVALUATION_MODE"]


class TestConfigYAMLLoading:
    def test_load_valid_yaml(self):

        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
model:
  provider: "local"
  name: "test-local"
  temperature: 0.8
attack:
  strategies:
    - roleplay
    - encoding_attack
evaluation:
  mode: "hybrid"
""")
            f.flush()
            try:
                cfg = Config(config_file=f.name)
                assert cfg.model_provider == "local"
                assert cfg.model_name == "test-local"
                assert cfg.temperature == 0.8
                assert cfg.eval_mode == "hybrid"
            finally:
                os.unlink(f.name)

    def test_nested_dict_flattening(self):

        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
model:
  provider: "openai"
  timeout: 60
""")
            f.flush()
            try:
                cfg = Config(config_file=f.name)
                assert cfg.timeout == 60
            finally:
                os.unlink(f.name)


class TestConfigGetMethod:
    def test_get_with_default(self):

        cfg = Config(config_file="/nonexistent/path.yaml")
        val = cfg.get("nonexistent.key", "fallback_value")
        assert val == "fallback_value"

    def test_get_existing_key(self):

        cfg = Config(config_file="/nonexistent/path.yaml")
        val = cfg.get("model.provider")
        assert val is not None

    def test_get_respects_env_override(self):

        os.environ["JBF_MODEL_TIMEOUT"] = "120"
        try:
            cfg = Config(config_file="/nonexistent/path.yaml")
            val = cfg.get("model.timeout")
            assert val == 120
        finally:
            del os.environ["JBF_MODEL_TIMEOUT"]


class TestConfigSummarize:
    def test_summarize_no_secrets(self):

        os.environ["OPENAI_API_KEY"] = "sk-secret-12345"
        try:
            cfg = Config(config_file="/nonexistent/path.yaml")
            summary = cfg.summarize()
            assert "sk-secret" not in str(summary)
            assert "model" in summary
            assert "strategies" in summary
        finally:
            del os.environ["OPENAI_API_KEY"]

    def test_summarize_has_key_fields(self):

        cfg = Config(config_file="/nonexistent/path.yaml")
        summary = cfg.summarize()
        assert "model" in summary
        assert "strategies" in summary
        assert "eval_mode" in summary


class TestConfigValidation:
    def test_invalid_model_provider_coerced(self):

        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
model:
  provider: "invalid_provider"
""")
            f.flush()
            try:
                cfg = Config(config_file=f.name)
                assert cfg.model_provider == "openai"
                assert cfg.validation_issues
            finally:
                os.unlink(f.name)

    def test_strict_config_rejects_invalid_provider(self, tmp_path):
        path = tmp_path / "invalid.yaml"
        path.write_text("model:\n  provider: invalid_provider\n")
        with pytest.raises(ValueError, match="model.provider"):
            Config(config_file=str(path), strict=True)

    def test_invalid_threshold_order_uses_defaults(self, tmp_path):
        path = tmp_path / "invalid.yaml"
        path.write_text(
            "scoring:\n  medium_threshold: 0.8\n  high_threshold: 0.5\n  critical_threshold: 0.7\n"
        )
        cfg = Config(config_file=str(path))
        assert cfg.medium_threshold == 0.40
        assert cfg.high_threshold == 0.65
        assert cfg.critical_threshold == 0.85

    def test_temperature_range(self):

        cfg = Config(config_file="/nonexistent/path.yaml")
        temp = cfg.temperature

        assert 0.0 <= temp <= 2.0

    def test_max_tokens_positive(self):

        cfg = Config(config_file="/nonexistent/path.yaml")
        assert cfg.max_tokens > 0

    def test_timeout_positive(self):

        cfg = Config(config_file="/nonexistent/path.yaml")
        assert cfg.timeout > 0


class TestLoadYamlWithoutPyyaml:
    def test_load_yaml_missing_pyyaml_falls_back_to_defaults(self, tmp_path, monkeypatch):
        path = tmp_path / "config.yaml"
        path.write_text("model:\n  provider: local\n")
        monkeypatch.setitem(sys.modules, "yaml", None)

        assert _load_yaml(path) == {}

    def test_load_dotenv_missing_python_dotenv_is_silent(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "dotenv", None)

        _load_dotenv(".env")


class TestCoerceValueDirect:
    def test_untemplated_bool_like_strings(self):
        assert _coerce_value("true") is True
        assert _coerce_value("YES") is True
        assert _coerce_value("off") is False
        assert _coerce_value("0") is False

    def test_untemplated_numeric_strings(self):
        assert _coerce_value("42") == 42
        assert _coerce_value("3.14") == 3.14

    def test_untemplated_passthrough_string(self):
        assert _coerce_value("plain-text") == "plain-text"

    def test_untemplated_non_string_passthrough(self):
        assert _coerce_value(7) == 7

    def test_bool_template_with_non_string_value(self):
        assert _coerce_value(1, template=True) is True
        assert _coerce_value(0, template=False) is False

    def test_list_template_with_non_string_value(self):
        assert _coerce_value(["a", "b"], template=["x"]) == ["a", "b"]

    def test_list_template_with_string_value(self):
        assert _coerce_value("a, b, c", template=["x"]) == ["a", "b", "c"]


class TestConfigRootValidation:
    def test_non_mapping_yaml_root_raises(self, tmp_path):
        path = tmp_path / "list.yaml"
        path.write_text("- one\n- two\n")
        with pytest.raises(ValueError, match="must be a mapping"):
            Config(config_file=str(path))


class TestConfigDerivedProperties:
    def test_allowed_hosts_from_csv_string(self, tmp_path):
        path = tmp_path / "config.yaml"
        path.write_text("model:\n  allowed_hosts: \"localhost, example.internal\"\n")
        cfg = Config(config_file=str(path))
        assert cfg.allowed_hosts == ["localhost", "example.internal"]

    def test_strategies_from_plain_string(self, tmp_path):
        path = tmp_path / "config.yaml"
        path.write_text("attack:\n  strategies: \"roleplay,encoding_attack\"\n")
        cfg = Config(config_file=str(path))
        assert cfg.strategies == ["roleplay", "encoding_attack"]

    def test_strategies_from_unsupported_type_falls_back_to_empty_list(self, tmp_path):
        path = tmp_path / "config.yaml"
        path.write_text("attack:\n  strategies: 42\n")
        cfg = Config(config_file=str(path))
        assert cfg.strategies == []

    def test_file_logging_default(self):
        cfg = Config(config_file="/nonexistent/path.yaml")
        assert cfg.file_logging is True

    def test_anthropic_api_key_from_env(self):
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-12345"
        try:
            cfg = Config(config_file="/nonexistent/path.yaml")
            assert cfg.anthropic_api_key == "sk-ant-test-12345"
        finally:
            del os.environ["ANTHROPIC_API_KEY"]
