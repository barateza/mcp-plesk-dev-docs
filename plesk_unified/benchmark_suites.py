from __future__ import annotations

BUILTIN_QUERIES: list[dict] = [
    # --- EXISTING 12 (ground_truth + reference_context added) ---
    {
        "query": "how to define default config settings for a Plesk extension",
        "relevant": ["ConfigDefaults", "getDefaults"],
        "bucket": "php-stubs",
        "ground_truth": (
            "Default configuration values for a Plesk extension are defined by "
            "implementing the `getDefaults()` method in the class extending "
            "`pm_Config`. This method returns an associative array of key-value "
            "pairs representing the default settings."
        ),
        "reference_context": (
            "The `pm_Config::getDefaults()` method should return an associative "
            "array of default values. Your extension config class extends "
            "`pm_Config` and overrides `getDefaults()` to supply initial values "
            "used when no saved config exists."
        ),
    },
    {
        "query": "retrieve extension configuration values",
        "relevant": ["pmConfig", "getDefaults"],
        "bucket": "php-stubs",
        "ground_truth": (
            "Extension configuration values are retrieved using "
            "`pm_Config::get($key)`, which returns the stored value for the "
            "given key, falling back to the default defined in `getDefaults()` "
            "if no value has been saved."
        ),
        "reference_context": (
            "`pm_Config::get(string $key)` retrieves the value associated with "
            "the configuration key. If the key has not been set, it falls back "
            "to the default returned by `getDefaults()`."
        ),
    },
    {
        "query": "hook interface for Plesk modules",
        "relevant": ["pmHookInterface", "Hook"],
        "bucket": "php-stubs",
        "ground_truth": (
            "Plesk modules implement hooks by extending or implementing "
            "`pm_Hook_Interface`. Each hook class must implement the required methods "
            "defined by the interface, which are called by Plesk at specific "
            "lifecycle events."
        ),
        "reference_context": (
            "`pm_Hook_Interface` defines the contract for Plesk hook implementations. "
            "Module hook classes implement this interface and are registered via the "
            "extension descriptor to be invoked at defined lifecycle points."
        ),
    },
    {
        "query": "restart Plesk service from command line",
        "relevant": ["plesk repair", "restart"],
        "bucket": "cli",
        "ground_truth": (
            "The Plesk service can be restarted from the command line using "
            "`plesk repair all` or the system service manager (e.g., `systemctl "
            "restart psa`). The `plesk repair` command performs diagnostics and "
            "restarts key services."
        ),
        "reference_context": (
            "To restart Plesk components, run `plesk repair all` from the shell. "
            "This command checks and restarts all Plesk services. Alternatively, "
            "individual services can be controlled via the OS service manager."
        ),
    },
    {
        "query": "create a new subscription via CLI",
        "relevant": ["subscription", "add"],
        "bucket": "cli",
        "ground_truth": (
            "A new subscription is created via CLI using the command `plesk bin "
            "subscription --create <subscription-name> -owner <login> -ip <ip> "
            "-service-plan <plan-name>`. The owner and service plan must exist before "
            "the subscription is created."
        ),
        "reference_context": (
            "`plesk bin subscription --create` creates a new hosting subscription. "
            "Required parameters include `-owner` (customer login), `-ip` (IP "
            "address), and `-service-plan` (the name of an existing hosting plan)."
        ),
    },
    {
        "query": "list all domains via Plesk REST API",
        "relevant": ["GET domains", "apiv2domains"],
        "bucket": "api",
        "ground_truth": (
            "All domains are listed by sending a GET request to `/api/v2/domains`. "
            "The response is a JSON array of domain objects, each containing fields "
            "such as `id`, `name`, `status`, and associated hosting details."
        ),
        "reference_context": (
            "`GET /api/v2/domains` returns a paginated list of all domains on the "
            "server. Each domain object includes `id`, `name`, `hosting_type`, and "
            "`status` fields."
        ),
    },
    {
        "query": "authenticate with Plesk API using secret key",
        "relevant": ["X-API-Key", "secretkey", "Authorization"],
        "bucket": "api",
        "ground_truth": (
            "Plesk REST API authentication uses the `X-API-Key` header. The value is "
            "the secret key generated in Plesk under Tools & Settings > API Access. "
            "Alternatively, HTTP Basic Auth with admin credentials is supported."
        ),
        "reference_context": (
            "To authenticate REST API requests, include the `X-API-Key: "
            "<your-secret-key>` header. The secret key is generated in Plesk admin "
            "under Tools & Settings > API Access Keys."
        ),
    },
    {
        "query": "add a custom button to Plesk panel",
        "relevant": ["button", "custombuttons", "addButton"],
        "bucket": "guide",
        "ground_truth": (
            "Custom buttons are added to the Plesk panel by defining a `buttons.xml` "
            "descriptor file in the extension's `htdocs` folder, specifying the "
            "button's label, URL, placement context (e.g., domain list, service "
            "plans), and optional icon."
        ),
        "reference_context": (
            "Custom buttons are configured via `buttons.xml` in the extension "
            "package. Each `<button>` element defines `name`, `url`, `place` (the "
            "Plesk UI location), and optionally `icon` and `description`."
        ),
    },
    {
        "query": "package a Plesk extension for distribution",
        "relevant": ["plesk ext", "package", ".zip"],
        "bucket": "guide",
        "ground_truth": (
            "A Plesk extension is packaged for distribution by running `plesk ext "
            "--package` from the extension directory. This produces a `.zip` archive "
            "following Plesk's required structure: `meta.xml`, `htdocs/`, and an "
            "optional `plib/` directory."
        ),
        "reference_context": (
            "Run `plesk ext <ext-name> --package` to produce a distributable `.zip` "
            "archive. The package must contain a valid `meta.xml` descriptor and "
            "the `htdocs/` directory. The `plib/` directory is optional for "
            "server-side PHP logic."
        ),
    },
    {
        "query": "register a new page in Plesk JS SDK",
        "relevant": ["registerPage", "router"],
        "bucket": "js-sdk",
        "ground_truth": (
            "A new page is registered in the Plesk JS SDK using "
            "`plesk.router.registerPage({ name, component, path })`. The page "
            "component must be a Vue component exported from the extension's JS "
            "bundle."
        ),
        "reference_context": (
            "`plesk.router.registerPage()` registers a Vue-based page in the Plesk "
            "panel. It accepts an object with `name` (route name), `path` (URL "
            "path), and `component` (Vue component reference)."
        ),
    },
    {
        "query": "SSL certificate management",
        "relevant": ["certificate", "SSL", "TLS"],
        "bucket": None,
        "ground_truth": (
            "SSL certificates in Plesk are managed under Domains > <domain> > "
            "SSL/TLS Certificates. The REST API supports certificate operations via "
            "`/api/v2/certificates`. CLI management uses `plesk bin certificate`."
        ),
        "reference_context": (
            "SSL/TLS certificate management is available across Plesk's "
            "interfaces: the panel UI under domain settings, the REST API at "
            "`/api/v2/certificates`, and the CLI via `plesk bin certificate "
            "--list|--install|--remove`."
        ),
    },
    {
        "query": "backup and restore Plesk",
        "relevant": ["backup", "restore"],
        "bucket": None,
        "ground_truth": (
            "Plesk backups are created and restored via Tools & Settings > Backup "
            "Manager in the UI, via CLI using `plesk bin pleskbackup` and `plesk "
            "bin pleskrestore`, or through the REST API endpoints under "
            "`/api/v2/backups`."
        ),
        "reference_context": (
            "`plesk bin pleskbackup` creates a full or partial server backup. "
            "`plesk bin pleskrestore` restores from a backup file. Both commands "
            "accept flags for scope (domains, mail, databases) and destination path."
        ),
    },
    # --- NEW 8 QUERIES ---
    {
        "query": "handle errors returned by the Plesk REST API",
        "relevant": ["error", "status_code", "response"],
        "bucket": "api",
        "ground_truth": (
            "Plesk REST API errors are returned as JSON objects with a `code` "
            "field (HTTP status) and a `message` field describing the error. "
            "Clients should check the HTTP status code and parse the error body "
            "to display meaningful messages."
        ),
        "reference_context": (
            "When a Plesk REST API request fails, the response body is typically "
            '{"code": 0, "message": "<description>"} (for internal/fatal errors) '
            "or includes additional fields in some cases. Always check the HTTP "
            "status code (4xx/5xx) first. Common codes include 400 (bad request), "
            "401 (unauthorized), 404 (not found), and 409 (conflict)."
        ),
    },
    {
        "query": "list all databases for a domain via API",
        "relevant": ["databases", "GET", "domain_id"],
        "bucket": "api",
        "ground_truth": (
            "Databases for a specific domain are listed using `GET "
            "/api/v2/domains/{domain_id}/databases`. The response is a JSON array "
            "of database objects including `id`, `name`, `type` (MySQL, "
            "PostgreSQL), and `server_id`."
        ),
        "reference_context": (
            "`GET /api/v2/domains/{domain_id}/databases` returns all databases "
            "belonging to a domain. Each entry includes `id`, `name`, `db_type`, "
            "and `db_server_id`."
        ),
    },
    {
        "query": "enable or disable a Plesk extension from CLI",
        "relevant": ["plesk ext", "enable", "disable"],
        "bucket": "cli",
        "ground_truth": (
            "A Plesk extension is enabled with `plesk ext <ext-name> --enable` "
            "and disabled with `plesk ext <ext-name> --disable`. These commands "
            "toggle the extension state without uninstalling it."
        ),
        "reference_context": (
            "`plesk ext <ext-name> --enable` activates an installed extension. "
            "`plesk ext <ext-name> --disable` deactivates it without removing "
            "files. Use `plesk ext --list` to see all extensions and their states."
        ),
    },
    {
        "query": "emit and listen to custom events in the Plesk JS SDK",
        "relevant": ["emit", "on", "event"],
        "bucket": "js-sdk",
        "ground_truth": (
            "Custom events in the Plesk JS SDK are dispatched using "
            "`plesk.events.emit(eventName, payload)` and subscribed to with "
            "`plesk.events.on(eventName, handler)`. This allows cross-component "
            "communication within extension UI."
        ),
        "reference_context": (
            "`plesk.events.on(event, callback)` registers a listener for the "
            "named event. `plesk.events.emit(event, data)` dispatches the event "
            "to all registered listeners. Both methods are available on the "
            "global `plesk` object injected into extension scripts."
        ),
    },
    {
        "query": "what PHP version is required to use pm_Config",
        "relevant": ["pm_Config", "php", "version"],
        "bucket": "php-stubs",
        "ground_truth": (
            "The Plesk PHP stubs do not specify a minimum PHP version for "
            "`pm_Config` directly; however, Plesk extensions generally require "
            "PHP 7.4 or higher based on Plesk's supported PHP stack."
        ),
        "reference_context": (
            "The `pm_Config` class is part of the Plesk PHP API stubs. No "
            "explicit PHP version constraint is documented in the stubs; "
            "compatibility follows the minimum PHP version enforced by the "
            "Plesk installation environment."
        ),
    },
    {
        "query": "show DNS records for a domain via Plesk REST API",
        "relevant": ["dns", "records", "GET", "domain"],
        "bucket": "api",
        "ground_truth": (
            "DNS records for a domain are retrieved with `GET "
            "/api/v2/domains/{domain_id}/dns/records`. The response is a JSON "
            "array of DNS record objects, each with `type`, `host`, `value`, "
            "and `ttl`."
        ),
        "reference_context": (
            "`GET /api/v2/domains/{domain_id}/dns/records` lists all DNS "
            "records for the domain. Each record object includes `id`, `type` "
            "(A, CNAME, MX, TXT, etc.), `host`, `value`, and `ttl`."
        ),
    },
    {
        "query": "how to display a notification in the Plesk panel from an extension",
        "relevant": ["notification", "alert", "UI", "js-sdk"],
        "bucket": "js-sdk",
        "ground_truth": (
            "Notifications in the Plesk panel are displayed from an extension "
            "using `plesk.ui.notify({ type, message })`, where `type` is one "
            "of `success`, `info`, `warning`, or `error`."
        ),
        "reference_context": (
            "`plesk.ui.notify({ type: 'success' | 'info' | 'warning' | 'error', "
            "message: string })` displays a toast-style notification in the "
            "Plesk panel UI. It is available on the global `plesk` object "
            "within extension JavaScript."
        ),
    },
    {
        "query": (
            "what happens if you call plesk bin subscription on a non-existent domain"
        ),
        "relevant": ["subscription", "error", "not found"],
        "bucket": "cli",
        "ground_truth": (
            "If `plesk bin subscription` is called with a domain that does not "
            "exist, the CLI returns a non-zero exit code and an error message "
            "indicating the domain or subscription was not found. No changes "
            "are made."
        ),
        "reference_context": (
            "When `plesk bin subscription --info <name>` or similar commands "
            "reference a non-existent subscription, Plesk CLI outputs an error "
            "such as `Subscription '<name>' was not found` and exits with a "
            "non-zero status code."
        ),
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
