import pytest
from blacksheep import HttpMethod
from blacksheep.server.routing import Route, RouteDuplicate, Router

FAKE = b"FAKE"

MATCHING_ROUTES = [
    ("head", b"", b"/"),
    ("get", b"", b"/"),
    ("head", b"/", b"/"),
    ("get", b"/", b"/"),
    ("get", b"/:a", b"/foo"),
    ("get", b"/foo", b"/foo"),
    ("get", b"/foo", b"/Foo"),
    ("get", b"/:a/:b", b"/foo/oof"),
    ("post", b"/", b"/"),
    ("post", b"/:id", b"/123"),
    ("put", b"/", b"/"),
    ("delete", b"/", b"/"),
]

NON_MATCHING_ROUTE = [
    ("head", b"/", b"/foo"),
    ("get", b"/", b"/foo"),
    ("post", b"/", b"/foo"),
    ("post", b"/foo", b"/123"),
    ("put", b"/a/b/c/d", b"/a/b/c/"),
    ("put", b"/a/b/c/d", b"/a/b/c/d/e"),
    ("delete", b"/", b"/a"),
]


def mock_handler():
    return None


class MockHandler:
    def __init__(self, request_handler, auth_handler):
        self.request_handler = request_handler
        self.auth_handler = auth_handler


@pytest.mark.parametrize(
    "pattern,url,expected_values",
    [
        (b"/foo/:id", b"/foo/123", {"id": "123"}),
        (b"/foo/{id}", b"/foo/123", {"id": "123"}),
        ("/foo/:id", b"/foo/123", {"id": "123"}),
        ("/foo/{id}", b"/foo/123", {"id": "123"}),
        (b"/foo/:id/ufo/:b", b"/foo/223/ufo/a13", {"id": "223", "b": "a13"}),
        (b"/foo/{id}/ufo/{b}", b"/foo/223/ufo/a13", {"id": "223", "b": "a13"}),
        ("/foo/:id/ufo/:b", b"/foo/223/ufo/a13", {"id": "223", "b": "a13"}),
        ("/foo/{id}/ufo/{b}", b"/foo/223/ufo/a13", {"id": "223", "b": "a13"}),
        (b"/foo/:id/ufo/:b", b"/Foo/223/Ufo/a13", {"id": "223", "b": "a13"}),
        (b"/:a", b"/Something", {"a": "Something"}),
        (b"/{a}", b"/Something", {"a": "Something"}),
        (b"/alive", b"/alive", None),
    ],
)
def test_route_good_matches(pattern, url, expected_values):
    route = Route(pattern, mock_handler)
    match = route.match(url)

    assert match is not None
    assert match.values == expected_values


@pytest.mark.parametrize(
    "pattern",
    ["/a", "/a/b", "/a/b/c", "/cats/:cat_id", "/cats/:cat_id/friends"],
)
def test_route_repr(pattern: str):
    route = Route(pattern, mock_handler)
    assert repr(route) == f"<Route {pattern}>"


@pytest.mark.parametrize(
    "pattern,url",
    [
        (b"/foo/:id", b"/fo/123"),
        (b"/foo/:id/ufo/:b", b"/foo/223/uof/a13"),
        (b"/:a", b"/"),
    ],
)
def test_route_bad_matches(pattern, url):
    route = Route(pattern, mock_handler)
    match = route.match(url)

    assert match is None


@pytest.mark.parametrize("pattern", [b"/:a/:a", b"/foo/:a/ufo/:a", b"/:foo/a/:foo"])
def test_invalid_route_repeated_group_name(pattern):
    with pytest.raises(ValueError):
        Route(pattern, mock_handler)


def test_route_handler_can_be_anything():
    def request_handler():
        pass

    def auth_handler():
        pass

    handler = MockHandler(request_handler, auth_handler)

    route = Route(b"/", handler)
    match = route.match(b"/")

    assert match is not None
    assert match.handler.request_handler is request_handler
    assert match.handler.auth_handler is auth_handler


@pytest.mark.parametrize("method,pattern,url", MATCHING_ROUTES)
def test_router_add_method(method, pattern, url):
    router = Router()
    router.add(method, pattern, mock_handler)

    route = router.get_match(method, url)

    assert route is not None
    assert route.handler is mock_handler

    route = router.get_match(FAKE, url)
    assert route is None


@pytest.mark.parametrize("method,pattern,url", NON_MATCHING_ROUTE)
def test_router_not_matching_routes(method, pattern, url):
    router = Router()
    router.add(method, pattern, mock_handler)
    route = router.get_match(method, url)
    assert route is None


@pytest.mark.parametrize("method,pattern,url", MATCHING_ROUTES)
def test_router_add_shortcuts(method, pattern, url):
    router = Router()

    fn = getattr(router, f"add_{method}")

    def home():
        return "Hello, World"

    fn(pattern, home)

    route = router.get_match(method.upper(), url)

    assert route is not None
    assert route.handler is home

    value = route.handler()
    assert value == "Hello, World"

    route = router.get_match(FAKE, url)
    assert route is None


@pytest.mark.parametrize("decorator,pattern,url", MATCHING_ROUTES)
def test_router_decorator(decorator, pattern, url):
    router = Router()

    method = getattr(router, decorator)

    @method(pattern)
    def home():
        return "Hello, World"

    route = router.get_match(decorator.upper(), url)

    assert route is not None
    assert route.handler is home

    value = route.handler()
    assert value == "Hello, World"

    route = router.get_match(FAKE, url)
    assert route is None


def test_router_match_any_by_extension():
    router = Router()

    def a():
        ...

    def b():
        ...

    router.add_get("/a/*.js", a)
    router.add_get("/b/*.css", b)

    m = router.get_match(HttpMethod.GET, b"/a/anything/really")
    assert m is None

    m = router.get_match(HttpMethod.GET, b"/a/anything/really.js")
    assert m is not None
    assert m.handler is a
    assert m.values.get("tail") == "anything/really"

    m = router.get_match(HttpMethod.GET, b"/b/anything/really.css")
    assert m is not None
    assert m.handler is b
    assert m.values.get("tail") == "anything/really"


def test_router_match_any_below():
    router = Router()

    def a():
        ...

    def b():
        ...

    def c():
        ...

    def d():
        ...

    router.add_get("/a/*", a)
    router.add_get("/b/*", b)
    router.add_get("/c/*", c)
    router.add_get("/d/*", d)

    m = router.get_match(HttpMethod.GET, b"/a")
    assert m is not None
    assert m.handler is a
    assert m.values.get("tail") == ""

    m = router.get_match(HttpMethod.GET, b"/a/")
    assert m is not None
    assert m.handler is a
    assert m.values.get("tail") == ""

    m = router.get_match(HttpMethod.GET, b"/a/anything/really")
    assert m is not None
    assert m.handler is a
    assert m.values.get("tail") == "anything/really"

    m = router.get_match(HttpMethod.GET, b"/b/anything/really")
    assert m is not None
    assert m.handler is b
    assert m.values.get("tail") == "anything/really"

    m = router.get_match(HttpMethod.GET, b"/c/anything/really")
    assert m is not None
    assert m.handler is c
    assert m.values.get("tail") == "anything/really"

    m = router.get_match(HttpMethod.GET, b"/d/anything/really")
    assert m is not None
    assert m.handler is d
    assert m.values.get("tail") == "anything/really"

    m = router.get_match(HttpMethod.POST, b"/a/anything/really")
    assert m is None

    m = router.get_match(HttpMethod.POST, b"/b/anything/really")
    assert m is None

    m = router.get_match(HttpMethod.POST, b"/c/anything/really")
    assert m is None

    m = router.get_match(HttpMethod.POST, b"/d/anything/really")
    assert m is None


def test_router_match_among_many():
    router = Router()

    def home():
        ...

    def home_verbose():
        ...

    def home_options():
        ...

    def home_connect():
        ...

    def get_foo():
        ...

    def create_foo():
        ...

    def patch_foo():
        ...

    def delete_foo():
        ...

    router.add_trace("/", home_verbose)
    router.add_options("/", home_options)
    router.add_connect("/", home_connect)
    router.add_get("/", home)
    router.add_get("/foo", get_foo)
    router.add_patch("/foo", patch_foo)
    router.add_post("/foo", create_foo)
    router.add_delete("/foo", delete_foo)

    m = router.get_match(HttpMethod.GET, b"/")
    assert m is not None
    assert m.handler is home

    m = router.get_match(HttpMethod.TRACE, b"/")
    assert m is not None
    assert m.handler is home_verbose

    m = router.get_match(HttpMethod.CONNECT, b"/")
    assert m is not None
    assert m.handler is home_connect

    m = router.get_match(HttpMethod.OPTIONS, b"/")
    assert m is not None
    assert m.handler is home_options

    m = router.get_match(HttpMethod.POST, b"/")
    assert m is None

    m = router.get_match(HttpMethod.GET, b"/foo")
    assert m is not None
    assert m.handler is get_foo

    m = router.get_match(HttpMethod.POST, b"/foo")
    assert m is not None
    assert m.handler is create_foo

    m = router.get_match(HttpMethod.PATCH, b"/foo")
    assert m is not None
    assert m.handler is patch_foo

    m = router.get_match(HttpMethod.DELETE, b"/foo")
    assert m is not None
    assert m.handler is delete_foo


def test_router_match_among_many_decorators():
    router = Router()

    @router.get("/")
    def home():
        ...

    @router.trace("/")
    def home_verbose():
        ...

    @router.options("/")
    def home_options():
        ...

    @router.connect("/")
    def home_connect():
        ...

    @router.get("/foo")
    def get_foo():
        ...

    @router.post("/foo")
    def create_foo():
        ...

    @router.patch("/foo")
    def patch_foo():
        ...

    @router.delete("/foo")
    def delete_foo():
        ...

    m = router.get_match(HttpMethod.GET, b"/")
    assert m is not None
    assert m.handler is home

    m = router.get_match(HttpMethod.TRACE, b"/")
    assert m is not None
    assert m.handler is home_verbose

    m = router.get_match(HttpMethod.CONNECT, b"/")
    assert m is not None
    assert m.handler is home_connect

    m = router.get_match(HttpMethod.OPTIONS, b"/")
    assert m is not None
    assert m.handler is home_options

    m = router.get_match(HttpMethod.POST, b"/")
    assert m is None

    m = router.get_match(HttpMethod.GET, b"/foo")
    assert m is not None
    assert m.handler is get_foo

    m = router.get_match(HttpMethod.POST, b"/foo")
    assert m is not None
    assert m.handler is create_foo

    m = router.get_match(HttpMethod.PATCH, b"/foo")
    assert m is not None
    assert m.handler is patch_foo

    m = router.get_match(HttpMethod.DELETE, b"/foo")
    assert m is not None
    assert m.handler is delete_foo


def test_router_match_with_trailing_slash():
    router = Router()

    def get_foo():
        ...

    def create_foo():
        ...

    router.add_get("/foo", get_foo)
    router.add_post("/foo", create_foo)

    m = router.get_match(HttpMethod.GET, b"/foo/")

    assert m is not None
    assert m.handler is get_foo

    m = router.get_match(HttpMethod.POST, b"/foo/")

    assert m is not None
    assert m.handler is create_foo

    m = router.get_match(HttpMethod.POST, b"/foo//")

    assert m is None


def test_fallback_route():
    router = Router()

    def not_found_handler():
        pass

    router.fallback = not_found_handler
    assert isinstance(router.fallback, Route)
    assert router.fallback.handler is not_found_handler

    m = router.get_match(HttpMethod.POST, b"/")

    assert m is not None
    assert m.handler is not_found_handler


def test_fallback_route_must_be_callable_or_route():
    router = Router()

    def not_found_handler():
        pass

    router.fallback = Route("*", not_found_handler)
    router.fallback = not_found_handler

    class Example:
        def __call__(self):
            pass

    router.fallback = Example()

    with pytest.raises(ValueError):
        router.fallback = False

    with pytest.raises(ValueError):
        router.fallback = "Something"


@pytest.mark.parametrize(
    "first_route,second_route",
    [
        ("/", "/"),
        (b"/", b"/"),
        (b"/", "/"),
        ("/", b"/"),
        ("/home/", "/home"),
        (b"/home/", b"/home"),
        ("/home", "/home/"),
        (b"/home", b"/home/"),
        ("/home", "/home//"),
        (b"/home", b"/home//"),
        ("/hello/world", "/hello/world/"),
        (b"/hello/world", b"/hello/world//"),
        ("/a/b", "/a/b"),
    ],
)
def test_duplicate_pattern_raises(first_route, second_route):
    router = Router()

    def home():
        ...

    def another():
        ...

    router.add_get(first_route, home)

    with pytest.raises(RouteDuplicate):
        router.add_get(second_route, another)


def test_duplicate_pattern_star_raises():
    router = Router()

    def home():
        ...

    def another():
        ...

    router.add_get("*", home)

    with pytest.raises(RouteDuplicate):
        router.add_get("*", another)


def test_more_than_one_star_raises():
    router = Router()

    def home():
        ...

    with pytest.raises(ValueError):
        router.add_get("*/*", home)


def test_automatic_pattern_with_ellipsis():
    router = Router()

    @router.get(...)
    def home():
        ...

    @router.get(...)
    def another():
        ...

    match = router.get_match("GET", "/")
    assert match is None

    match = router.get_match("GET", "/home")

    assert match is not None
    assert match.handler is home

    match = router.get_match("GET", "/another")

    assert match is not None
    assert match.handler is another


def test_automatic_pattern_with_ellipsis_name_normalization():
    router = Router()

    @router.get(...)
    def hello_world():
        ...

    match = router.get_match("GET", "/hello_world")

    assert match is None

    match = router.get_match("GET", "/hello-world")

    assert match is not None
    assert match.handler is hello_world


def test_automatic_pattern_with_ellipsis_index_name():
    router = Router()

    @router.get(...)
    def index():
        ...

    match = router.get_match("GET", "/")

    assert match is not None
    assert match.handler is index


def test_router_iterable():
    router = Router()

    @router.get("/")
    def home():
        ...

    @router.trace("/")
    def home_verbose():
        ...

    @router.options("/")
    def home_options():
        ...

    routes = list(router)
    assert len(routes) == 3

    handlers = {home, home_verbose, home_options}

    for route in routes:
        assert route.handler in handlers

    def fallback():
        ...

    router.fallback = fallback

    routes = list(router)
    assert len(routes) == 4

    handlers = {home, home_verbose, home_options, fallback}

    for route in routes:
        assert route.handler in handlers


@pytest.mark.parametrize(
    "route_pattern,expected_pattern",
    [
        ["/", "/"],
        ["/api/v1/help", "/api/v1/help"],
        ["/api/cats/:cat_id", "/api/cats/{cat_id}"],
        ["/api/cats/:cat_id/friends", "/api/cats/{cat_id}/friends"],
        [
            "/api/cats/:cat_id/friends/:friend_id",
            "/api/cats/{cat_id}/friends/{friend_id}",
        ],
    ],
)
def test_route_to_openapi_pattern(route_pattern, expected_pattern):
    route = Route(route_pattern, object())

    assert route.mustache_pattern == expected_pattern
