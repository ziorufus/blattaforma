// Validates the JSON body of every request forwarded to the local helper
// service. This is a defense-in-depth check only: the authoritative
// allow-list of labels/actions lives in the root-only whitelist read by
// `bin/daemonctl` on the machine (see helpers/macos-daemons/), not here.

const LABEL_RE = /^[A-Za-z0-9._-]+$/;

function jsonError(r, status, error) {
    r.headersOut["Content-Type"] = "application/json";
    r.return(status, JSON.stringify({ error: error }));
}

async function check(r) {
    var request;

    try {
        request = await r.readRequestJSON();
    } catch (e) {
        jsonError(r, 400, "Invalid JSON request body");
        return;
    }

    if (!request || typeof request !== "object" || Array.isArray(request)) {
        jsonError(r, 400, "The request body must be a JSON object");
        return;
    }

    if (typeof request.label !== "string" || !LABEL_RE.test(request.label)) {
        jsonError(
            r,
            400,
            "label must be a non-empty string of letters, digits, '.', '_' or '-'"
        );
        return;
    }
}

export default { check: check };
