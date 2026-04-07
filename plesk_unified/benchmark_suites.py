from __future__ import annotations

BUILTIN_QUERIES: list[dict] = [
    # php-stubs
    {
        "query": "how to define default config settings for a Plesk extension",
        "relevant": ["ConfigDefaults", "getDefaults"],
        "category": "php-stubs",
    },
    {
        "query": "retrieve extension configuration values",
        "relevant": ["pm_Config", "getDefaults"],
        "category": "php-stubs",
    },
    {
        "query": "hook interface for Plesk modules",
        "relevant": ["pm_Hook_Interface", "Hook"],
        "category": "php-stubs",
    },
    # cli
    {
        "query": "restart Plesk service from command line",
        "relevant": ["plesk repair", "restart"],
        "category": "cli",
    },
    {
        "query": "create a new subscription via CLI",
        "relevant": ["subscription", "add"],
        "category": "cli",
    },
    # api
    {
        "query": "list all domains via Plesk REST API",
        "relevant": ["List of Domains", "admin-domain-list", "domain-list"],
        "category": "api",
    },
    {
        "query": "authenticate with Plesk API using secret key",
        "relevant": ["X-API-Key", "secret_key", "Authorization"],
        "category": "api",
    },
    # guide
    {
        "query": "add a custom button to Plesk panel",
        "relevant": ["button", "custom_buttons", "addButton"],
        "category": "guide",
    },
    {
        "query": "package a Plesk extension for distribution",
        "relevant": ["plesk ext", "package", ".zip"],
        "category": "guide",
    },
    # js-sdk
    {
        "query": "register a new page in Plesk JS SDK",
        "relevant": ["registerPage", "router"],
        "category": "js-sdk",
    },
    # cross-source
    {
        "query": "SSL certificate management",
        "relevant": ["certificate", "SSL", "TLS"],
        "category": None,
    },
    {
        "query": "backup and restore Plesk",
        "relevant": ["backup", "restore"],
        "category": None,
    },
]

STRUCTURAL_QUERIES: list[dict] = [
    {
        "query": "where is the custom button documentation for Plesk extensions",
        "relevant": ["button", "custom_buttons", "addButton"],
        "category": "guide",
        "bucket": "structural",
    },
    {
        "query": "which section explains packaging a Plesk extension for distribution",
        "relevant": ["plesk ext", "package", ".zip"],
        "category": "guide",
        "bucket": "structural",
    },
    {
        "query": "where is the API reference for listing domains",
        "relevant": ["List of Domains", "admin-domain-list", "domain-list"],
        "category": "api",
        "bucket": "structural",
    },
    {
        "query": "which page covers the extension config defaults hook",
        "relevant": ["ConfigDefaults", "getDefaults"],
        "category": "php-stubs",
        "bucket": "structural",
    },
]

LONG_DOC_QUERIES: list[dict] = [
    {
        "query": "what does the guide say about custom buttons in the extensions UI",
        "relevant": ["button", "custom_buttons", "addButton"],
        "category": "guide",
        "bucket": "long-doc",
    },
    {
        "query": "how do the API docs describe authentication with a secret key",
        "relevant": ["X-API-Key", "secret_key", "Authorization"],
        "category": "api",
        "bucket": "long-doc",
    },
    {
        "query": "where does the CLI reference describe restarting services",
        "relevant": ["plesk repair", "restart"],
        "category": "cli",
        "bucket": "long-doc",
    },
]

MULTI_HOP_QUERIES: list[dict] = [
    {
        "query": "how do I add a custom button and where is that button API defined",
        "relevant": ["button", "custom_buttons", "addButton"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "medium",
        "source": "expanded-manual",
    },
    {
        "query": (
            "how do I package an extension and where is the SDK page "
            "registration reference"
        ),
        "relevant": ["plesk ext", "package", "registerPage", "router"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "medium",
        "source": "expanded-manual",
    },
    {
        "query": (
            "what is the authentication path and where do the domain list "
            "endpoints live"
        ),
        "relevant": ["X-API-Key", "secret_key", "Authorization", "domain-list"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "medium",
        "source": "expanded-manual",
    },
    {
        "query": (
            "which hook interface is used for extension defaults and where are "
            "defaults retrieved"
        ),
        "relevant": ["pm_Hook_Interface", "ConfigDefaults", "getDefaults", "pm_Config"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "medium",
        "source": "expanded-manual",
    },
    {
        "query": (
            "where can I restart services from CLI and where is backup restore "
            "documented"
        ),
        "relevant": ["plesk repair", "restart", "backup", "restore"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "easy",
        "source": "expanded-manual",
    },
    {
        "query": "how do extension defaults connect to config retrieval APIs",
        "relevant": ["ConfigDefaults", "getDefaults", "pm_Config"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "easy",
        "source": "expanded-manual",
    },
    {
        "query": (
            "where are domain listing endpoints and secret key headers "
            "documented together"
        ),
        "relevant": ["domain-list", "List of Domains", "X-API-Key", "Authorization"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "medium",
        "source": "expanded-manual",
    },
    {
        "query": (
            "how do I create a subscription and then configure SSL "
            "certificate management"
        ),
        "relevant": ["subscription", "add", "certificate", "SSL", "TLS"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "medium",
        "source": "expanded-manual",
    },
    {
        "query": "where is custom button guidance and where is SDK router registration",
        "relevant": ["button", "custom_buttons", "registerPage", "router"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "medium",
        "source": "expanded-manual",
    },
    {
        "query": (
            "how do extension packaging steps map to extension CLI packaging commands"
        ),
        "relevant": ["plesk ext", "package", ".zip"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "medium",
        "source": "expanded-manual",
    },
    {
        "query": "where do backup restore operations and API authentication intersect",
        "relevant": ["backup", "restore", "X-API-Key", "secret_key", "Authorization"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "hard",
        "source": "expanded-manual",
    },
    {
        "query": (
            "which documents connect extension setting defaults with hook lifecycle"
        ),
        "relevant": ["ConfigDefaults", "pm_Hook_Interface", "Hook"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "hard",
        "source": "expanded-manual",
    },
    {
        "query": (
            "how does SDK page registration relate to custom panel button creation"
        ),
        "relevant": ["registerPage", "router", "button", "addButton"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "medium",
        "source": "expanded-manual",
    },
    {
        "query": "where can I find subscription creation in CLI and domain list in API",
        "relevant": ["subscription", "add", "domain-list", "List of Domains"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "medium",
        "source": "expanded-manual",
    },
    {
        "query": (
            "how do tls certificate operations relate to backup and restore guidance"
        ),
        "relevant": ["certificate", "SSL", "TLS", "backup", "restore"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "medium",
        "source": "expanded-manual",
    },
    {
        "query": (
            "which references combine API secret key auth and extension hook interfaces"
        ),
        "relevant": ["X-API-Key", "Authorization", "pm_Hook_Interface", "Hook"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "hard",
        "source": "expanded-manual",
    },
    {
        "query": "how do I package extension artifacts and then expose a new SDK page",
        "relevant": ["package", ".zip", "registerPage", "router"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "medium",
        "source": "expanded-manual",
    },
    {
        "query": (
            "where is service restart in cli and where is domain management in api"
        ),
        "relevant": ["plesk repair", "restart", "domain-list", "List of Domains"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "easy",
        "source": "expanded-manual",
    },
    {
        "query": (
            "which section explains defaults hooks and where are custom buttons "
            "documented"
        ),
        "relevant": ["ConfigDefaults", "getDefaults", "button", "custom_buttons"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "medium",
        "source": "expanded-manual",
    },
    {
        "query": (
            "where can I find api secret key authentication and ssl lifecycle "
            "references"
        ),
        "relevant": ["X-API-Key", "secret_key", "Authorization", "certificate", "SSL"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "hard",
        "source": "expanded-manual",
    },
    {
        "query": (
            "how does backup restore guidance align with subscription lifecycle "
            "commands"
        ),
        "relevant": ["backup", "restore", "subscription", "add"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "medium",
        "source": "expanded-manual",
    },
    {
        "query": (
            "which docs connect sdk router registration and extension package "
            "distribution"
        ),
        "relevant": ["registerPage", "router", "package", ".zip"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "medium",
        "source": "expanded-manual",
    },
    {
        "query": (
            "where is extension config retrieval and where are hook contracts defined"
        ),
        "relevant": ["pm_Config", "getDefaults", "pm_Hook_Interface", "Hook"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "medium",
        "source": "expanded-manual",
    },
    {
        "query": (
            "how do custom panel button docs and api domain docs complement each other"
        ),
        "relevant": ["button", "custom_buttons", "domain-list", "List of Domains"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "hard",
        "source": "expanded-manual",
    },
    {
        "query": (
            "where should I look for api auth details and cli restart recovery steps"
        ),
        "relevant": ["X-API-Key", "Authorization", "plesk repair", "restart"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "medium",
        "source": "expanded-manual",
    },
    {
        "query": (
            "which combined references cover extension packaging, page "
            "registration, and buttons"
        ),
        "relevant": ["package", ".zip", "registerPage", "router", "button"],
        "category": None,
        "bucket": "multi-hop",
        "difficulty": "hard",
        "source": "expanded-manual",
    },
]

BENCHMARK_SUITES: dict[str, list[dict]] = {
    "control": BUILTIN_QUERIES,
    "structural": STRUCTURAL_QUERIES,
    "long-doc": LONG_DOC_QUERIES,
    "multi-hop": MULTI_HOP_QUERIES,
}
