"""
A malformed automation action is refused, and says which one.

WHY THIS IS A TEST
POST /api/automations with an action missing its key answered

    500  {"message": "Internal Server Error", "detail": "'key'"}

The single word 'key' was the entire explanation. The builder was a
comprehension doing x["key"] over whatever the caller sent, so a KeyError
escaped as a server error.

This is the same class as the equity handlers that read payload["stakeholder_id"]
directly, but one level down: the top-level body was fine and the fault was
inside a list ITEM. A scan for payload["x"] at the top level cannot see it,
which is why walking the workflow found it and the endpoint sweep did not.

Creating an automation with a malformed action is the caller's mistake, and
they can only fix it if we say which action and which field.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services.automations_service import _actions_from


def test_an_action_without_a_key_is_refused():
    with pytest.raises(HTTPException) as e:
        _actions_from([{"kind": "notify"}])
    assert e.value.status_code == 422
    detail = str(e.value.detail)
    assert "action 0" in detail, "the caller cannot tell WHICH action is wrong"
    assert "'key'" in detail
    assert "kind" in detail, "saying what WAS supplied is how they spot the typo"


def test_the_offending_index_is_the_real_one():
    """With several actions, naming the wrong index sends someone to the wrong
    line of their config."""
    with pytest.raises(HTTPException) as e:
        _actions_from([{"key": "a"}, {"key": "b"}, {"label": "no key here"}])
    assert "action 2" in str(e.value.detail)


def test_a_non_object_action_is_refused_too():
    with pytest.raises(HTTPException) as e:
        _actions_from(["notify"])
    assert e.value.status_code == 422
    assert "must be an object" in str(e.value.detail)


def test_an_empty_key_counts_as_missing():
    """An action keyed "" does nothing and would be stored happily."""
    with pytest.raises(HTTPException):
        _actions_from([{"key": ""}])


def test_valid_actions_are_built_unchanged():
    """CONTROL. Over-refusing would break every automation in the catalog."""
    built = _actions_from([
        {"key": "notify", "label": "Tell the manager", "params": {"to": "manager"}},
        {"key": "create_task"},
    ])
    assert [a.key for a in built] == ["notify", "create_task"]
    assert built[0].label == "Tell the manager"
    assert built[0].params == {"to": "manager"}
    assert built[1].label == "" and built[1].params == {}


def test_no_actions_is_not_an_error():
    """An automation with no actions yet is a draft, not a malformed request."""
    assert _actions_from([]) == []
    assert _actions_from(None) == []


def test_the_raw_comprehension_really_did_raise_keyerror():
    """MUTATION CONTROL. The original shape, so the test cannot pass for a
    reason unrelated to the fix."""
    with pytest.raises(KeyError):
        [x["key"] for x in [{"kind": "notify"}]]
