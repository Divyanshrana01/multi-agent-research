from fastapi import Request, HTTPException


# checks that whoever is calling our api sent the right key in the headers
# we attach this to routes so random people can't hit our endpoints
async def require_api_key(request: Request) -> None:
    # grab the config we stored on the app when it started up
    config = request.app.state.config
    if not config.api_key:
        return  # auth disabled when no key is configured
    # look for the key in the request headers, empty string if missing
    key = request.headers.get("X-API-Key", "")
    # if it doesn't match, stop here and send back 401 unauthorized
    if key != config.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
