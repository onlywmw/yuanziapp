"""Regression tests for guess_category token-based matching."""

from __future__ import annotations

from register_mcp_atoms import guess_category


def _funcs(*names: str):
    return [{"name": n} for n in names]


def test_substring_ai_false_positive():
    # "details" / "available" contain "ai" but must not match AI & Model
    assert (
        guess_category("mcp.example", _funcs("get_details", "list_available"))
        == "Integration"
    )


def test_substring_repo_false_positive():
    # "report" contains "repo" but must not match Version Control
    assert guess_category("mcp.reporting", _funcs("generate_report")) == "Integration"


def test_substring_log_false_positive():
    # "login" / "catalog" contain "log" but must not match Observability
    assert guess_category("mcp.shop", _funcs("login_user")) == "Integration"


def test_substring_email_not_ai():
    # "email" contains "ai"; Communication keyword should win by token match
    assert guess_category("mcp.mailer", _funcs("send_email")) == "Communication"


def test_real_ai_atom():
    assert guess_category("mcp.sagemaker-ai", _funcs("train_model")) == "AI & Model"


def test_database_by_token():
    assert guess_category("mcp.documentdb", _funcs("query_collection")) == "Database"


def test_observability_prometheus():
    assert guess_category("mcp.prometheus", _funcs("query_metrics")) == "Observability"


def test_security_category():
    assert guess_category("mcp.security-agent", _funcs("start_scan")) == "Security"


def test_cloud_before_ai_for_pricing():
    # function mentions bedrock, but the atom itself is AWS pricing
    assert (
        guess_category("mcp.aws-pricing", _funcs("get_bedrock_patterns"))
        == "Cloud & Storage"
    )


def test_fallback_integration():
    assert guess_category("mcp.widget", _funcs("render_panel")) == "Integration"


def test_name_tokens_take_priority_over_function_names():
    # atom_id 是 aws-iac，即使函数名含 documentation 也应按 IaC/Cloud 分类
    assert (
        guess_category("mcp.aws-iac", _funcs("search_cdk_documentation"))
        == "Cloud & Storage"
    )


def test_aws_api_is_cloud_not_web():
    assert guess_category("mcp.aws-api", _funcs("call_aws_api")) == "Cloud & Storage"


def test_cloudtrail_is_observability():
    assert guess_category("mcp.cloudtrail", _funcs("lookup_events")) == "Observability"
