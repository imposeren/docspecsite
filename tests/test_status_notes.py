import pytest
from conftest import make_doc

from docspecsite.check import StatusNoteCheck
from docspecsite.schema import STATUS_NOTES


def check_doc(body: str, status: object) -> list[tuple[int | None, str, str | None]]:
    """Check a doc ``import.md`` whose body starts on file line 10; return its problems as (line, message, hint)."""
    doc = make_doc("import.md", body, 10, status=status)
    return [(p.line_number, p.message, p.hint) for p in StatusNoteCheck(STATUS_NOTES).check(doc)]


def test_matching_status_note_passes() -> None:
    assert check_doc("# Import\n\n## Import\n\n> **Not built yet.**\n", ["implemented", "specified"]) == []


def test_one_value_list_without_notes_passes() -> None:
    assert check_doc("# A\n\n## B\n", ["specified"]) == []


def test_single_changed_without_notes_passes() -> None:
    assert check_doc("# A\n\n## B\n", "changed") == []


def test_status_note_with_trailing_text_passes() -> None:
    body = "# E\n\n## File name\n\n> **Changed, not built yet.** Exports still use the old file name.\n"
    assert check_doc(body, ["implemented", "changed"]) == []


def test_listed_status_without_status_note() -> None:
    assert check_doc("# I\n\n## A\n\n> **Not built yet.**\n", ["implemented", "specified", "changed"]) == [
        (
            1,
            '"changed" is in "status", but no section has a "Changed, not built yet." status note',
            (
                'add a "> **Changed, not built yet.**" status note to a section, '
                'or remove "changed" from "status" so it reads "status: [implemented, specified]"'
            ),
        )
    ]


def test_status_note_not_in_status() -> None:
    body = "# I\n\n## A\n\n> **Not built yet.**\n\n## Export\n\n> **Changed, not built yet.**\n"
    assert check_doc(body, ["implemented", "specified"]) == [
        (
            18,
            'status note "Changed, not built yet." ("changed") in a doc whose "status" is "[implemented, specified]"',
            (
                'add "changed" to "status" so it reads "status: [implemented, specified, changed]", '
                'or remove the status note from the section "## Export"'
            ),
        )
    ]


def test_status_note_repeats_first_status() -> None:
    body = "# I\n\n## Import\n\n> **Built.**\n\n## Export\n\nText.\n\n### Backend checks\n\n> **Not built yet.**\n"
    assert check_doc(body, ["specified", "implemented"]) == [
        (
            22,
            (
                'status note "Not built yet." ("specified") gives the status the section "### Backend checks" '
                'already has from "status: [specified, implemented]"'
            ),
            'remove the "Not built yet." status note from the section "### Backend checks"',
        )
    ]


def test_subsection_has_its_own_status() -> None:
    body = "# I\n\n## Import\n\nText.\n\n### Backend checks\n\n> **Not built yet.**\n"
    assert check_doc(body, ["implemented", "specified"]) == []


def test_subsection_note_repeating_its_section_note_passes() -> None:
    body = "# I\n\n## Import\n\n> **Built.**\n\n### Sub\n\n> **Built.**\n"
    assert check_doc(body, ["specified", "implemented"]) == []


def test_section_note_does_not_cover_subsections() -> None:
    body = "# I\n\n## Import\n\n> **Built.**\n\n### Backend checks\n\n> **Not built yet.**\n"
    assert check_doc(body, ["specified", "implemented"]) == [
        (
            18,
            (
                'status note "Not built yet." ("specified") gives the status the section '
                '"### Backend checks" already has from "status: [specified, implemented]"'
            ),
            'remove the "Not built yet." status note from the section "### Backend checks"',
        )
    ]


def test_later_level_one_heading_is_a_section() -> None:
    body = "# Import\n\nText.\n\n# Export\n\n> **Not built yet.**\n"
    assert check_doc(body, ["implemented", "specified"]) == []


def test_heading_before_title_is_a_section() -> None:
    body = "## Intro\n\n> **Not built yet.**\n\n# Import\n\nText.\n"
    assert check_doc(body, ["implemented", "specified"]) == []


@pytest.mark.parametrize(
    ("status", "hint"),
    [
        (
            "implemented",
            (
                'add "specified" to "status" so it reads "status: [implemented, specified]", '
                'or remove the status note from the section "## Import"'
            ),
        ),
        ("specified", 'remove the status note from the section "## Import"'),
        ("draft", 'remove the status note from the section "## Import"'),
    ],
)
def test_status_note_in_single_status_doc(status: str, hint: str) -> None:
    [(line, message, found_hint)] = check_doc("# I\n\n## Import\n\n> **Not built yet.**\n", status)
    assert (line, message, found_hint) == (
        14,
        f'status note "Not built yet." ("specified") in a doc with the single status "{status}"',
        hint,
    )


def test_status_note_under_title_gives_one_problem() -> None:
    assert check_doc("# Import\n\n> **Not built yet.**\n", "implemented") == [
        (
            12,
            'status note "Not built yet." ("specified") right under the doc\'s title "# Import"',
            'set the doc\'s "status" instead',
        )
    ]


def test_title_note_does_not_give_a_status() -> None:
    assert check_doc("# Import\n\n> **Not built yet.**\n", ["implemented", "specified"]) == [
        (
            12,
            'status note "Not built yet." ("specified") right under the doc\'s title "# Import"',
            'set the doc\'s "status" instead',
        ),
        (
            1,
            '"specified" is in "status", but no section has a "Not built yet." status note',
            (
                'add a "> **Not built yet.**" status note to a section, '
                'or remove "specified" from "status" so it reads "status: implemented"'
            ),
        ),
    ]


@pytest.mark.parametrize(
    "status", [["implemented", "specified", "specified"], ["draft", "specified"], ["implemented", "done"], 5, []]
)
def test_rejected_status_is_skipped(status: object) -> None:
    assert check_doc("# I\n\n## A\n\n> **Not built yet.**\n", status) == []


def test_note_further_down_a_section_is_ordinary_text() -> None:
    assert check_doc("# I\n\n## A\n\nText.\n\n> **Not built yet.**\n", "implemented") == []


def test_note_text_in_code_block_passes() -> None:
    assert check_doc("# I\n\n## A\n\n```\n> **Not built yet.**\n```\n", "implemented") == []


def test_status_note_after_other_note_counts() -> None:
    body = "# I\n\n## Import\n\n> **Experimental.** The format may change.\n> **Not built yet.**\n"
    assert check_doc(body, ["implemented", "specified"]) == []


def test_note_after_paragraph_is_not_a_status_note() -> None:
    [(line, message, hint)] = check_doc(
        "# I\n\n## Import\n\nText.\n\n> **Not built yet.**\n", ["implemented", "specified"]
    )
    assert (line, message) == (1, '"specified" is in "status", but no section has a "Not built yet." status note')
    assert hint == (
        'add a "> **Not built yet.**" status note to a section, '
        'or remove "specified" from "status" so it reads "status: implemented"'
    )


@pytest.mark.parametrize(("label", "status"), [("Changed, not built yet.", "changed"), ("Not built yet.", "specified")])
def test_two_status_notes_in_one_section(label: str, status: str) -> None:
    body = f"# I\n\n## Import\n\n> **Not built yet.**\n> **{label}**\n"
    assert check_doc(body, ["implemented", *dict.fromkeys(["specified", status])]) == [
        (
            15,
            (
                f'status note "{label}" ("{status}") in the section "## Import", '
                'which already has the status note "Not built yet." ("specified")'
            ),
            'keep one status note in the section "## Import"',
        )
    ]


def test_unknown_label_passes() -> None:
    assert check_doc("# I\n\n## A\n\n> **Deprecated soon.** Use the new import.\n", "implemented") == []
