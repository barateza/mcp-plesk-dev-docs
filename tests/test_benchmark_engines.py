from mcp_plesk_dev_docs.benchmark_engines import (
    bucket_query,
    rerank_with_structure,
    route_query,
)
from mcp_plesk_dev_docs.benchmark_suites import BENCHMARK_SUITES


def test_bucket_query_classifies_structural_and_lookup_queries():
    assert bucket_query("add a custom button to Plesk panel") == "structural"
    assert bucket_query("list all domains via Plesk REST API") == "lookup"


def test_rerank_with_structure_prefers_title_and_breadcrumb_matches():
    results = [
        {
            "title": "Working with Buttons",
            "breadcrumb": "Extensions > UI Components",
            "text": "General extension UI guidance.",
            "filename": "ui-guide.htm",
            "category": "guide",
        },
        {
            "title": "Custom Button Setup",
            "breadcrumb": "Extensions > UI Components > Buttons",
            "text": "This section explains how to add a custom button.",
            "filename": "button-setup.htm",
            "category": "guide",
        },
    ]

    ranked = rerank_with_structure("add a custom button", results)

    assert ranked[0]["title"] == "Custom Button Setup"
    assert ranked[0]["_pilot_score"] >= ranked[1]["_pilot_score"]


def test_benchmark_suite_registry_includes_requested_suites():
    assert set(BENCHMARK_SUITES) >= {"control", "structural", "long-doc", "multi-hop"}
    assert len(BENCHMARK_SUITES["structural"]) >= 3
    assert len(BENCHMARK_SUITES["long-doc"]) >= 3
    assert len(BENCHMARK_SUITES["multi-hop"]) >= 20


def test_route_query_baseline_only_keeps_baseline_engine():
    decision = route_query(
        "how do I add a custom button and where is that button API defined",
        "multi-hop",
        routing_policy="baseline-only",
    )
    assert decision.engine == "baseline"
    assert decision.pilot_config is None


def test_route_query_adaptive_routes_multi_hop_to_pageindex():
    decision = route_query(
        "how do I add a custom button and where is that button API defined",
        "multi-hop",
        routing_policy="adaptive",
    )
    assert decision.engine == "pageindex-pilot"
    assert decision.pilot_config is not None


def test_route_query_adaptive_routes_structural_phrase_to_pageindex():
    decision = route_query(
        "how to define default config settings for a Plesk extension",
        "structural",
        routing_policy="adaptive",
    )
    assert decision.engine == "pageindex-pilot"


def test_route_query_adaptive_keeps_lookup_on_baseline():
    decision = route_query(
        "list all domains via Plesk REST API",
        "lookup",
        routing_policy="adaptive",
    )
    assert decision.engine == "baseline"


def test_route_query_aggressive_always_uses_pageindex():
    decision = route_query(
        "list all domains via Plesk REST API",
        "lookup",
        routing_policy="aggressive",
    )
    assert decision.engine == "pageindex-pilot"
