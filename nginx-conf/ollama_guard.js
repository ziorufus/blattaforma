function jsonError(r, status, error, extra) {
    var response = {
        error: error
    };

    if (extra && typeof extra === "object") {
        Object.keys(extra).forEach(function (key) {
            response[key] = extra[key];
        });
    }

    r.headersOut["Content-Type"] = "application/json";
    r.return(status, JSON.stringify(response));
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

    var model = request.model;
    var requestedNumCtx;

    if (
        request.options &&
        typeof request.options === "object" &&
        !Array.isArray(request.options)
    ) {
        requestedNumCtx = request.options.num_ctx;
    }

    if (
        model !== undefined &&
        (typeof model !== "string" || model.length === 0)
    ) {
        jsonError(r, 400, "model must be a non-empty string");
        return;
    }

    if (
        requestedNumCtx !== undefined &&
        (!Number.isInteger(requestedNumCtx) || requestedNumCtx <= 0)
    ) {
        jsonError(
            r,
            400,
            "options.num_ctx must be a positive integer"
        );
        return;
    }

    r.variables.ollama_auth_mode = "inference";

    r.variables.ollama_model =
        model === undefined || model === null
            ? ""
            : model;

    r.variables.ollama_num_ctx =
        requestedNumCtx === undefined
            ? ""
            : String(requestedNumCtx);

    var reply;

    try {
        reply = await r.subrequest("/_ollama_auth_check", {
            method: "GET"
        });
    } catch (e) {
        r.error("Ollama authorization check failed: " + e);
        jsonError(r, 502, "Authorization service unavailable");
        return;
    }

    if (reply.status === 401 || reply.status === 403) {
        r.headersOut["Content-Type"] =
            reply.headersOut["Content-Type"] || "application/json";

        r.return(
            reply.status,
            reply.responseText ||
                JSON.stringify({
                    error: "Request rejected by policy"
                })
        );
        return;
    }

    if (reply.status < 200 || reply.status >= 300) {
        r.error(
            "Authorization service returned unexpected status " +
            reply.status
        );

        jsonError(
            r,
            502,
            "Invalid response from authorization service"
        );
        return;
    }

    /*
     * Opzionale: il Python può comunicare il valore effettivamente
     * caricato/autorizzato.
     */
    const loadedHeader =
        reply.headersOut["X-Ollama-Loaded-Num-Ctx"];

    if (loadedHeader !== undefined && loadedHeader !== "") {
        const loadedNumCtx = Number.parseInt(loadedHeader, 10);

        if (!Number.isInteger(loadedNumCtx) || loadedNumCtx <= 0) {
            r.error(
                `Invalid loaded context returned by authorization service: ${loadedHeader}`
            );

            jsonError(
                r,
                502,
                "Authorization service returned an invalid context size"
            );
            return;
        }

        /*
         * Qui non stai più verificando che requestedNumCtx sia consentito:
         * quella decisione è già stata presa dal Python.
         *
         * Stai solo applicando al body il valore effettivo restituito
         * dal servizio.
         */
        if (
            !request.options ||
            typeof request.options !== "object" ||
            Array.isArray(request.options)
        ) {
            request.options = {};
        }

        request.options.num_ctx = loadedNumCtx;
    }

    r.variables.ollama_request_body = JSON.stringify(request);
}

export default { check: check };
