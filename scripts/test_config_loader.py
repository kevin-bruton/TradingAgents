from tradingagents.config_loader import load_config, get_providers, get_models, validate_model


def test_load_config_providers_present():
    cfg = load_config()
    assert 'providers' in cfg and isinstance(cfg['providers'], dict)
    providers = get_providers()
    # Expect at least one provider
    assert any(p['key'] == 'openai' for p in providers)


def test_models_structure():
    models = get_models('openai', 'quick')
    assert isinstance(models, list)
    assert all('id' in m for m in models)


def test_validate_model():
    quick_models = get_models('openai', 'quick')
    if quick_models:
        assert validate_model('openai', quick_models[0]['id'])
