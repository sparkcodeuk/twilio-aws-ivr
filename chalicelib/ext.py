from chalice import Chalice


def url_of(app: Chalice, path: str = None):
    """
    Returns a usable URL based on an API endpoint path
    """

    if not app.current_request:
        return path

    request = app.current_request.to_dict()

    if not path.startswith('/') and path is not None:
        raise Exception(f'path must start with a leading slash: {path}')

    try:
        scheme = request['headers']['x-forwarded-proto']
    except KeyError:
        scheme = 'http'

    try:
        host = request['headers']['host']
    except KeyError:
        raise Exception('Unable to determine host')

    path = '' if path is None else str(path)

    try:
        stage = request['context']['stage']
    except KeyError:
        stage = ''

    # Normalise the path of this URL
    stage = stage.strip('/')
    path = path.lstrip('/')
    pathinfo = f'{stage}/{path}'.lstrip('/')

    return f'{scheme}://{host}/{pathinfo}'
