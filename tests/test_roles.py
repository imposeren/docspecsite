from docspecsite.roles import RoleRef


def test_role_parse() -> None:
    assert RoleRef.parse("~.attempt") == RoleRef(".attempt", None, True)
    assert RoleRef.parse("docspecsite.build") == RoleRef("docspecsite.build", None, False)
    titled = RoleRef.parse("the builder <docspecsite.build.SiteBuilder>")
    assert titled == RoleRef("docspecsite.build.SiteBuilder", "the builder", False)
    assert titled.written_text == "the builder"
    assert RoleRef.parse("~.attempt").written_text == ".attempt"


def test_role_display_text() -> None:
    assert RoleRef.parse(".attempt").display_text("p.m.C.attempt") == "p.m.C.attempt"
    assert RoleRef.parse("~p.m.C").display_text("p.m.C") == "C"
    assert RoleRef.parse("the class <~p.m.C>").display_text("p.m.C") == "the class"
